#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static negative contracts and real git apply, no C execution or compilation."""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check
import generate as gen
import run_ci
import stage


class ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.output, cls.evidence = check.check(ARGS.kernel_archive, ARGS.device_repo, ARGS.modules_repo)

    def changed(self, path, old, new):
        output = dict(self.output)
        self.assertIn(old, output[path])
        output[path] = output[path].replace(old, new, 1)
        return output

    def reject(self, path, old, new, message):
        with self.assertRaisesRegex(ValueError, message):
            check.contracts(self.base, self.changed(path, old, new), self.evidence)

    def test_production_closure(self):
        self.assertEqual(len(self.evidence['production_units']), 16)
        check.contracts(self.base, self.output, self.evidence)

    def test_no_dt_payload(self):
        with self.assertRaisesRegex(ValueError, 'DT activation'):
            check.contracts(self.base, {**self.output, 'arch/arm64/fake.dts': ''}, self.evidence)

    def test_default_off(self):
        self.reject(gen.DIR + 'Kconfig', 'default n', 'default y', 'default off')

    def test_builtin_only(self):
        self.reject(gen.DIR + 'Kconfig', '\tbool ', '\ttristate ', 'built-in only')

    def test_shared_provider_cannot_be_module(self):
        self.reject(gen.DIR + 'Kconfig', 'MTK_SMI=y', 'MTK_SMI', 'constrained built-in')

    def test_duplicate_kbuild_unit(self):
        self.reject(gen.DIR + 'Makefile', 'cold-capture.o\n', 'cold-capture.o cold-capture.o\n', 'Kbuild unit drift')

    def test_no_smoke_replacement(self):
        evidence = deepcopy(self.evidence)
        evidence['production_units'][0] = 'test-smoke.o'
        output = self.changed(gen.DIR + 'Makefile', 'mt6878-camsv-vb2.o', 'test-smoke.o')
        output[gen.DIR + 'test-smoke.c'] = ''
        with self.assertRaisesRegex(ValueError, 'substituted'):
            check.contracts(self.base, output, evidence)

    def test_missing_header(self):
        output = dict(self.output)
        del output[gen.DIR + 'cold-capture.h']
        with self.assertRaisesRegex(ValueError, 'unresolved production include'):
            check.contracts(self.base, output, self.evidence)

    def test_no_duplicate_graph(self):
        self.reject(gen.SENINF_MAKEFILE, 'ifneq', 'ifeq', 'duplicate graph owner')

    def test_missing_real_export(self):
        self.reject('drivers/memory/mt6878-camisp-smi.inc',
                    'EXPORT_SYMBOL_GPL(mt6878_camisp_dma_idle)', '', 'real provider export')

    def test_sensor_uses_pad_lifecycle(self):
        self.reject(gen.stream.DRIVER, '.enable_streams = imx882_enable_streams,', '', 'pad stream lifecycle')

    def test_sensor_no_recursive_state_lock(self):
        self.reject(gen.stream.DRIVER, 'lockdep_assert_held(&camera->lock);',
                    'mutex_lock(&camera->lock);', 'recursively lock')

    def test_mclk_contract_not_rewritten(self):
        self.reject(gen.stream.DRIVER, 'clk_rate_exclusive_get(imx882->xclk_source)',
                    'clk_prepare_enable(imx882->xclk_source)', 'frozen lifecycle drift')

    def test_no_active_sensor_cleanup(self):
        self.reject(gen.stream.DRIVER, 'v4l2_subdev_is_streaming(sd) ? -EBUSY : imx882_stop(camera)',
                    'imx882_stop(camera)', 'reject an active stream')

    def test_no_null_sensor_state(self):
        self.reject(gen.DIR + 'mt6878-seninf-route.c',
                    'v4l2_subdev_call_state_active(r->sensor, pad, get_fmt, &fmt)',
                    'v4l2_subdev_call(r->sensor, pad, get_fmt, NULL, &fmt)', 'NULL active sensor state')

    def test_owner_identified_before_container(self):
        self.reject(gen.PD + 'mt6878-native-vmm.inc',
                    'consumer->pm_domain->ops.runtime_resume != scpsys_vmm_resume',
                    'consumer->pm_domain->ops.runtime_resume != genpd_runtime_resume', 'substring not found')

    def test_cached_on_does_not_bypass_vmm(self):
        self.reject(gen.PD + 'mtk-pm-domains.c',
                    'pd->genpd.domain.ops.runtime_resume = scpsys_vmm_resume',
                    'pd->genpd.domain.ops.runtime_resume = genpd_runtime_resume', 'cached-ON')

    def test_receiver_cannot_resume_unknown_owner(self):
        self.reject(gen.DIR + 'mt6878-seninf-pm.c',
                    'mt6878_camera_vmm_validate_domain(p->domains[0], MT6878_POWER_DOMAIN_CAM_MAIN)',
                    '0', 'substring not found')

    def test_camsv_cannot_resume_unknown_owner(self):
        self.reject(gen.DIR + 'mt6878-camsv-platform.c',
                    'mt6878_camera_vmm_validate_domain(p->cam_main, MT6878_POWER_DOMAIN_CAM_MAIN)',
                    '0', 'substring not found')

    def test_disabled_vmm_not_success(self):
        self.reject(gen.HEADER, 'return -EOPNOTSUPP;', 'return 0;', 'stub claims success')

    def test_legacy_vote_veto(self):
        self.reject(gen.PD + 'mt6878-native-vmm.inc', 'mediatek,vmm_notifier',
                    'not-a-voter', 'admission veto')

    def test_camsv_real_vmm_gate(self):
        self.reject(gen.DIR + 'mt6878-camsv-hardware.c',
                    'mt6878_camera_vmm_check(p->cam_main, MT6878_POWER_DOMAIN_CAM_MAIN)', '0', 'powered access')

    def test_receiver_retains_failed_leases(self):
        self.reject(gen.DIR + 'mt6878-seninf-pm.c', 'p->first_error ? p->first_error : release(p)',
                    'release(p)', 'unwinds retained')

    def test_no_self_supplier(self):
        self.reject(gen.DIR + 'cold-capture.c', 's->dma == &s->pdev->dev', 'false', 'topology guard')

    def test_receiver_topology_exact(self):
        self.reject(gen.DIR + 'cold-capture.c', 'receiver == s->receiver', 'true', 'topology guard')

    def test_real_runtime_links(self):
        self.reject(gen.DIR + 'cold-capture.c', 'DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER',
                    'DL_FLAG_AUTOREMOVE_CONSUMER', 'topology guard|runtime-PM')

    def test_constructor_checks_installed(self):
        self.reject(gen.DIR + 'mt6878-native-video.c', 'ret = mt6878_cold_suppliers_check(s);',
                    'ret = 0;', 'real constructor')

    def test_no_unverified_ccd_adoption(self):
        evidence = deepcopy(self.evidence)
        evidence['adopted_tracked_sha256']['patches/camera-ccd-bus/mt6878-ccd-bus.c'] = 'unverified'
        with self.assertRaisesRegex(ValueError, 'CCD source adopted'):
            check.contracts(self.base, self.output, evidence)

    def write_base(self, root):
        for path, text in self.base.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)

    def test_actual_strict_patch_application(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.write_base(tree)
            stage.apply(tree, self.base, self.output)
            for path, text in self.output.items():
                self.assertEqual((tree / path).read_text(), text)

    def test_prepared_native_source_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.write_base(tree)
            (tree / 'drivers/pinctrl/mediatek/pinctrl-paris.c').write_text('unverified')
            with self.assertRaisesRegex(ValueError, 'prepared input differs'):
                stage.apply(tree, self.base, self.output)
            self.assertFalse((tree / gen.DIR).exists())

    def test_preexisting_candidate_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.write_base(tree)
            target = tree / gen.rail.DRIVER
            target.write_text('preexisting-untracked')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                stage.apply(tree, self.base, self.output)
            self.assertEqual(target.read_text(), 'preexisting-untracked')


class RunnerTests(unittest.TestCase):
    def test_shipping_owners_disabled(self):
        gen.shipping_disabled('# CONFIG_VIDEO_MT6878_COLD_CAPTURE is not set\n')
        for name in ('VIDEO_MT6878_COLD_CAPTURE', 'REGULATOR_TETRIS_CAMERA_GPIO', 'MTK_MT6878_NATIVE_VMM'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'enabled in shipping'):
                gen.shipping_disabled('CONFIG_' + name + '=y\n')

    def test_local_compile_refused_before_any_tools(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(run_ci.gen, 'build') as build:
            with self.assertRaisesRegex(ValueError, 'CI-only'):
                run_ci.main()
            build.assert_not_called()

    def test_ci_requires_both_markers(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'CI-only'):
                run_ci.ci_only()

    def test_security_profile_not_disabled_for_elf(self):
        original = 'CONFIG_LTO_CLANG_THIN=y\nCONFIG_CFI=y\nCONFIG_RANDOMIZE_BASE=y\n'
        self.assertEqual(run_ci.verify_security(original, original)['CFI'], 'y')
        for name in ('LTO_CLANG_THIN', 'CFI', 'RANDOMIZE_BASE'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'security profile changed'):
                run_ci.verify_security(original, original.replace('CONFIG_' + name + '=y', '# CONFIG_' + name + ' is not set'))

    def test_output_paths_must_be_disjoint(self):
        with self.assertRaisesRegex(ValueError, 'disjoint'):
            run_ci.separate_paths(Path('/tmp/kernel'), Path('/tmp/kernel/out'), Path('/tmp/report'))

    def test_export_plan_matches_real_owners(self):
        self.assertEqual(set(run_ci.EXPORTS), set(check.EXPORT_OWNER))

    def test_ci_runner_really_links_native_kernel(self):
        text = (gen.HERE / 'run_ci.py').read_text()
        self.assertIn("run([*make, 'vmlinux'])", text)
        self.assertIn('smoke.object_identity(artifact)', text)
        self.assertNotIn('LTO_NONE', text)
        self.assertNotIn('modules_prepare', text)

    def test_candidate_stages_only_an_independent_source_copy(self):
        text = (gen.HERE / 'run_ci.py').read_text()
        self.assertIn('shutil.copytree(kernel, source,', text)
        self.assertIn('stage.apply(source, base, output)', text)
        self.assertNotIn('stage.apply(kernel, base, output)', text)
        self.assertIn('stage.verify_prepared(kernel, base, output)', text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    gen.stream.arguments(parser)
    ARGS = parser.parse_args()
    unittest.main(argv=[__file__])
