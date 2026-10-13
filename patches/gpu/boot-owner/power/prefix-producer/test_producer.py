#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exact-object/static patch checks only; required fixtures, no compilation."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import audit_producer as audit
import generate_report as report
import read_initial


def selected_source(source, enabled):
    """Select only this file's CONFIG_IS_ENABLED branches, without invoking cpp."""
    logical = source.replace('\\\n', '')
    stack, output, active = [], [], True
    for line in logical.splitlines():
        if line.startswith('#ifdef ') or line.startswith('#ifndef '):
            name = line.split()[1]
            branch = name in enabled if line.startswith('#ifdef ') else name not in enabled
            stack.append((active, branch))
            active = active and branch
        elif line.startswith('#if '):
            expression = line[4:]
            names = re.findall(r'CONFIG_IS_ENABLED\((\w+)\)', expression)
            remainder = re.sub(r'CONFIG_IS_ENABLED\(\w+\)', '', expression)
            if not names or remainder.strip().replace('||', '').strip():
                raise ValueError('unsupported conditional in static selector')
            branch = any(name in enabled for name in names)
            stack.append((active, branch))
            active = active and branch
        elif line == '#else':
            parent, branch = stack[-1]
            active = parent and not branch
        elif line.startswith('#endif'):
            active = stack.pop()[0]
        elif active:
            output.append(line)
    if stack:
        raise ValueError('unclosed conditional')
    return '\n'.join(output)


