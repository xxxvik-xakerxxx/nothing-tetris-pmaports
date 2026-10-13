#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source/command and optional authenticated-input tests; no C or RV execution."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci_dram import HERE, PINS, API, NAMES, UNIT, source_check, native_command, blob_id, build, stage
import ci_join

INPUTS = None


class Static(unittest.TestCase):
    def test_actual_source_and_api(self):
        digests = source_check()
        self.assertEqual(len(digests), 4)
        source = (HERE / 'mt6878-gpueb-dram.c').read_text()
        for name in API:
            self.assertIn(name, source)
        self.assertNotIn('__GFP_ZERO', source)
        self.assertNotIn('alloc_pages_exact(', source)

    def test_real_allocation_and_loan_ordering(self):
        source = (HERE / 'mt6878-gpueb-dram.c').read_text()
        self.assertLess(source.index('get_device(parent)'), source.index('cma_alloc(dram->area'))
        self.assertLess(source.index('cma_alloc(dram->area'), source.index('page_to_phys(dram->pages)'))
        self.assertLess(source.index('ret = validate_allocation(dram->physical)'), source.rindex('*result = dram;'))
        destroy = source[source.index('int mt6878_gpueb_dram_destroy'):]
        self.assertLess(destroy.index('if (dram->loan)'), destroy.index('cma_release('))
        self.assertLess(destroy.index('if (ret)'), destroy.index('put_device(dram->parent)'))

    def test_physical_bounds_and_exact_shift(self):
        source = (HERE / 'mt6878-gpueb-dram.c').read_text()
        for term in ('0x600000UL', '0x10000UL', '0x40000000ULL', '0x80000000ULL',
                     'physical > GPUEB_DRAM_LIMIT - GPUEB_DRAM_BYTES',
                     '(physical & (GPUEB_DRAM_ALIGN - 1))', '*word = dram->physical >> 12',
                     'page_to_phys(dram->pages) != dram->physical ? -ESTALE'):
            self.assertIn(term, source)

    def test_ci_faults_cover_actual_allocation_history(self):
        source = (HERE / 'test-dram.c').read_text()
        for term in ('allocation_failure = 1', 'release_failure = 1', 'metadata_failure = 1',
                     'absent_area = 1', '0x7fa10000ULL', '0x7fa00000ULL',
                     'mt6878_gpueb_dram_destroy(held) == -EBUSY',
                     'mt6878_gpueb_dram_destroy(held) == -EIO',
                     'mt6878_gpueb_dram_candidate_gpr6(loan, &word) == -ESTALE',
                     'selected_area = &foreign_area'):
            self.assertIn(term, source)

    def test_constructor_retains_accessible_failed_owner(self):
        source = (HERE / 'mt6878-gpueb-dram.c').read_text()
        self.assertIn('if (!parent || !result || *result)', source)
        self.assertIn('dram->first_error = ret;\n\t\t\t*result = dram;\n\t\t\treturn -EIO;', source)
        acquire = source[source.index('mt6878_gpueb_dram_acquire('):
                         source.index('int mt6878_gpueb_dram_candidate_gpr6(')]
        self.assertLess(acquire.index('if (dram->first_error)'), acquire.index('kzalloc('))
        fixture = (HERE / 'test-dram.c').read_text()
        self.assertIn('mt6878_gpueb_dram_create(&parent, &held) == -EIO && held', fixture)
        self.assertIn('held->first_error == -ERANGE && owned && parent.refs == 1', fixture)
        self.assertIn('mt6878_gpueb_dram_destroy(held) == -EIO && held->first_error == -ERANGE', fixture)

    def test_kernel_and_host_headers_are_separate(self):
        source = (HERE / 'mt6878-gpueb-dram.c').read_text()
        self.assertIn('#ifdef GPUEB_DRAM_HOST_TEST\n#include "dram-host.h"\n#else', source)
        self.assertIn('#include <linux/cma.h>', source)
        self.assertIn('#include <linux/dma-map-ops.h>', source)
        command = list(map(str, native_command(HERE, HERE / 'never-created')))
        self.assertIn('-DGPUEB_DRAM_HOST_TEST', command)
        self.assertIn('-fsanitize=address,undefined', command)

    def test_local_build_guard_precedes_all_writes(self):
        # No generated success manifest, executable, or mocked compiler result.
        for ci, github in (('', ''), ('true', ''), ('', 'true')):
            with patch.dict(os.environ, CI=ci, GITHUB_ACTIONS=github), \
                    patch('subprocess.run', side_effect=AssertionError('no local process')):
                with self.assertRaisesRegex(ValueError, 'CI-only'):
                    build(None)

    def test_linux_blob_pin_shape(self):
        self.assertEqual(PINS['linux'], 'd84b264a54a37611f2f46bc19363cb9b41606205')
        self.assertEqual(len(PINS['linux_blobs']), 6)
        self.assertEqual(blob_id(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')
        comparison = PINS['comparison_only_cache_header']
        self.assertIn('NOT the GPUEB', comparison['scope'])
        self.assertIn('0x400f', comparison['cache_encoding_expression'])

    def test_private_stage_joins_canonical_sources_without_changing_inputs(self):
        # Parent stage validation has its own twelve source-only tests. Here we
        # isolate this wrapper's copy/Kbuild behavior, never emulate a build or
        # emit a successful compilation manifest.
        files = ci_join.checked_sources()
        originals = {name: ci_join.sha(HERE / name) for name in NAMES}
        with tempfile.TemporaryDirectory(prefix='gpueb-dram-stage-static-') as directory:
            base = Path(directory)
            kernel, output, work = base / 'kernel', base / 'output', base / 'work'
            kernel.mkdir(); output.mkdir()
            config = output / '.config'
            config.write_text('# Orchestration fixture; not a compilable kernel.\n')
            before = config.read_bytes()

            def parent_stage(k, o, w, baseline):
                self.assertEqual((k, o, w), (kernel, output, work))
                variant = w / 'source'
                variant.mkdir(parents=True)
                for name, text in files.items():
                    target = variant / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text)
                (variant / 'Makefile').write_text('obj-y += ' + ' '.join(
                    name + '.o' for name in ci_join.TRANSLATION_UNITS) + '\n')
                (w / 'output').mkdir()
                (w / 'output/.config').write_bytes(before)
                return variant, {'.config': ci_join.sha(config)}

            with patch('ci_dram.validate_kernel') as validate, \
                    patch('ci_dram.ci_join.stage', side_effect=parent_stage) as parent, \
                    patch('subprocess.run', side_effect=AssertionError('no compiler/process')):
                variant, inputs, digests = stage(kernel, output, work, base / 'not-build-evidence')
            validate.assert_called_once_with(kernel, output)
            parent.assert_called_once()
            self.assertEqual(digests, originals)
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(inputs['.config'], ci_join.sha(config))
            for name, text in files.items():
                self.assertEqual((variant / name).read_text(), text)
            for name in NAMES:
                self.assertEqual((variant / name).read_bytes(), (HERE / name).read_bytes())
            self.assertIn('obj-y += ' + UNIT + '.o', (variant / 'Makefile').read_text())
            command = list(map(str, ci_join.kernel_command(kernel, work / 'output', variant))) + [UNIT + '.o']
            self.assertEqual(command[-5:], [name + '.o' for name in (*ci_join.TRANSLATION_UNITS, UNIT)])
            self.assertFalse(any('GPUEB_DRAM_HOST_TEST' in argument for argument in command))
            self.assertFalse(list(variant.glob('*.o')))
            self.assertFalse(list(variant.glob('*.ko')))
        self.assertEqual(originals, {name: ci_join.sha(HERE / name) for name in NAMES})

    def test_bad_prepared_dependency_stops_before_staging(self):
        with patch('ci_dram.validate_kernel', side_effect=ValueError('pinned API/config drift')), \
                patch('ci_dram.ci_join.stage') as parent:
            with self.assertRaisesRegex(ValueError, 'drift'):
                stage(Path('/not-used'), Path('/not-used'), Path('/not-created'), Path('/not-used'))
        parent.assert_not_called()


@unittest.skipUnless(INPUTS, 'exact authenticated inputs not supplied')
class RealInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from trace import refine, audit, signed_lk, read_private_snapshot, read_bounded
        cls.primary = read_private_snapshot(INPUTS.snapshot)
        container = read_bounded(INPUTS.lk, 8 * 1024 * 1024)
        audit(cls.primary, container, read_bounded(INPUTS.gpueb, 2 * 1024 * 1024),
              INPUTS.device_tree, INPUTS.module_tree, INPUTS.linux_tree)
        cls.lk = signed_lk(container)
        cls.report = refine(cls.primary, cls.lk)

    def test_no_guessed_cache_or_initial_table_semantics(self):
        report = self.report
        self.assertEqual([word['opcode'] for word in report['rv33_words']], [0x33, 0x33])
        self.assertIn('exact OP-0x33 effects', report['gpr6']['not_proven'])
        self.assertEqual(report['gpr6']['zero_fill_candidate']['length'], 0x400000)
        self.assertIn('NOT decoded', report['gpr6']['zero_fill_candidate']['boundary'])

    def test_staging_prefix_is_not_signed_primary_header(self):
        header = self.report['gpr0']['different_signed_primary_header']
        self.assertEqual(header['words'], [0x0ac0006f, 0, 0, 0, 0, 0])
        self.assertEqual(header['copy_count_field'], 16)
        self.assertEqual(header['copy_count'], 0)
        self.assertEqual(self.report['gpr0']['data_offset'], 512)
        self.assertIn('none established', self.report['gpr0']['prefix']['producer'])

    def test_unknown_words_and_reader_mutations_rejected(self):
        from trace import refine
        for offset in (0xfe9a, 0xfec2, 0x7a4e, 0x1e04, 0x1e54):
            mutated = bytearray(self.primary)
            mutated[offset] ^= 1
            with self.subTest(primary=offset), self.assertRaises(ValueError):
                refine(mutated, self.lk)
        for offset in (0x75024, 0x75030, 0x75180, 0x7db50):
            mutated = bytearray(self.lk)
            mutated[offset] ^= 1
            with self.subTest(lk=offset), self.assertRaises(ValueError):
                refine(self.primary, mutated)

    def test_real_linux_allocator_prototypes_and_not_module_exports(self):
        sources = {}
        for path, expected in PINS['linux_blobs'].items():
            data = subprocess.check_output(['git', '-C', str(INPUTS.linux_tree), 'show',
                                            PINS['linux'] + ':' + path],
                                           env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})
            self.assertEqual(blob_id(data), expected)
            sources[path] = data.decode()
        self.assertIn('struct page *cma_alloc(', sources['include/linux/cma.h'])
        self.assertIn('bool cma_release(', sources['include/linux/cma.h'])
        self.assertNotRegex(sources['mm/cma.c'], r'EXPORT_SYMBOL(?:_GPL)?\(cma_(?:alloc|release)\)')
        self.assertIn('get_order(size)', sources['mm/page_alloc.c'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('snapshot', 'lk', 'gpueb', 'device-tree', 'module-tree', 'linux-tree'):
        parser.add_argument('--' + name, type=Path)
    args, remaining = parser.parse_known_args()
    provided = [value is not None for value in vars(args).values()]
    if any(provided) and not all(provided):
        parser.error('supply all six actual inputs, or none for source-only checks')
    INPUTS = args if all(provided) else None
    # unittest decorators run before argument parsing; set skip status explicitly.
    RealInputs.__unittest_skip__ = INPUTS is None
    unittest.main(argv=[sys.argv[0], *remaining])
