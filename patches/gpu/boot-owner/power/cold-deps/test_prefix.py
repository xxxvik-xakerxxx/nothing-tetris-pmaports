#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source, signed-LK and patch-application checks only; no native code execution."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from audit_cold import HERE, ROOT, PINS, git_source, trace_lk, trace_sources, trace_modules, sha
from generate_prefix import NATIVE, RESEARCH, SOURCE, native_variant, render
import ci_prefix


def prepared_native(pristine):
    if sha(pristine) != PINS['native_pristine_sha256']:
        raise ValueError('pinned native Linux source mismatch')
    package = ROOT / 'pmaports/device/testing/linux-postmarketos-mediatek-mt6878'
    with tempfile.TemporaryDirectory(prefix='cold-prefix-native-') as directory:
        target = Path(directory) / NATIVE
        target.parent.mkdir(parents=True)
        target.write_bytes(pristine)
        for name, expected in PINS['native_patches'].items():
            path = package / name
            if sha(path.read_bytes()) != expected:
                raise ValueError('packaged native patch drift: ' + name)
            subprocess.run(['git', 'apply', '--unidiff-zero', '--include=' + NATIVE, str(path)],
                           cwd=directory, check=True, capture_output=True)
        if sha(target.read_bytes()) != PINS['native_prepared_sha256']:
            raise ValueError('prepared native source mismatch')
        return target.read_text()


