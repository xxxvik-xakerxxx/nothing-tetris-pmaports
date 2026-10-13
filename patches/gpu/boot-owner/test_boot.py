#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Real-input source and patch-application tests; no C execution or hardware."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from audit_boot import audit, trace_lk, trace_primary, signed_lk, read_bounded, read_private_snapshot
from generate_join_patch import HERE, ROOT, render
sys.path.insert(0, str(HERE.parent / 'flat-handoff-draft'))
from test_ram_admission import function, without_comments, compact

INPUTS = None


def check_join(sources):
    flat = sources['patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c']
    sram = sources['patches/gpu/sram-owner/mt6878-gpueb-sram.c']
    reset = sources['patches/gpu/reset-owner-draft/mt6878-gpueb-reset.c']
    loans = function(flat, 'tetris_gpueb_flat_use_primary')
    for guard in ('input->dev.driver != &flat_driver.driver',
                  '!analysis || !analysis->snapshot || !analysis->reservation',
                  'analysis->metadata.profile_id != 1 || analysis->size != TETRIS_FLAT_BYTES'):
        if guard not in loans:
            raise ValueError('missing input guard: ' + guard)
    if loans.index('analysis->metadata.profile_id') > loans.index('consume(analysis->snapshot'):
        raise ValueError('profile admission after loan')
    body = function(reset, 'mt6878_gpueb_reset_primary_transaction')
    for term in ('scope->sram != sram || !scope->dispatch_owner',
                 'scope->dispatch_owner->scope != scope',
                 'scope->dispatch_owner->parent != scope->parent',
                 'scope->reset_written || scope->dispatch_used || scope->dispatch_active',
                 'dispatch_identity(scope)', 'mt6878_gpueb_sram_check_parent(sram, scope->parent)',
                 '!irq_data || !irqd_irq_disabled(irq_data)',
                 'active = pm_runtime_get_if_in_use(scope->parent)', 'active <= 0',
                 'ret = mt6878_gpueb_sram_unknown_start(sram)',
                 'scope->reset_written = true;', 'writel(0, scope->registers + 0x600)',
                 'readl(scope->registers + 0x600)', 'ret = latch(scope, ret)'):
        if term not in body:
            raise ValueError('missing real owner operation: ' + term)
    ordered = ('scope->sram != sram', 'mt6878_gpueb_reset_drain_irq(scope)',
               'mt6878_gpueb_sram_unknown_start(sram)', 'scope->reset_written = true',
               'writel(0,', 'readl(scope->registers + 0x600)',
               'ret = install(scope->gpr, scope->mbox, data)')
    positions = [body.index(term) for term in ordered]
    if positions != sorted(positions):
        raise ValueError('reset/upload/quarantine ordering')
    image = function(sram, 'install_quarantined_primary')
    for term in ('gpr->sram != sram || mbox->sram != sram',
                 'gpr->type != GPUEB_WINDOW_GPR || mbox->type != GPUEB_WINDOW_MBOX',
                 'input->bytes != 156064', 'sram->core.phase != GPUEB_SRAM_QUARANTINED',
                 'sram->core.clients !=', 'memset_io(sram->mapping, 0, GPUEB_SRAM_SIZE)',
                 'offset < input->bytes', 'get_unaligned_le32(input->primary + offset)',
                 'offset < GPUEB_SRAM_SIZE', 'readl(sram->mapping + offset) != expected'):
        if term not in image:
            raise ValueError('missing bounded image operation: ' + term)
    if image.index('memset_io(') > image.index('writel('):
        raise ValueError('copy before initialization')
    if compact(function(sram, 'install_owned_snapshot')).find('input->primary = NULL;') < 0:
        raise ValueError('borrowed snapshot retained')
    entry = compact(function(sram, 'mt6878_gpueb_sram_install_retained'))
    if 'tetris_gpueb_flat_use_primary(source, install_owned_snapshot, &input)' not in entry:
        raise ValueError('canonical input loan bypassed')
    if 'mt6878_gpueb_reset_primary_transaction(input->reset, input->sram,' not in compact(
            function(sram, 'install_owned_snapshot')):
        raise ValueError('real reset owner bypassed')
    added = '\n'.join((HERE / name).read_text() for name in
                      ('flat-input.inc', 'sram-install.inc', 'reset-install.inc'))
    if re.search(r'\b(?:enable_irq|rproc_boot|request_mem_region|ioremap|arm_smccc_smc|'
                 r'pm_runtime_resume_and_get|regulator_enable|clk_prepare_enable)\s*\(',
                 without_comments(added)):
        raise ValueError('new owner or activation operation')


class BootContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = read_private_snapshot(INPUTS.snapshot)
        cls.lk_container = read_bounded(INPUTS.lk, 8 * 1024 * 1024)
        cls.gpueb = read_bounded(INPUTS.gpueb, 2 * 1024 * 1024)
        cls.report = audit(cls.snapshot, cls.lk_container, cls.gpueb,
                           INPUTS.device_tree, INPUTS.module_tree, INPUTS.linux_tree)
        cls.code = signed_lk(cls.lk_container)

    def test_actual_in_primary_bss_and_stack_fill(self):
        fills = self.report['primary']['cold_fills']
        self.assertEqual((fills[0]['start'], fills[0]['end_exclusive'], fills[0]['bytes']),
                         (0x1b538, 0x2619c, 44132))
        self.assertLessEqual(fills[0]['end_exclusive'], len(self.snapshot))
        self.assertEqual(fills[2]['word'], 0xabababab)
        self.assertIn('assumes callees return', self.report['primary']['cold_fill_scope'])

    def test_stock_overread_is_not_new_upload_dependency(self):
        self.assertEqual(self.report['primary']['stock_copy_bytes'], 258744)
        self.assertEqual(self.report['primary']['signed_bytes'], 156064)
        self.assertNotIn('stock overread', ' '.join(self.report['start_boundary']).lower())
        self.assertIn('not a requirement to reproduce', self.report['stock_overread_policy'])

    def test_gpr0_and_gpr6_are_distinct_from_linux_shared_memory(self):
        self.assertEqual(self.report['lk']['gpr0']['prefix_bytes'], 24)
        self.assertEqual(self.report['lk']['gpr6']['reservation_bytes'], 0x600000)
        self.assertEqual(self.report['lk']['gpr6']['emi_region'], 12)
        self.assertEqual(self.report['lk']['linux_shared_dram']['reservation_bytes'], 0x180000)
        self.assertEqual(self.report['lk']['linux_shared_dram']['emi_region'], 31)
        self.assertEqual(self.report['lk']['linux_shared_dram']['excess_over_stock_reservation'], 0x4000)
        self.assertEqual(self.report['primary']['gpr6_consumer']['size_argument'], 0x400000)
        self.assertIn('opaque', self.report['primary']['gpr6_consumer']['boundary'])

    def test_wrong_primary_and_lk_instruction_mutations_rejected(self):
        for offset in (0, 0x100b8, 0x310, 156063):
            changed = bytearray(self.snapshot)
            changed[offset] ^= 1
            with self.subTest(primary=offset), self.assertRaises(ValueError):
                trace_primary(changed)
        for offset in (0x1ed8c, 0x1ee38, 0x1ee44, 0x2987c, 0x16ec0):
            changed = bytearray(self.code)
            changed[offset] ^= 1
            with self.subTest(lk=offset), self.assertRaises(ValueError):
                trace_lk(changed)

    def test_wrong_matching_container_is_rejected(self):
        changed = bytearray(self.gpueb)
        changed[512] ^= 1
        with self.assertRaises(ValueError):
            audit(self.snapshot, self.lk_container, changed,
                  INPUTS.device_tree, INPUTS.module_tree, INPUTS.linux_tree)


