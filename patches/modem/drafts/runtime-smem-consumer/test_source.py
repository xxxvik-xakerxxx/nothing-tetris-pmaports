#!/usr/bin/env python3
"""Focused source/negative/application checks; no native compiler or hardware."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import unittest
from check_consumer import HERE, ROOT, ECCCI, UTIL, COMMON, GUARD, build, replace, apply_check

VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', ROOT.parent /
    'android_kernel_device_modules_6.1_nothing_mt6878'))


class ConsumerSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundles = build(VENDOR)

    def test_frozen_generation_and_apply(self):
        for name, (text, before, _) in self.bundles.items():
            self.assertEqual(text, (HERE / name).read_text())
            apply_check(text, before)

    def test_complete_review_manifest(self):
        files = {}
        for line in (HERE / 'REVIEW.sha256').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertNotIn(name, files)
            self.assertEqual(digest, hashlib.sha256((HERE / name).read_bytes()).hexdigest())
            files[name] = digest
        expected = {p.name for p in HERE.iterdir() if p.is_file()
                    and (p.name == 'Kbuild' or p.suffix in ('.py', '.c', '.h', '.md', '.overlay'))}
        self.assertEqual(set(files), expected)

    def test_patch_scope_is_only_additive_binding(self):
        allowed = {COMMON, UTIL + 'owned_smem_plan.c', UTIL + 'tetris_smem_provider.h',
            ECCCI + 'modem_sys.h', ECCCI + 'fsm/modem_sys1.c',
            ECCCI + 'fsm/register_prepare.h', ECCCI + 'fsm/tetris_smem_consumer.h'}
        touched = set()
        for text, _, _ in self.bundles.values():
            touched.update(re.findall(r'^diff --git a/(\S+) b/', text, re.M))
            for token in ('Kconfig', 'Makefile', '.dts', 'APKBUILD', 'EXPORT_SYMBOL_GPL(ccci_md_get_mem)'):
                self.assertNotIn(token, text)
        self.assertEqual(touched, allowed)

    def test_provider_reuses_real_private_export_and_module_ref(self):
        source = (HERE / 'provider.h').read_text()
        self.assertIn('tetris_owned_smem_plan.owner', source)
        self.assertIn('EXPORT_SYMBOL_GPL(mtk_ccci_owned_mapped_copy)', source)
        self.assertLess(source.index('try_module_get(THIS_MODULE)'),
                        source.index('tetris_smem_export_mapped_private('))
        self.assertIn('module_put(THIS_MODULE);\n\t\treturn ret;', source)
        self.assertLess(source.index('tetris_smem_export_mapped_private('),
                        source.index('out->provider = THIS_MODULE'))
        for token in ('symbol_get(', 'register_', 'bool ready', 'has_boot_evidence',
                      'ioremap', 'readl(', 'writel(', 'arm_smccc', 'tetris_smem_publish_private('):
            self.assertNotIn(token, source)
        self.assertIn('#ifndef MODULE', source)

    def test_alias_and_duplicate_output_fail_before_reference(self):
        source = (HERE / 'provider.h').read_text()
        for token in ('sizeof(tetris_owned_smem_plan)', 'owner, sizeof(*owner)', 'if (out->provider)'):
            self.assertLess(source.index(token), source.index('try_module_get('))
        self.assertIn('first > ~0UL - bytes || second > ~0UL - size', source)

    def test_actual_private_prepare_order_and_abort(self):
        source = self.bundles['consumer.overlay'][2][ECCCI + 'fsm/register_prepare.h']
        memory = source.index('ret = tetris_ccci_mem_prepare(md)')
        for token in ('ret = ccci_tetris_fsm_prepare()', 'ret = ccci_tetris_ports_prepare(pdev)',
                      'ret = md->ops->init(md)', 'ret = tetris_pin_hif_modules()', 'tetris_prepared_md = md'):
            self.assertLess(memory, source.index(token))
        self.assertIn('ret = tetris_ccci_mem_prepare(md);\n\tif (ret)\n\t\tgoto free_peer;', source)
        abort = source[source.index('free_peer:'):source.index('fault:')]
        self.assertLess(abort.index('tetris_ccci_mem_abort(md)'), abort.index('wakeup_source_unregister'))
        self.assertLess(abort.index('tetris_ccci_mem_abort(md)'), abort.index('kfree(md->private_data)'))
        self.assertIn('return ccci_tetris_registration_quarantine(ret);', source)

    def test_commit_and_legacy_void_config_are_inaccessible(self):
        source = self.bundles['consumer.overlay'][2][ECCCI + 'fsm/register_prepare.h']
        commit = source[source.index('int ccci_tetris_register_prepared('):]
        self.assertLess(commit.index('return -EOPNOTSUPP'), commit.index('device_trylock('))
        self.assertLess(commit.index('return -EOPNOTSUPP'), commit.index('tetris_registration_exposed, true'))
        main = self.bundles['consumer.overlay'][2][ECCCI + 'fsm/modem_sys1.c']
        config = main[main.index('void ccci_md_config('):main.index('int boot_md_show(')]
        self.assertLess(config.index('return;'), config.index('get_md_img_type()'))
        self.assertLess(config.index('return;'), config.index('ap_md_mem_init('))

    def test_consumer_owns_only_storage_and_one_provider_reference(self):
        source = (HERE / 'consumer.h').read_text()
        self.assertIn('copy = kzalloc(sizeof(*copy), GFP_KERNEL)', source)
        self.assertIn('ret = mtk_ccci_owned_mapped_copy(copy)', source)
        self.assertIn('if (ret)\n\t\tgoto free_copy;', source)
        self.assertIn('md->mem_layout = copy->layout;\n\tmd->tetris_smem = copy;', source)
        abort = source[source.index('static void tetris_ccci_mem_abort('):
                       source.index('static int tetris_ccci_mem_prepare(')]
        self.assertLess(abort.index('memset(&md->mem_layout'), abort.index('module_put('))
        self.assertLess(abort.index('module_put('), abort.index('kfree('))
        for token in ('ioremap', 'iounmap', 'ap_md_mem_init(', 'get_md_resv_mem_info(',
                      'mtk_ccci_get_smem_by_id(', 'post_cfg_for_ccb(', 'MD_SETTING_ENABLE',
                      'SMC', 'START', 'modem_sys =', 'platform_data ='):
            self.assertNotIn(token, source)

    def test_native_boundaries_use_actual_copy_layout_bodies(self):
        source = (HERE / 'run_native_ci.py').read_text()
        self.assertIn("('output_overlap', 'copy_layout', 'tetris_smem_export_mapped_private')", source)
        self.assertIn("smem.native_types(vendor)", source)
        self.assertIn("'-Wall', '-Wextra', '-Werror'", source)
        self.assertIn("'-fsanitize=address,undefined'", source)
        self.assertIn("'-fno-sanitize-recover=undefined'", source)
        fixture = (HERE / 'test_binding.c').read_text()
        for token in ('unchanged_failure(-EIO', 'alloc_fail = true', 'pin_fail = true',
                      'i <= 6', 'owner.nc[0].size == 0', 'tetris_ccci_mem_abort(&md)',
                      'tetris_ccci_mem_prepare(&md) == -EALREADY'):
            self.assertIn(token, fixture)

    def test_native_execution_is_rejected_locally(self):
        env = dict(os.environ)
        env.pop('CI', None)
        env.pop('GITHUB_ACTIONS', None)
        result = subprocess.run(['python3', '-B', str(HERE / 'run_native_ci.py'),
            '--vendor', '/nonexistent'], env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('GitHub CI-only', result.stderr)

    def test_native_transaction_fixture_has_real_prepare_body_and_lifetime_faults(self):
        runner = (HERE / 'run_native_ci.py').read_text()
        self.assertIn("runtime-prepare/test_registration.c", runner)
        self.assertIn("['consumer.overlay'][2][ECCCI + 'fsm/register_prepare.h']", runner)
        self.assertIn("'-DMODULE=1'", runner)
        self.assertIn('loadable module lifetime', runner)
        fixture = (HERE / 'test_prepare.c').read_text()
        for token in ('1, 2, 3, 4, 5, 6, 7, 10, 15, 16, 17, 18',
                      'tetris_common_prepare(&pdev, &cfg, &hw) == expected',
                      'mem_provider.pins == 1', 'mem_provider.pins == 2',
                      'ccci_tetris_register_prepared(&pdev) == -EOPNOTSUPP',
                      'assert(!tetris_registration_exposed', 'abort_ports =='):
            self.assertIn(token, fixture)

    def test_native_fixture_assembly_without_compilation(self):
        from run_native_ci import function, prepare_fixture
        fixture = prepare_fixture(VENDOR)
        self.assertNotIn('/* ACTUAL_REGISTRATION */', fixture)
        self.assertNotIn('/* PRODUCTION */', fixture)
        self.assertIn('ret = tetris_ccci_mem_prepare(md)', fixture)
        self.assertIn('assert(md && md->tetris_smem)', fixture)
        self.assertEqual(fixture.count('int main(void)'), 1)
        original = (HERE.parent / 'runtime-smem/smem.c').read_text()
        for name in ('output_overlap', 'copy_layout', 'tetris_smem_export_mapped_private'):
            self.assertTrue(function(original, name))

    def test_optional_smoke_uses_real_modem_type_and_no_persistent_consumer(self):
        source = (HERE / 'private-binding-smoke.c').read_text()
        self.assertIn('#include "modem_sys.h"', source)
        self.assertNotIn('struct ccci_modem {', source)
        self.assertIn('md = kzalloc(sizeof(*md), GFP_KERNEL)', source)
        self.assertEqual(source.count('tetris_ccci_mem_prepare(md)'), 1)
        self.assertEqual(source.count('tetris_ccci_mem_abort(md)'), 1)
        self.assertLess(source.index('tetris_ccci_mem_abort(md)'), source.index('kfree(md)'))
        self.assertIn('module_init(tetris_private_binding_init)', source)
        self.assertIn('module_exit(tetris_private_binding_exit)', source)
        self.assertIn('MODULE_LICENSE("GPL")', source)
        for token in ('ccci_md_alloc(', 'readl(', 'writel(', 'ioremap', 'arm_smccc',
                      'platform_driver', 'register_prepared(', 'tetris_common_prepare(', '__module_get('):
            self.assertNotIn(token, source)
        kbuild = (HERE / 'Kbuild').read_text()
        self.assertIn('obj-m += private-binding-smoke.o', kbuild)
        for path in ('eccci/inc', 'eccci/fsm', 'eccci/hif', 'eccci/port', 'mediatek/include'):
            self.assertIn(path, kbuild)

    def test_exact_context_rejects_missing_and_duplicate_anchor(self):
        for source in ('missing', 'same same'):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                replace(source, 'same', 'changed')

    def test_c_shape_without_compilation(self):
        for name in ('provider.h', 'consumer.h', 'tetris_ccci_smem.h', 'test_binding.c',
                     'test_prepare.c', 'private-binding-smoke.c'):
            text = (HERE / name).read_text()
            text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
            text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', text)
            stack = []
            for char in text:
                if char in '([{':
                    stack.append(char)
                elif char in ')]}':
                    self.assertTrue(stack, name)
                    self.assertEqual(stack.pop(), {')': '(', ']': '[', '}': '{'}[char], name)
            self.assertFalse(stack, name)


if __name__ == '__main__':
    unittest.main()