class PrefixSource(unittest.TestCase):
    def setUp(self):
        self.delta, self.files = render()
        self.native = (HERE / 'native-prefix.inc').read_text()
        self.parent = (HERE / 'mt6878-gpueb-cold-prefix.c').read_text()
        self.mfg0 = self.files[RESEARCH + 'mt6878-gpueb-mfg0.c']

    def test_generated_patch_matches(self):
        self.assertEqual(self.delta, (HERE / 'native-prefix.patch').read_text())

    def test_required_kconfig_matches_the_packaged_native_supplier(self):
        text = (HERE / 'ci_prefix.py').read_text()
        self.assertIn('CONFIG_MTK_SCPSYS_PM_DOMAINS=y', text)
        self.assertNotIn('CONFIG_MTK_PM_DOMAINS=y', text)
        shipping = (ROOT / 'pmaports/device/testing/linux-postmarketos-mediatek-mt6878/'
                    'config-postmarketos-mediatek-mt6878.aarch64').read_text()
        self.assertIn('CONFIG_MTK_SCPSYS_PM_DOMAINS=y', shipping.splitlines())

    def test_no_invented_physical_dependencies(self):
        for text in (self.native, self.parent, self.mfg0):
            for forbidden in ('MTK_SCPD_DOMAIN_SUPPLY', 'regulator_enable(', 'regulator_get(',
                              'clk_prepare_enable(', '__clk_is_enabled(', 'pd->supply', 'pd->num_clks',
                              'proven', 'cookie', 'dummy', 'arm_smccc', 'writel(', 'regmap_write('):
                self.assertNotIn(forbidden, text)

    def test_native_identity_and_exact_lk_condition(self):
        for token in ('dev_gpd_data(dev)', 'genpd->power_on != scpsys_power_on',
                      'pd->scpsys->soc_data != &mt6878_scpsys_data',
                      'pd->data != &scpsys_domain_data_mt6878[MT6878_POWER_DOMAIN_MFG0_SHUTDOWN]',
                      'regmap_read(pd->scpsys->base, pd->data->ctl_offs, &ctl)',
                      '(GENMASK(31, 30) | BIT(12) | BIT(13))', '(GENMASK(31, 30) | BIT(13))'):
            self.assertIn(token, self.native)

    def test_existing_bus_owner_and_no_guessed_ack(self):
        self.assertIn('{ 0x0ca0, 0x0c40 }', self.native)
        self.assertIn('scpsys_bus_protect_get_regmap(pd, bpd)', self.native)
        self.assertIn('enabled & bpd->bus_prot_set_clr_mask', self.native)
        for forbidden in ('ioremap(', 'bus_prot_sta', 'poll_timeout', 'syscon_node_to_regmap'):
            self.assertNotIn(forbidden, self.native)

    def test_sram_claim_and_publication_precede_real_pm(self):
        self.assertLess(self.parent.index('mt6878_gpueb_sram_create('), self.parent.index('mt6878_gpueb_mfg0_resume('))
        self.assertLess(self.parent.index('*result = prefix'), self.parent.index('mt6878_gpueb_mfg0_resume('))
        self.assertIn('mt6878_gpueb_reset_validate_resources(parent)', self.parent)
        resume = self.mfg0.split('int mt6878_gpueb_mfg0_resume(', 1)[1].split('EXPORT_SYMBOL', 1)[0]
        self.assertLess(resume.index('pm_runtime_get_sync(dev)'), resume.index('mt6878_cold_mfg0_readback(dev)'))
        self.assertIn('mt6878_gpueb_mfg0_quarantine(scope, ret)', resume)

    def test_no_unsafe_continuation(self):
        for text in (self.parent, self.native):
            for token in ('install_retained(', 'reset_hold(', 'dispatch_acquire(', 'reset_provider_register(',
                          '0x13f9', '0x13fa', 'BOOTREADY', 'platform_driver_register('):
                self.assertNotIn(token, text)

    def test_success_retains_real_usage_not_lock(self):
        finish = self.mfg0.split('int mt6878_gpueb_mfg0_finish(', 1)[1].split('EXPORT_SYMBOL', 1)[0]
        block = finish.split('if (scope->attempted) {', 1)[1].split('\n\t}', 1)[0]
        self.assertIn('scope->task = NULL', block)
        self.assertIn('device_unlock(dev)', block)
        for token in ('pm_runtime_put', 'module_put', 'kfree', '*slot = NULL'):
            self.assertNotIn(token, block)
        self.assertLess(finish.index('scope->first_error'), finish.index('scope->attempted'))

    def test_source_drift_cannot_be_adopted(self):
        original = Path.read_bytes
        with patch.object(Path, 'read_bytes', lambda path: b'foreign change' if path == ROOT / SOURCE else original(path)):
            with self.assertRaisesRegex(ValueError, 'supplier drift'):
                render()
        with self.assertRaisesRegex(ValueError, 'packaged source drift'):
            native_variant('not pinned Linux')

    def test_compilation_guard_is_before_any_write_or_process(self):
        with tempfile.TemporaryDirectory(prefix='cold-prefix-guard-') as tmp:
            root = Path(tmp)
            for ci, github in (('', ''), ('true', ''), ('', 'true')):
                with patch.dict(os.environ, CI=ci, GITHUB_ACTIONS=github), \
                        patch('subprocess.run', side_effect=AssertionError('unexpected process')):
                    with self.assertRaisesRegex(ValueError, 'CI-only'):
                        ci_prefix.build(root / 'kernel', root / 'output', root / 'work', root / 'report', root / 'baseline')
                self.assertEqual(list(root.iterdir()), [])

    def test_private_real_objects_not_mocks_or_full_power(self):
        command = list(map(str, ci_prefix.kernel_command(Path('/kernel'), Path('/private/output'), Path('/private/source'))))
        self.assertEqual(command[-6:], [unit + '.o' for unit in ci_prefix.UNITS])
        self.assertIn('M=/private/source', command)
        self.assertIn('O=/private/output', command)
        self.assertFalse(any('host-include' in value for value in command))
        self.assertNotIn('mt6878-gpueb-control', ci_prefix.UNITS)
        self.assertNotIn('mt6878-gpueb-power', ci_prefix.UNITS)

    def test_private_stage_preserves_inputs_and_existing_work(self):
        with tempfile.TemporaryDirectory(prefix='cold-prefix-stage-') as tmp:
            base = Path(tmp)
            kernel, output, work = base / 'kernel', base / 'output', base / 'work'
            kernel.mkdir(); output.mkdir()
            (kernel / 'preserve').write_text('source\n')
            (output / '.config').write_text('config\n')
            with patch('ci_prefix.prepared_inputs', return_value=(ci_prefix.checked_sources(), {})):
                variant, _ = ci_prefix.stage(kernel, output, work, base / 'baseline')
                with self.assertRaises(FileExistsError):
                    ci_prefix.stage(kernel, output, work, base / 'baseline')
            self.assertEqual((kernel / 'preserve').read_text(), 'source\n')
            (work / 'output/.config').write_text('private\n')
            self.assertEqual((output / '.config').read_text(), 'config\n')
            self.assertIn('ccflags-y += -I$(src)/include', (variant / 'Makefile').read_text())


