#!/usr/bin/env python3
import ast
import os
from pathlib import Path
import unittest
from check_prepare import replace, overlay, build

HERE = Path(__file__).resolve().parent
VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', str(
    HERE.parents[4] / 'android_kernel_device_modules_6.1_nothing_mt6878')))


class PrepareTests(unittest.TestCase):
    def test_syntax(self):
        for path in HERE.glob('*.py'):
            ast.parse(path.read_text())

    def test_no_fuzzy_edits(self):
        for source in ('absent', 'old old'):
            with self.assertRaises(ValueError):
                replace(source, 'old', 'new')
        with self.assertRaises(ValueError):
            overlay({'a': 'wrong\n'}, 'diff --git a/a b/a\n--- a/a\n+++ b/a\n'
                    '@@ -1 +1 @@\n-old\n+new\n')

    def test_prepare_publication_boundary(self):
        source = (HERE / 'register_prepare.h').read_text()
        prepare = source[source.index('static int tetris_common_prepare_locked'):
                         source.index('int ccci_tetris_register_prepared(')]
        for operation in ('ccci_tetris_fsm_prepare()', 'ccci_tetris_ports_prepare(pdev)',
                          'tetris_pin_hif_modules()'):
            self.assertIn(operation, prepare)
        for forbidden in ('modem_sys =', 'platform_data =', 'ccci_md_config(',
                          '_commit()', 'registration_exposed, true', 'ccci_init()'):
            self.assertNotIn(forbidden, prepare)
        commit = source[source.index('int ccci_tetris_register_prepared('):]
        exposure = commit.index('WRITE_ONCE(tetris_registration_exposed, true)')
        for gate in ('device_trylock(', 'device_is_bound(', 'tetris_commit_attempted = true'):
            self.assertLess(commit.index(gate), exposure)
        self.assertLess(exposure, commit.index('ccci_init();'))
        self.assertGreater(source.index('ccci_tetris_fsm_run();'), source.index('tetris_sysfs_register(md);'))
        self.assertIn('cmpxchg(&tetris_registration_error, 0, failure)', source)

    def test_complete_stack_start_and_monitor_boundaries(self):
        _, before, after = build(VENDOR)
        base = 'drivers/misc/mediatek/eccci/'
        self.assertIn('ccci_tetris_owner_entry();', before[base + 'fsm/ccci_fsm.c'])
        self.assertIn('class_create("ccci_node")', before[base + 'ccci_core.c'])
        fsm = after[base + 'fsm/ccci_fsm.c']
        start = fsm[fsm.index('static void fsm_routine_start('):]
        self.assertLess(start.index('ccci_tetris_registration_quarantine(-EOPNOTSUPP)'),
                        start.index('ccci_tetris_owner_entry();'))
        import re
        for path, names in (
            ('fsm/ccci_fsm_monitor.c', ('dev_char_open', 'dev_char_close',
                                      'dev_char_ioctl', 'dev_char_compat_ioctl')),
            ('fsm/ccci_fsm_ioctl.c', ('ccci_fsm_ioctl',))):
            for name in names:
                match = re.search(r'\b' + name + r'\([^;]+?\n\{', after[base + path], re.S)
                self.assertIsNotNone(match)
                entry = after[base + path][match.end():]
                guard = entry[:entry.index('#endif')]
                self.assertIn('#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)', guard)
                self.assertIn('return -EOPNOTSUPP;', guard)
                self.assertNotIn('registration_complete()', guard)

    def test_no_commit_or_power_from_resource_probe(self):
        _, _, after = build(VENDOR)
        base = 'drivers/misc/mediatek/eccci/'
        platform = after[base + 'fsm/md_sys1_platform.c']
        probe = platform[platform.index('static int ccci_modem_probe('):]
        self.assertNotIn('ccci_tetris_register_prepared(', probe)
        self.assertIn('#if defined(CCCI_KMODULE_ENABLE) && !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)', probe)
        self.assertIn('#if defined(USING_PM_RUNTIME) && !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)', platform)
        self.assertIn('return PTR_ERR(clk_table[idx].clk_ref);', platform)
        self.assertIn('return PTR_ERR(md_cd_plat_val_ptr.spm_sleep_base);', platform)
        for name, text in after.items():
            if name.endswith('.c'):
                self.assertNotIn('ccci_tetris_register_prepared(', text)
        self.assertEqual(after[base + 'ccci_core.c'].count('return PTR_ERR(dev_class);'), 2)

    def test_actual_configured_port_kinds_checked(self):
        _, _, after = build(VENDOR)
        base = 'drivers/misc/mediatek/eccci/'
        import re
        kinds = set(re.findall(r'&(\w+_port_ops)', after[base + 'port/port_cfg.c']))
        self.assertEqual(kinds, {'char_port_ops', 'rpc_port_ops', 'ipc_port_ops',
            'smem_port_ops', 'net_port_ops', 'ctl_port_ops', 'sys_port_ops',
            'poller_port_ops', 'ccci_udc_port_ops'})
        proxy = (HERE / 'ports_prepare.h').read_text()
        self.assertIn('proxy->ports[i].ops->init(&proxy->ports[i])', proxy)
        for filename in ('port_ctlmsg.c', 'port_sysmsg.c', 'port_udc.c', 'port_ipc.c', 'port_rpc.c'):
            self.assertIn('ccci_tetris_port_worker(port,', after[base + 'port/' + filename])

    def test_close_and_stop_not_physical_proof(self):
        _, _, after = build(VENDOR)
        base = 'drivers/misc/mediatek/eccci/'
        proxy = after[base + 'port/port_proxy.c']
        close = proxy[proxy.index('int port_dev_close('):proxy.index('ssize_t port_dev_read(')]
        self.assertGreater(close.rindex('atomic_dec(&port->usage_cnt)'), close.index('port_user_unregister(port)'))
        fsm = after[base + 'fsm/ccci_fsm.c']
        stop = fsm[fsm.index('static void fsm_routine_stop('):fsm.index('static void fsm_routine_wdt(')]
        self.assertLess(stop.index('ccci_tetris_registration_quarantine(-EOPNOTSUPP)'),
                        stop.index('ccci_md_pre_stop('))


if __name__ == '__main__':
    unittest.main()