class Producer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audit_gpueb_b41 import signed_lk, pinned_atf, read_bounded
        cls.sources = report.checked_sources(cls.args.tree)
        cls.original = cls.sources[report.SOURCE]
        cls.integrated = report.integrate(cls.original)
        cls.raw_lk = read_bounded(cls.args.lk, 8 * 1024 * 1024)
        cls.lk = signed_lk(cls.raw_lk)
        cls.atf = pinned_atf(read_bounded(cls.args.atf, 900752))
        cls.evidence = audit.trace(cls.lk)
        cls.evidence['nos'] = audit.check_nos(cls.args.device_tree)
        cls.evidence['atf'] = audit.trace_atf(cls.atf)

    def test_generated_patch(self):
        self.assertEqual(report.generated(self.args.tree), (report.HERE / 'initial-report.patch').read_text())

    def test_patch_application_exact_and_non_destructive(self):
        with tempfile.TemporaryDirectory(prefix='gpueb-prefix-report-') as tmp:
            root = Path(tmp)
            target = root / report.SOURCE
            target.parent.mkdir(parents=True)
            target.write_text(self.original)
            patch = report.HERE / 'initial-report.patch'
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--whitespace=error-all', str(patch)], check=True)
            self.assertEqual(target.read_text(), self.original)
            subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True)
            self.assertEqual(target.read_text(), self.integrated)
            subprocess.run(['git', '-C', str(root), 'apply', '--reverse', str(patch)], check=True)
            self.assertEqual(target.read_text(), self.original)

    def test_one_read_and_exact_field_reporting(self):
        helper = (report.HERE / 'report.inc').read_text()
        self.assertEqual(helper.count('readl('), 1)
        self.assertIn('readl((const volatile void *)0x1c001eb4UL)', helper)
        for field in ('(raw >> 30) & 3U', '(raw >> 12) & 1U', '(raw >> 13) & 1U'):
            self.assertIn(field, helper)
        for forbidden in ('writel(', 'poll_timeout', 'while (', 'arm_smccc',
                          'ioremap(', 'regulator_', 'clk_prepare'):
            self.assertNotIn(forbidden, helper)
        self.assertNotRegex(helper, r'\bmap_sysmem\(')

    def test_report_before_either_gpu_load_without_activation(self):
        source = self.integrated
        startup = source.index('\tgpueb_initial_power_capture();')
        self.assertGreater(startup, source.index('int board_late_init(void)'))
        self.assertLess(startup, source.index('if (mode != TETRIS_REBOOT_MODE_BOOTLOADER)'))
        call = source.index('\tret = gpueb_initial_report_publish(images);')
        preparation = source.index('void board_prep_linux(')
        self.assertGreater(call, source.index('ret = tetris_linux_fdt_prepare(images);', preparation))
        self.assertLess(call, source.index('\t\ttetris_scp_prepare_diagnostic(images, fdt);'))
        self.assertEqual(source.count('gpueb_initial_power_capture();'), 1)

    def test_configuration_selection_retention_only_and_transform_only(self):
        choices = ('TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC', 'TETRIS_GPUEB_TRANSFORM_DIAGNOSTIC')
        for enabled in (set(), {choices[0]}, {choices[1]}, set(choices)):
            text = selected_source(self.integrated, enabled)
            self.assertEqual(text.count('static void gpueb_initial_power_capture('), bool(enabled))
            self.assertEqual(text.count('\tgpueb_initial_power_capture();'), bool(enabled))
            self.assertEqual(text.count('\tret = gpueb_initial_report_publish(images);'), bool(enabled))

    def test_authentication_wipe_and_error_paths_unchanged(self):
        helper = (report.HERE / 'report.inc').read_text().rstrip() + '\n\n'
        guard = ('#if CONFIG_IS_ENABLED(TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC) || \\\n'
                 '\tCONFIG_IS_ENABLED(TETRIS_GPUEB_TRANSFORM_DIAGNOSTIC)\n')
        capture = guard + '\tgpueb_initial_power_capture();\n#endif\n'
        publish = (guard + '\tret = gpueb_initial_report_publish(images);\n\tif (ret)\n'
                   '\t\tprintf("Tetris: GPUEB initial report error=%d (observation only)\\n", ret);\n#endif\n')
        self.assertEqual(self.integrated.replace(helper, '', 1).replace(capture, '', 1).replace(publish, '', 1), self.original)

    def test_real_bounded_clone_and_atomic_commit(self):
        helper = (report.HERE / 'report.inc').read_text()
        publish = helper.split('static int gpueb_initial_report_publish(', 1)[1]
        self.assertLess(publish.index('tetris_linux_fdt_prepare(&candidate)'), publish.index('gpueb_initial_write(final'))
        self.assertLess(publish.index('fdt_check_full(final, capacity)'), publish.index('*images = candidate'))
        self.assertLess(publish.index('flush_dcache_range('), publish.index('*images = candidate'))
        self.assertIn('lmb_free(address, capacity, LMB_NOOVERWRITE | LMB_NONOTIFY)', publish)
        self.assertIn('tetris_linux_fdt_sync(images)', publish)
        self.assertIn('node, 0, ret)', publish)
        self.assertEqual(publish.count('return ret;'), 1)

    def test_stale_report_erased_version_last_and_no_absent_raw(self):
        helper = (report.HERE / 'report.inc').read_text()
        self.assertLess(helper.index('gpueb-initial-report-version'), helper.index('gpueb-initial-spm-raw'))
        write = helper.split('static int gpueb_initial_write(', 1)[1].split('static int gpueb_initial_report_publish', 1)[0]
        self.assertLess(write.index('gpueb_initial_clear('), write.index('fdt_setprop_u32('))
        self.assertIn('if (!ret && stage == 1 && !error)', write)
        self.assertGreater(write.index('gpueb_initial_properties[0], 1'), write.index('gpueb_initial_properties[6]'))
        capture = helper.split('static void gpueb_initial_power_capture(', 1)[1].split('static int gpueb_initial_clear', 1)[0]
        self.assertLess(capture.index('readl('), capture.index('gpueb_initial_error = 0'))
        self.assertLess(capture.index('readl('), capture.index('gpueb_initial_stage = 1'))

    def test_wrong_preimage_not_adopted(self):
        for source in ('other source', self.original + self.original):
            with self.assertRaisesRegex(ValueError, 'unique'):
                report.integrate(source)
        real = report.git_source
        for path in report.PINS['uboot_sources']:
            def changed(tree, revision, name):
                data = real(tree, revision, name)
                return data + b'foreign' if name == path else data
            with patch.object(report, 'git_source', changed):
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    report.checked_sources(self.args.tree)

    def test_full_signed_inventory_target_reads_not_producer(self):
        inventory = self.evidence['address_inventory']
        target = inventory['target_candidates']
        self.assertEqual({item['offset'] for item in target}, {'0x1e194', '0x1e42c', '0x1eb74', '0x1ebc8'})
        self.assertFalse(any(item['write'] for item in target))
        self.assertTrue(any(item['write'] for item in inventory['constant_spm_memory_candidates']))
        self.assertIn('no indirect/dynamic writer exclusion', inventory['scope'])
        self.assertEqual(self.evidence['direct_gpueb_loader_refs'], ['0xed94'])
        self.assertTrue(all(not hits for hits in self.evidence['target_literals'].values()))

    def test_static_inventory_can_detect_target_write(self):
        # Change only the load opcode into a store in this synthetic decode input.
        snippet = self.lk[0x1eb68:0x1eb78]
        changed = snippet[:-4] + struct.pack('<I', 0xb9000108)  # str w8,[x8]
        target = audit.constant_memory_inventory(changed)['target_candidates']
        self.assertEqual(len(target), 1)
        self.assertTrue(target[0]['write'])
        self.assertEqual(target[0]['address'], '0x1c001eb4')

    def test_unknown_pointer_does_not_become_zero_or_proven(self):
        changed = struct.pack('<I', 0xb9000108)  # Unknown incoming x8.
        self.assertEqual(audit.constant_memory_inventory(changed)['target_candidates'], [])

    def test_payload_drift_rejected_before_disassembly(self):
        changed = bytearray(self.lk)
        changed[0x1ebe0] ^= 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            audit.trace(changed)
        changed = bytearray(self.atf)
        changed[0x19988] ^= 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            audit.trace_atf(changed)

    def test_signed_container_drift_rejected(self):
        from audit_gpueb_b41 import signed_lk
        changed = bytearray(self.raw_lk)
        changed[512 + 0xed94] ^= 1
        with self.assertRaises(ValueError):
            signed_lk(changed)

    def test_exact_evidence_generated(self):
        self.assertEqual(json.loads((report.HERE / 'SOURCE-EVIDENCE.json').read_text()), self.evidence)

    def test_actual_secure_boundary_not_a_grant_or_bit13_claim(self):
        boundary = self.evidence['preceding_spm_boundary']
        self.assertEqual(boundary['smc'], '0x33438 -> 0x188dc')
        self.assertEqual(boundary['x0'], '0x82000410')
        self.assertIn('NOT established', boundary['meaning'])
        atf = self.evidence['atf']
        self.assertIn('0x19f00', atf['resolved_platform_callbacks']['0x3108c'])
        self.assertIn('not a MFG0 writer', atf['conditional_spm_event'])
        self.assertIn('not independently authenticated', atf['provenance'])
        self.assertIn('firmware-only origin is NOT established', atf['limits'])