class ExactEvidence(unittest.TestCase):
    def test_native_descriptor_headers_come_from_exact_linux_and_patches(self):
        tree = Path(os.environ.get('TETRIS_LINUX_GIT', '/private/tmp/tetris-gpu-canonical-linux.git'))
        if not tree.exists():
            self.skipTest('pinned Linux git object not supplied')
        package = ROOT / 'pmaports/device/testing/linux-postmarketos-mediatek-mt6878'
        paths = list(PINS['native_headers'])
        with tempfile.TemporaryDirectory(prefix='cold-prefix-headers-') as tmp:
            base = Path(tmp)
            target = base / paths[0]
            target.parent.mkdir(parents=True)
            target.write_bytes(git_source(tree, PINS['linux'], paths[0]))
            for name, expected in PINS['native_header_patches'].items():
                source = package / name
                self.assertEqual(sha(source.read_bytes()), expected)
                subprocess.run(['git', 'apply', '--unidiff-zero', *('--include=' + path for path in paths), str(source)],
                               cwd=tmp, check=True, capture_output=True)
            for path, expected in PINS['native_headers'].items():
                self.assertEqual(sha((base / path).read_bytes()), expected)

    def test_exact_modules_symlink_and_later_mali_phase(self):
        tree = Path(os.environ.get('TETRIS_MODULES_TREE', str(ROOT.parent / 'android_kernel_modules_nothing_mt6878')))
        if not tree.exists():
            self.skipTest('exact NOS modules git objects not supplied')
        report = trace_modules(tree)
        self.assertEqual(report['power_on_line'], 111)
        self.assertIn('not a GPUEB cold boot', report['phase'])

    def test_actual_nos_optional_contract_and_runtime_phases(self):
        tree = Path(os.environ.get('TETRIS_DEVICE_MODULES_TREE', str(ROOT.parent / 'android_kernel_device_modules_6.1_nothing_mt6878')))
        if not tree.exists():
            self.skipTest('exact NOS git objects not supplied')
        report = trace_sources(tree)
        self.assertIn('optional absent regulator', report['mfg0'])
        self.assertIn('mt6315 driver', report['gpu_rails'])
        self.assertIn('not cold initialization', report['gpueb_boot_clock'])

    def test_apply_after_exact_native_packages_without_touching_frozen_files(self):
        tree = Path(os.environ.get('TETRIS_LINUX_GIT', '/private/tmp/tetris-gpu-canonical-linux.git'))
        if not tree.exists():
            self.skipTest('pinned Linux git object not supplied')
        native = prepared_native(git_source(tree, PINS['linux'], NATIVE))
        with tempfile.TemporaryDirectory(prefix='cold-prefix-apply-') as tmp:
            target = Path(tmp) / NATIVE
            target.parent.mkdir(parents=True)
            target.write_text(native)
            for name in ('mt6878-gpueb-mfg0.c', 'mt6878-gpueb-mfg0.h'):
                source = ROOT / 'patches/gpu/mfg0-supplier-draft' / name
                destination = Path(tmp) / RESEARCH / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            subprocess.run(['git', 'apply', '--unidiff-zero', str(HERE / 'native-prefix.patch')],
                           cwd=tmp, check=True, capture_output=True)
            self.assertEqual(target.read_text(), native_variant(native))
            for path, source in render()[1].items():
                self.assertEqual((Path(tmp) / path).read_text(), source)

    def test_signed_lk_bit13_direction_and_stub(self):
        path = Path(os.environ.get('TETRIS_LK_IMG', str(ROOT.parents[1] /
            'worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img')))
        if not path.exists():
            self.skipTest('signed LK not supplied')
        try:
            from audit_gpueb_b41 import signed_lk, read_bounded
        except ModuleNotFoundError as error:
            if error.name != 'capstone':
                raise
            self.skipTest('offline Capstone static-inspection dependency not supplied')
        code = signed_lk(read_bounded(path, 8 * 1024 * 1024))
        result = trace_lk(code)
        self.assertEqual(result['pre_rpc_admission']['bit13'], 'SET, not clear')
        self.assertIn('zero-return stub', result['caller'])
        self.assertEqual(result['gpueb_pll_timeout_read']['address'], '0x13fa080c')
        self.assertIn('earlier than 0x1ebc8', result['first_unresolved_producer'])
        modified = bytearray(code)
        modified[0x1ebe0] ^= 1
        with self.assertRaisesRegex(ValueError, 'payload mismatch'):
            trace_lk(modified)


if __name__ == '__main__':
    unittest.main()
