#!/usr/bin/env python3
"""Source/application checks only; no C compiler or device operations."""
import os
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
import check_metadata as candidate

HERE = Path(__file__).resolve().parent
VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', HERE.parents[4] /
    'android_kernel_device_modules_6.1_nothing_mt6878'))


class MetadataTests(unittest.TestCase):
    def test_complete_installed_stack(self):
        objects = candidate.load('metadata_exact_objects', HERE.parent /
                                 'runtime-object-ci/check_objects.py')
        manifest, _, package = objects.plan()
        patch, _ = candidate.build(VENDOR)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'vendor'
            with contextlib.redirect_stdout(io.StringIO()):
                objects.stage_vendor(VENDOR, root, package, manifest)
            subprocess.run(['git', 'apply', '--check', '-'], input=patch,
                           text=True, cwd=root, check=True)

    def test_exact_overlay_applies(self):
        patch, before = candidate.build(VENDOR)
        self.assertEqual(patch, (HERE / 'runtime-metadata.patch.vendor').read_text())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, body in before.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)
            subprocess.run(['git', 'apply', '--check', '-'], input=patch,
                           text=True, cwd=root, check=True)
            subprocess.run(['git', 'apply', '-'], input=patch,
                           text=True, cwd=root, check=True)
            source = (root / (candidate.PREFIX + 'ccci_util_lib_fo.c')).read_text()
            collect = source[source.index('static int __init collect_lk_boot_arguments'):]
            early = collect.index('return ret;')
            self.assertLess(early, collect.index('lk_info_parsing_v2(raw_ptr)'))
            self.assertLess(early, collect.index('mtk_ccci_md_smem_layout_init()'))

    def test_import_has_no_unchecked_append(self):
        source = (HERE / 'owned_tags.h').read_text()
        self.assertEqual(source.count('memcpy_fromio('), 1)
        self.assertNotIn('mtk_ccci_add_new_args(', source)
        self.assertLess(source.index('get_unaligned_le32(chk + 508)'),
                        source.index('struct args_key_val *arg'))
        self.assertIn('arg->source = FROM_KERNEL;', source)

    def test_reservation_before_mapping(self):
        source = (HERE / 'handoff.h').read_text()
        self.assertIn('of_reserved_mem_lookup(owned[i])', source)
        self.assertIn('(u64)reserved->size != windows[i]->capacity', source)
        self.assertIn('of_find_property(owned[i], "reusable", NULL)', source)
        collect = source[source.index('static int tetris_collect_owned_metadata'):]
        self.assertLess(collect.index('mtk_ccci_validate_owned_handoff('),
                        collect.index('ioremap_wc('))
        self.assertNotIn('memset_io(', source)
        self.assertNotIn('ccci_map_phy_addr(', source)
        self.assertNotIn('get_unaligned_le64(raw + 40)', source)
        self.assertLess(collect.index('tetris_owned_banks(&banks)'), collect.index('ioremap_wc('))

    def test_exact_pinned_layout_model(self):
        uboot = Path(os.environ.get('TETRIS_UBOOT_TREE', HERE.parents[4] / 'u-boot-mt6878'))
        self.assertEqual(candidate.layout_model(uboot), (HERE / 'layout_model.h').read_text())
        model = (HERE / 'layout_model.h').read_text()
        self.assertNotIn('(const unsigned char *)rom + rom_size', model)
        self.assertIn('header = chk;', model)
        self.assertIn('static void padding(', model)

    def test_semantics_before_private_publication(self):
        source = (HERE / 'owned_tags.h').read_text()
        self.assertLess(source.index('cursor != size'), source.index('tetris_metadata_semantics('))
        self.assertLess(source.index('tetris_metadata_semantics('), source.index('struct args_key_val *arg'))
        self.assertLess(source.index('tetris_metadata_windows(banks)'), source.index('memcpy_fromio('))
        semantic = (HERE / 'semantic.h').read_text()
        self.assertIn('banks->firmware.capacity, &memory', semantic)
        self.assertIn('get_unaligned_le64(raw + 16) != block->physical', semantic)
        self.assertIn('padding(&memory)', semantic)
        self.assertIn('smem.nc_capacity > banks->nc.capacity', semantic)
        self.assertNotIn('ioremap', semantic)

    def test_all_native_boundary_functions_extract(self):
        extractor = candidate.load('metadata_static_extract', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
        for name in ('tetris_owned_banks', 'tetris_brom_result', 'tetris_descriptor_bytes',
                     'tetris_nomap_resource', 'tetris_retained_nomap'):
            self.assertTrue(extractor.function((HERE / 'handoff.h').read_text(), name)[0])
        for fixture in ('test_import.c', 'test_handoff.c', 'test_reservations.c'):
            self.assertNotIn('-Wno-', (HERE / fixture).read_text())

    def test_retained_nomap_not_catalogue_only(self):
        source = (HERE / 'handoff.h').read_text()
        self.assertIn('of_find_property(owned[i], "compatible", NULL)', source)
        self.assertIn('resource->flags != IORESOURCE_MEM', source)
        self.assertIn('resource->parent != &iomem_resource', source)
        self.assertIn('cover.cursor != cover.end', source)
        self.assertIn('address < cover.end; address += PAGE_SIZE', source)
        self.assertIn('pfn_is_map_memory(pfn)', source)
        self.assertNotIn('memblock_is_map_memory(', source)
        self.assertNotIn('memblock_clear_nomap(', source)
        banks = source[source.index('static int tetris_owned_banks'):]
        self.assertLess(banks.index('tetris_retained_nomap('), banks.index('*out = banks;'))

    def test_pinned_kernel_api_lifetime(self):
        kernel = Path(os.environ.get('TETRIS_KERNEL_TREE', HERE.parents[4] /
            'linux-d84b264a54a37611f2f46bc19363cb9b41606205'))
        init = (kernel / 'arch/arm64/mm/init.c').read_text()
        config = (kernel / 'arch/arm64/Kconfig').read_text()
        setup = (kernel / 'arch/arm64/kernel/setup.c').read_text()
        resources = (kernel / 'kernel/resource.c').read_text()
        rmem = (kernel / 'drivers/of/of_reserved_mem.c').read_text()
        self.assertIn('select ARCH_KEEP_MEMBLOCK', config)
        self.assertIn('return memblock_is_map_memory(addr);', init)
        self.assertIn('EXPORT_SYMBOL(pfn_is_map_memory);', init)
        self.assertIn('if (memblock_is_nomap(region))', setup)
        self.assertIn('res->flags = IORESOURCE_MEM;', setup)
        self.assertIn('EXPORT_SYMBOL_GPL(walk_iomem_res_desc);', resources)
        self.assertIn('.parent = p->parent,', resources)
        self.assertIn('memblock_clear_nomap(rmem->base, rmem->size);', rmem)

    def test_actual_native_fixture_materializes_without_compilation(self):
        fixture, producer = candidate.native_fixture_sources(VENDOR)
        self.assertNotIn('/* STRUCT */', fixture)
        self.assertNotIn('/* EXISTING_LOOKUP */', fixture)
        self.assertNotIn('/* IMPORT */', fixture)
        self.assertIn('tetris_metadata_semantics(snapshot, offsets, lengths, banks)', fixture)
        self.assertIn('const struct tetris_metadata_banks *source_banks', fixture)
        self.assertIn('kernel_import_probe(buffer, (unsigned int)ret, (unsigned int)atoi(argv[2]), &banks)', producer)
        self.assertIn('.dram_size = atoi(argv[2]) == 58 ? 0x200000000ULL', producer)
        self.assertIn('which = 0;', producer)

    def test_missing_producer_precedes_bank_or_map_access(self):
        extractor = candidate.load('metadata_absence_extract', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
        source = extractor.function((HERE / 'handoff.h').read_text(),
                                    'mtk_ccci_validate_owned_handoff')[0]
        descriptor = source.index('tetris_descriptor_bytes(')
        banks = source.index('tetris_owned_banks(')
        self.assertLess(descriptor, banks)
        self.assertIn('if (ret)\n\t\tgoto out;', source[descriptor:banks])

    def test_real_resource_dependency_order(self):
        patch, _ = candidate.build(VENDOR)
        self.assertIn('+\tret = mtk_ccci_validate_owned_handoff(consumer->dev.of_node);', patch)
        self.assertNotIn('register_prepared', patch)

    def test_ci_only_native(self):
        with mock.patch.dict(os.environ, {'CI': 'false', 'GITHUB_ACTIONS': 'false'}):
            with self.assertRaisesRegex(ValueError, 'CI-only'):
                candidate.native_ci(VENDOR, Path('/unused'), Path('/unused'))


if __name__ == '__main__':
    unittest.main()
