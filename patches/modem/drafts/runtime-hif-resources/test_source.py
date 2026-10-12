#!/usr/bin/env python3
"""Source/application/lifecycle checks only; no compiler or device operations."""
import hashlib
import json
import os
from pathlib import Path
import re
import unittest

from check_resources import HERE, ROOT, ECCCI, CENSUS, GUARD, PAYLOADS, build, function, replace, review
from run_native_ci import fixture

VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', ROOT.parent / 'android_kernel_device_modules_6.1_nothing_mt6878'))


class ResourceSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch, cls.before, cls.after, cls.report = build(VENDOR)

    def test_whole_stack_generation_application_and_evidence(self):
        self.assertEqual(self.patch, (HERE / 'resources.overlay').read_text())
        evidence = json.loads((HERE / 'SOURCE-EVIDENCE.json').read_text())
        for key, value in self.report.items():
            self.assertEqual(value, evidence[key], key)

    def test_exact_edit_scope(self):
        touched = set(re.findall(r'^diff --git a/(\S+) b/', self.patch, re.M))
        self.assertEqual(touched, set(self.before) | {ECCCI + name for name in PAYLOADS.values()})
        for token in ('Kconfig', 'Makefile', 'APKBUILD', 'EXPORT_SYMBOL', '.dts', 'provider.h'):
            self.assertNotIn(token, self.patch)

    def test_resources_are_handles_not_permission(self):
        payload = re.sub(r'/\*.*?\*/', '', '\n'.join((HERE / name).read_text() for name in PAYLOADS), flags=re.S)
        for token in ('ioremap', 'of_iomap', 'readl(', 'writel(', 'request_irq(', 'enable_irq(',
                      'irq_set_irq_wake(', 'dma_alloc', 'dma_map', 'dma_set', 'clk_prepare_enable(',
                      'pm_runtime_get', 'arm_smccc', 'ccci_hif_register(', 'EXPORT_SYMBOL', 'bool ready',
                      'bool authorized', 'NS_READY', 'MD_SETTING_ENABLE', 'modem_sys =', 'platform_data =',
                      'platform_get_irq(', 'irq_of_parse_and_map(', 'irq_create_of_mapping('):
            self.assertNotIn(token, payload, token)
        # Comments can name a blocked function but must not contain an executable call.
        self.assertIn('devm_request_mem_region(', payload)
        self.assertIn('of_irq_parse_one(', payload)
        self.assertIn('devm_clk_get(', payload)

    def test_actual_resource_lifetimes_and_first_errors(self):
        common = (HERE / 'resources.h').read_text()
        supplier = (HERE / 'supplier.h').read_text()
        self.assertIn('return PTR_ERR(res->clk[i]);', supplier)
        self.assertIn('tetris_irq_descriptor(&pdev->dev, i, &res->irq[i])', supplier)
        self.assertIn('res->irq[j]', supplier)
        self.assertLess(supplier.index('devm_clk_get('), supplier.index('platform_set_drvdata(pdev, res)'))
        self.assertIn('devm_add_action_or_reset(dev, tetris_node_put, node)', common)
        self.assertLess(common.index('strcmp(supplier->dev.driver->name, name)'),
                        common.index('res = platform_get_drvdata(supplier)'))
        self.assertLess(common.index('try_module_get(res->owner)'), common.index('get_device(&supplier->dev)'))
        self.assertIn('devm_add_action_or_reset(consumer, tetris_hif_release, lease)', common)
        self.assertIn('module_put(lease->owner);\n\tput_device(&lease->pdev->dev);', common)
        self.assertNotIn('irq_dispose_mapping(', common + supplier)

    def test_supplier_probe_bypasses_legacy_hardware_init(self):
        for filename, probe, old in (('ccci_hif_ccif.c', 'ccci_hif_ccif_probe', 'ccci_ccif_hif_init('),
                                     ('ccci_dpmaif_com.c', 'dpmaif_probe', 'dpmaif_init_com(')):
            source = self.after[ECCCI + 'hif/' + filename]
            body = function(source, probe)[0]
            self.assertLess(body.index('return tetris_hif_supplier_probe('), body.index(old))
            self.assertIn(GUARD + '\t\t.pm = NULL,', source)
            self.assertIn('.remove = tetris_hif_supplier_remove,', source)
            self.assertIn('.suppress_bind_attrs = true,', source)

    def test_private_prepare_is_a_separate_request(self):
        source = self.after[ECCCI + 'fsm/md_sys1_platform.c']
        init = function(source, 'modem_cd_init')[0]
        self.assertLess(init.index('if (!tetris_private_prepare)'), init.index('tetris_preflight_driver('))
        self.assertLess(init.index('tetris_preflight_driver('), init.index('platform_driver_register('))
        probe = function(source, 'ccci_modem_probe')[0]
        self.assertLess(probe.index('if (!tetris_private_prepare)'), probe.index('tetris_ccci_dependencies('))
        self.assertIn('bool, 0400)', source)
        self.assertIn('return tetris_modem_hw_resources(dev_ptr, dev_cfg, hw_info);', source)
        registration = self.after[ECCCI + 'fsm/register_prepare.h']
        self.assertIn('#if !IS_ENABLED(CONFIG_TETRIS_CCCI_HIF_RESOURCES)\n\tret = tetris_pin_hif_modules();', registration)
        self.assertIn('ret = tetris_ccci_mem_prepare(md);', registration)
        commit = function(registration, 'ccci_tetris_register_prepared')[0]
        self.assertLess(commit.index('return -EOPNOTSUPP'), commit.index('device_trylock('))
        self.assertIn('tetris_prepared_md = md;', registration)
        self.assertIn('ccci_tetris_registration_quarantine(ret)', registration)

    def test_unused_pericfg_is_not_a_new_mt6878_prerequisite(self):
        source = (HERE / 'supplier.h').read_text()
        self.assertIn('if (id != CCIF_HIF_ID ||', source)
        self.assertIn('of_find_property(pdev->dev.of_node, "ccif-pericfg", NULL)', source)
        self.assertIn('generation != 6299 || platform != 6878', (HERE / 'modem.h').read_text())
        self.assertEqual(self.report['ccif_pericfg']['policy'],
                         'optional for resource-only MT6878/6299; validate if present')

    def test_artifact_inspector_checks_headers_not_only_constructor_source(self):
        source = (HERE / 'inspect_init.py').read_text()
        self.assertIn("recorded.get('overlay_sha256') != evidence['overlay_sha256']", source)
        self.assertIn("evidence['touched_source_sha256'].items()", source)
        self.assertIn("compiled resource header/source differs", source)

    def test_preprobe_pm_hazard_fails_before_registration(self):
        common = (HERE / 'resources.h').read_text()
        for token in ('power-domains', 'assigned-clocks', 'iommus', 'iommu-map', 'of_device_is_available(node)'):
            self.assertIn(token, common)
        for path, init in (('hif/ccci_hif_ccif.c', 'ccci_hif_ccif_init'),
                           ('hif/ccci_dpmaif_com.c', 'ccci_dpmaif_init')):
            body = function(self.after[ECCCI + path], init)[0]
            self.assertLess(body.index('tetris_preflight_driver('), body.index('platform_driver_register('))

    def test_optional_companions_denied_and_no_new_exports(self):
        for path, probe in (('hif/ccci_hif_cldma.c', 'ccci_hif_cldma_probe'),
                            ('ccci_auxadc.c', 'get_auxadc_probe'), ('fsm/ccci_fsm_scp_c.c', 'ccci_scp_probe')):
            body = function(self.after[ECCCI + path], probe)[0]
            self.assertIn('{\n' + GUARD + '\treturn -EOPNOTSUPP;\n#endif\n', body)
        consumer = (HERE / 'consumer.h').read_text()
        self.assertIn('DL_FLAG_AUTOREMOVE_CONSUMER', consumer)
        self.assertNotIn('DL_FLAG_PM_RUNTIME', consumer)
        self.assertNotIn('device_link_del(', consumer)
        self.assertNotIn('symbol_get(', consumer)

    def test_census_covers_all_eight_and_raw_global_lookups(self):
        for profile in ('base_init_census', 'resource_init_census'):
            census = self.report[profile]
            self.assertEqual(set(census) - {'global_of_searches'}, set(CENSUS))
            self.assertIsNone(census['ccmni']['module_init'])
            self.assertIsNone(census['rps_perf']['module_init'])
            self.assertIn(ECCCI + 'hif/ccci_hif_ccif.c', census['global_of_searches'])
            self.assertIn('of_find_compatible_node(', json.dumps(census['global_of_searches']))

    def test_source_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            replace('changed', 'expected', 'new')
        with self.assertRaises(ValueError):
            function('int missing(void);', 'missing')

    def test_native_fixture_uses_actual_helpers_and_gated_runner(self):
        code = fixture()
        self.assertNotIn('/* PRODUCTION */', code)
        self.assertIn('static int tetris_hif_supplier_probe(', code)
        self.assertIn('static int tetris_resource_dependencies(', code)
        self.assertIn('for (int f = 1; f <= total[i]; f++)', code)
        runner = (HERE / 'run_native_ci.py').read_text()
        self.assertLess(runner.index("os.environ.get('CI')"), runner.index("subprocess.run(['cc'"))
        self.assertIn("'-Wall', '-Wextra', '-Werror'", runner)
        self.assertIn('detect_leaks=1:halt_on_error=1', runner)

    def test_review_manifest_coverage_and_identity(self):
        review()

    def test_irq_bounds_precede_parser_and_hardware_identity_ignores_trigger(self):
        source = (HERE / 'resources.h').read_text()
        body = source.split('static inline int tetris_irq_descriptor(', 1)[1].split(
            'static inline bool tetris_same_irq(', 1)[0]
        for preflight in ('"interrupts-extended"', 'cells > MAX_PHANDLE_ARGS',
                          'of_property_count_u32_elems', 'index >= count / cells'):
            self.assertLess(body.index(preflight), body.index('of_irq_parse_one('))
        self.assertIn('of_device_is_compatible(parent, "arm,gic-v3")', body)
        identity = source.split('static inline bool tetris_same_irq(', 1)[1].split('}', 1)[0]
        self.assertIn('a->args[1] == b->args[1]', identity)
        self.assertNotIn('memcmp', identity)
        self.assertNotIn('args[2]', identity)

    def test_inherited_address_capacity_is_checked_before_parser(self):
        source = (HERE / 'resources.h').read_text()
        body = source.split('static inline int tetris_irq_descriptor(', 1)[1]
        self.assertLess(body.index('tetris_irq_address_shape(parent)'),
                        body.index('of_irq_parse_one('))
        guard = source.split('static inline int tetris_irq_address_shape(', 1)[1].split(
            'static inline int tetris_irq_descriptor(', 1)[0]
        self.assertIn('ret != 1', guard)
        self.assertIn('cells <= 2', guard)
        self.assertIn('of_get_parent(node)', guard)
        fixture_source = (HERE / 'test_resources.c').read_text()
        self.assertIn('nodes[7].address_cells = 4', fixture_source)
        self.assertIn('nodes[5].address_cells = 4', fixture_source)

    def test_fixture_uses_real_capacity_and_exclusive_claim_ledger(self):
        fixture_source = (HERE / 'test_resources.c').read_text()
        self.assertIn('#define MAX_PHANDLE_ARGS 16', fixture_source)
        self.assertIn('claims[i].active && start <= claims[i].resource.end', fixture_source)
        self.assertIn('claim->active = false;', fixture_source)
        self.assertIn('auxiliary[1] = auxiliary[0]', fixture_source)
        self.assertIn('suppliers[1].mem[0] = suppliers[0].mem[0]', fixture_source)
        self.assertIn('MAX_PHANDLE_ARGS + 1', fixture_source)


if __name__ == '__main__':
    unittest.main()