class LinuxReader(unittest.TestCase):
    def fixture(self, root, raw=0xc0002000, stage=1, error=0):
        values = {'report-version': 1, 'report-stage': stage, 'report-error': error}
        if stage == 1:
            values.update({'spm-raw': raw, 'spm-ack': (raw >> 30) & 3,
                           'spm-pdn-ack12': (raw >> 12) & 1, 'spm-sleep-b-ack13': (raw >> 13) & 1})
        for name, value in values.items():
            (root / (read_initial.PREFIX + name)).write_bytes((value & 0xffffffff).to_bytes(4, 'big'))

    def test_actual_word_fields_and_no_power_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            result = read_initial.read_report(root)
            self.assertEqual((result['raw'], result['ack'], result['pdn_ack12'], result['sleep_b_ack13']),
                             ('c0002000', 3, 0, 1))
            self.assertIn('not authenticated power ownership', result['meaning'])
            self.assertNotIn('ready', result)

    def test_real_zero_word_is_not_a_missing_fixture_or_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, raw=0)
            self.assertEqual(read_initial.read_report(root)['raw'], '00000000')

    def test_actual_signed_failure_without_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, stage=0, error=-12)
            result = read_initial.read_report(root)
            self.assertEqual(result['error'], -12)
            self.assertNotIn('raw', result)

    def test_absent_or_malformed_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                read_initial.read_report(root)
            self.fixture(root)
            prop = root / (read_initial.PREFIX + 'spm-raw')
            for data in (b'', b'\x00', b'\0' * 8):
                prop.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'one big-endian'):
                    read_initial.read_report(root)

    def test_disagreement_and_stale_error_raw_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / (read_initial.PREFIX + 'spm-ack')).write_bytes((0).to_bytes(4, 'big'))
            with self.assertRaisesRegex(ValueError, 'disagree'):
                read_initial.read_report(root)
            self.fixture(root, stage=0, error=-3)
            with self.assertRaisesRegex(ValueError, 'stale/raw'):
                read_initial.read_report(root)

    def test_unknown_stage_or_inconsistent_error_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for stage, error in ((0, 0), (1, -3), (2, 0)):
                self.fixture(root, stage=stage, error=error)
                with self.assertRaises(ValueError):
                    read_initial.read_report(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, required=True)
    parser.add_argument('--lk', type=Path, required=True)
    parser.add_argument('--atf', type=Path, required=True)
    parser.add_argument('--device-tree', type=Path, required=True)
    Producer.args, remaining = parser.parse_known_args()
    unittest.main(argv=[__file__] + remaining)
