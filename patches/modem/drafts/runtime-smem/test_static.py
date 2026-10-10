#!/usr/bin/env python3
"""Source/application tests only: never invoke a C compiler or phone API."""
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
import check_smem as check

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', ROOT.parent / 'android_kernel_device_modules_6.1_nothing_mt6878'))
UBOOT = Path(os.environ.get('TETRIS_UBOOT_TREE', ROOT.parent / 'u-boot-mt6878'))


class SourceTests(unittest.TestCase):
    def test_exact_source_model(self):
        self.assertEqual(check.generated_model(VENDOR, UBOOT, ROOT), (HERE / 'source_model.h').read_text())

    def test_generation_deterministic(self):
        self.assertEqual(check.generated_model(VENDOR, UBOOT, ROOT), check.generated_model(VENDOR, UBOOT, ROOT))
        self.assertEqual(check.patch_text(), check.patch_text())

    def test_review_manifest(self):
        names = set()
        for line in (HERE / 'REVIEW.sha256').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertNotIn(name, names)
            names.add(name)
            self.assertEqual(digest, hashlib.sha256((HERE / name).read_bytes()).hexdigest())
        self.assertEqual(len(names), 10)

    def test_exact_new_file_patch(self):
        patch = check.patch_text()
        self.assertEqual(patch, (HERE / 'runtime-smem.patch.vendor').read_text())
        destinations = re.findall(r'^\+\+\+ b/(.*)$', patch, re.M)
        self.assertEqual(destinations, [check.DESTINATION + name for name in sorted(check.PRODUCTION)])
        self.assertNotIn('\n--- a/', patch, 'must not modify existing/shipping sources')
        with tempfile.TemporaryDirectory(prefix='smem-new-files-') as temporary:
            subprocess.run(['git', 'apply', '--check', '-'], input=patch, text=True, cwd=temporary, check=True)
            subprocess.run(['git', 'apply', '-'], input=patch, text=True, cwd=temporary, check=True)
            for name in check.PRODUCTION:
                self.assertEqual((Path(temporary) / check.DESTINATION / name).read_bytes(), (HERE / name).read_bytes())

    def test_exact_complete_stack(self):
        check.check_stack(VENDOR, UBOOT)

    def test_native_only_ci(self):
        with mock.patch.dict(os.environ, {'CI': 'false', 'GITHUB_ACTIONS': 'false'}), \
                mock.patch.object(check.subprocess, 'run') as run:
            with self.assertRaisesRegex(SystemExit, 'only allowed in GitHub CI'):
                check.native_ci(VENDOR, UBOOT, ROOT, Path('not-read'))
            run.assert_not_called()
        with mock.patch.dict(os.environ, {'CI': 'true', 'GITHUB_ACTIONS': 'false'}), \
                mock.patch.object(check.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                check.native_ci(VENDOR, UBOOT, ROOT, Path('not-read'))
            run.assert_not_called()

    def test_exact_native_types(self):
        types = check.native_types(VENDOR)
        self.assertIn('SMEM_USER_MD_POST_DUMP = 46', types)
        self.assertIn('SMEM_USER_CCB_DHL = SMEM_USER_CCB_START', types)
        for name in ('ccci_mem_region', 'ccci_smem_region', 'ccci_mem_layout'):
            self.assertEqual(types.count('struct ' + name + ' {'), 1)
        self.assertIn('SMF_NO_REMAP = (1 << 3)', types)

    def test_native_wraps_actual_bodies(self):
        fixture = (HERE / 'test_smem.c').read_text()
        self.assertIn('#include "smem.c"', fixture)
        self.assertIn('#include "arguments.c"', fixture)
        self.assertNotIn('#define tetris_smem_', fixture)
        self.assertIn('tetris_smem_publish_private(&slot, other) == -EEXIST', fixture)
        self.assertIn('unmap_order[0] == 2 && unmap_order[1] == 1', fixture)
        self.assertIn('tetris_smem_map_private(owner) == ret && map_calls == fail_map', fixture)
        runner = (HERE / 'check_smem.py').read_text()
        self.assertIn('for case in range(70)', runner)
        self.assertIn('for page in (4096, 65536)', runner)
        self.assertIn("'-Wall', '-Wextra', '-Werror'", runner)
        self.assertIn("'-fsanitize=address,undefined'", runner)
        self.assertIn("'-fno-sanitize-recover=undefined'", runner)
        self.assertIn('#include <asm-generic/errno.h>', runner)
        workflow = (ROOT / '.github/workflows/modem-metadata.yml').read_text()
        driver = workflow.split('  driver-objects:', 1)[1]
        self.assertLess(driver.index('linux-headers git'),
                        driver.index('uses: actions/checkout@v6'))

    def test_pure_arguments_no_mapping(self):
        text = (HERE / 'arguments.c').read_text()
        for forbidden in ('ioremap', 'memcpy_fromio', 'memcpy_toio', 'arm_smccc', 'ccci_md_register'):
            self.assertNotIn(forbidden, text)
        for key in ('nc_smem_layout_num', 'c_smem_layout_num', 'md1_chk', 'nc_smem_layout', 'c_smem_layout'):
            self.assertIn('"' + key + '"', text)
        self.assertIn('return ret;', text)
        self.assertIn('-EMSGSIZE', text)
        self.assertLess(text.index('nc_count > 36'), text.index('args = kzalloc'))
        self.assertIn('kfree(args);', text)

    def test_no_activation_or_claim(self):
        text = '\n'.join((HERE / name).read_text() for name in check.PRODUCTION)
        for forbidden in ('module_init(', 'EXPORT_SYMBOL', 'of_match_table', 'ccci_tetris_register_prepared(',
                          'arm_smccc_smc(', 'memset_io(', 'writel(', 'readl(', 'LK_LOAD_MD_EN'):
            self.assertNotIn(forbidden, text)
        public = (HERE / 'smem.h').read_text()
        self.assertNotIn('map_private', public)
        self.assertNotIn('publish_private', public)
        self.assertNotRegex(text, r'\bbool\s+(?:ready|authorized|permission|granted|authenticated)\b')

    def test_no_map_page_boundary_and_extents(self):
        text = (HERE / 'smem.c').read_text()
        self.assertIn('span->offset < row->offset + row->size', text)
        self.assertIn('row->offset < span->offset + span->size', text)
        self.assertIn('return -EADDRNOTAVAIL;', text)
        self.assertIn('last->size = end - last->offset;', text)
        self.assertNotIn('size += row->size', text)
        self.assertIn('plan.nc[17].offset + plan.nc[17].size', text)
        self.assertIn('plan.cache[4].offset + plan.cache[4].size', text)

    def test_mapping_then_publication_and_lifetime(self):
        text = (HERE / 'smem.c').read_text()
        mapper = text.split('int tetris_smem_map_private(', 1)[1].split('void tetris_smem_slot_init', 1)[0]
        self.assertLess(mapper.index('ioremap_wc('), mapper.index('populate_tables(owner);'))
        self.assertLess(mapper.index('populate_tables(owner);'), mapper.index('TETRIS_SMEM_MAPPED'))
        self.assertIn('ret = fail_private(owner, -ENOMEM)', mapper)
        self.assertNotIn('slot->owner', mapper)
        publication = text.split('int tetris_smem_publish_private(', 1)[1].split('static bool output_overlap', 1)[0]
        self.assertLess(publication.index('mutex_lock(&slot->lock)'), publication.index('mutex_lock(&owner->lock)'))
        self.assertLess(publication.index('TETRIS_SMEM_MAPPED'), publication.index('slot->owner = owner'))
        self.assertIn('fail_private(owner, -EEXIST)', publication)
        destroy = text.split('int tetris_smem_destroy(', 1)[1]
        self.assertLess(destroy.index('return -EBUSY'), destroy.index('unmap_private(owner)'))

    def test_consumer_copy_isolation(self):
        text = (HERE / 'smem.c').read_text()
        self.assertIn('output_overlap(owner, sizeof(*owner), nc, sizeof(owner->nc))', text)
        self.assertIn('output_overlap(nc, sizeof(owner->nc), cache, sizeof(owner->cache))', text)
        self.assertIn('layout->md_bank4_noncacheable = nc;', text)
        self.assertIn('layout->md_bank4_cacheable = cache;', text)

    def test_c_delimiter_syntax(self):
        # Cheap syntax-shape check, NOT a substitute for actual CI compilation.
        for name in (*check.PRODUCTION, 'test_smem.c'):
            text = (HERE / name).read_text()
            text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
            text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', text)
            stack = []
            pairs = {')': '(', ']': '[', '}': '{'}
            for char in text:
                if char in '([{':
                    stack.append(char)
                elif char in pairs:
                    self.assertTrue(stack, name)
                    self.assertEqual(stack.pop(), pairs[char], name)
            self.assertFalse(stack, name)

    def test_public_stock_footer_bounds(self):
        with tempfile.TemporaryDirectory(prefix='smem-stock-shape-') as temporary:
            path = Path(temporary) / 'test-container'
            header = bytearray(512)
            struct.pack_into('<II', header, 0, 0x58881688, 1024)
            header[8:15] = b'md1rom\0'
            footer = b'CHECK_HEADER' + bytes(500)
            path.write_bytes(header + bytes(512) + footer)
            self.assertEqual(check.stock_footer(path), footer)
            path.write_bytes((header + bytes(512) + footer)[:-1])
            with self.assertRaises(ValueError):
                check.stock_footer(path)
            struct.pack_into('<I', header, 4, 64 * 1024 * 1024 + 16)
            path.write_bytes(header)
            with self.assertRaises(ValueError):
                check.stock_footer(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