class OwnerJoin(unittest.TestCase):
    def test_deterministic_delta_applies_to_real_owners_without_fuzz(self):
        patch, sources = render()
        self.assertEqual(patch, render()[0])
        self.assertEqual(patch, (HERE / 'owner-join.patch').read_text())
        with tempfile.TemporaryDirectory(prefix='gpueb-boot-owner-') as directory:
            for path in sources:
                target = Path(directory) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((ROOT / path).read_text())
            result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(HERE / 'owner-join.patch')],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('offset', result.stdout)
            for path, expected in sources.items():
                self.assertEqual((Path(directory) / path).read_text(), expected)

    def test_actual_owner_helpers_are_unchanged(self):
        _, sources = render()
        paths = {
            'patches/gpu/sram-owner/mt6878-gpueb-sram.c':
                ('mt6878_gpueb_sram_create', 'mt6878_gpueb_sram_destroy',
                 'mt6878_gpueb_sram_read_transaction', 'mt6878_gpueb_sram_send_transaction'),
            'patches/gpu/reset-owner-draft/mt6878-gpueb-reset.c':
                ('mt6878_gpueb_reset_prepare', 'mt6878_gpueb_reset_hold',
                 'mt6878_gpueb_reset_destroy', 'mt6878_gpueb_reset_trysend'),
            'patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c': ('flat_probe', 'flat_read'),
        }
        for path, functions in paths.items():
            for name in functions:
                self.assertEqual(function((ROOT / path).read_text(), name), function(sources[path], name))

    def test_canonical_input_and_real_owner_guards(self):
        check_join(render()[1])

    def test_guard_removal_mutants_rejected(self):
        sources = render()[1]
        mutations = {
            'patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c':
                ('input->dev.driver != &flat_driver.driver', 'analysis->metadata.profile_id != 1'),
            'patches/gpu/sram-owner/mt6878-gpueb-sram.c':
                ('input->bytes != 156064', 'sram->core.phase != GPUEB_SRAM_QUARANTINED',
                 'readl(sram->mapping + offset) != expected'),
            'patches/gpu/reset-owner-draft/mt6878-gpueb-reset.c':
                ('scope->dispatch_owner->scope != scope', '!irqd_irq_disabled(irq_data)',
                 'ret = mt6878_gpueb_sram_unknown_start(sram)', 'scope->reset_written = true;'),
        }
        for path, guards in mutations.items():
            for guard in guards:
                altered = dict(sources)
                name = ('mt6878_gpueb_reset_primary_transaction' if '/reset-owner-' in path else
                        'install_quarantined_primary' if '/sram-owner/' in path else
                        'tetris_gpueb_flat_use_primary')
                body = function(sources[path], name)
                self.assertIn(guard, body)
                # function() strips comments; replace inside the actual function's source span.
                marker = sources[path].index('\n' + ('int ' if name != 'install_quarantined_primary' else
                                                     'static int ') + name + '(')
                altered[path] = sources[path][:marker] + sources[path][marker:].replace(guard, '0', 1)
                with self.subTest(guard=guard), self.assertRaises(ValueError):
                    check_join(altered)

    def test_no_start_ready_or_independent_resource_owner(self):
        for name in ('flat-input.inc', 'reset-install.inc', 'sram-install.inc'):
            code = without_comments((HERE / name).read_text())
            self.assertNotRegex(code, r'\bbool\b|0x3f00000b|0x55667788|0x5a5a5a5a')
            self.assertNotRegex(code, r'\b(?:enable_irq|rproc_boot|ioremap|request_mem_region)\s*\(')
        sram = (HERE / 'sram-install.inc').read_text()
        self.assertNotIn('memcpy_toio', sram)
        self.assertNotIn('+ 24', without_comments(sram))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('snapshot', 'lk', 'gpueb', 'device-tree', 'module-tree', 'linux-tree'):
        parser.add_argument('--' + name, type=Path, required=True)
    INPUTS, remaining = parser.parse_known_args()
    unittest.main(argv=[sys.argv[0], *remaining])
