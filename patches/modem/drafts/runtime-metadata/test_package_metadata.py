#!/usr/bin/env python3
"""Source/patch tests of the real packaged util path, never C compilation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from package_metadata import build, candidate, MODE, PREFIX, SMEM
from check_packaged_smem import fixture_sources

ROOT = Path(__file__).resolve().parents[4]
VENDOR = Path(os.environ.get('TETRIS_VENDOR_TREE', ROOT.parent /
    'android_kernel_device_modules_6.1_nothing_mt6878'))
PACKAGE = ROOT / 'pmaports/device/testing/linux-postmarketos-mediatek-mt6878'


class PackageMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch, cls.sources = build(VENDOR)

    def test_only_util_sources_and_separate_mode(self):
        self.assertTrue(self.sources)
        self.assertTrue(all(name.startswith(PREFIX) for name in self.sources))
        self.assertNotIn('ccci_tetris_register_prepared', self.patch)
        self.assertNotIn('CONFIG_MTK_ECCCI_TETRIS_OWNER', self.patch)
        self.assertIn(MODE, self.patch)

    def test_owned_module_init_returns_before_legacy_side_effects(self):
        main = self.sources[PREFIX + 'ccci_util_lib_main.c']
        begin = main.index('#if IS_ENABLED(' + MODE + ')')
        branch = main[begin:main.index('#endif', begin)]
        self.assertIn('int ret = mtk_ccci_args_key_val_init()', branch)
        self.assertIn('ret = ccci_util_fo_init()', branch)
        self.assertIn('return 0;', branch)
        for call in ('ccci_log_init(', 'ccci_common_sysfs_init(',
                     'ccci_util_broadcast_init(', 'ccci_sib_init(',
                     'ccci_util_pin_broadcast_init(', 'mtk_ccci_dump_args_info('):
            self.assertNotIn(call, branch)
        self.assertEqual(branch.count('if (ret)\n\t\tgoto metadata_fail;'), 3)
        self.assertIn('ret = mtk_ccci_owned_smem_init()', branch)
        self.assertLess(branch.index('ccci_util_fo_init()'), branch.index('mtk_ccci_owned_smem_init()'))
        self.assertIn('metadata_fail:\n\tmtk_ccci_owned_smem_cleanup();\n\tmtk_ccci_owned_args_cleanup();\n\treturn ret;', branch)

    def test_argument_storage_and_node_are_released(self):
        args = self.sources[PREFIX + 'ccci_util_boot_args.c']
        cleanup = args[args.index('void mtk_ccci_owned_args_cleanup(void)'):args.index('int mtk_ccci_add_new_args(')]
        self.assertIn('i < ARRAY_SIZE(s_buf)', cleanup)
        self.assertIn('kfree(s_buf[i]);\n\t\ts_buf[i] = NULL;', cleanup)
        self.assertIn('kfree(tetris_owned_tags);\n\ttetris_owned_tags = NULL;', cleanup)
        self.assertIn('memset(s_args_tbl, 0, sizeof(s_args_tbl));', cleanup)
        init = args[args.index('int mtk_ccci_args_key_val_init(void)'):args.index('void mtk_ccci_dump_args_info(void)')]
        self.assertEqual(init.count('of_node_put(node)'), 1)
        main = self.sources[PREFIX + 'ccci_util_lib_main.c']
        self.assertIn('module_exit(ccci_util_metadata_exit);', main)
        self.assertIn('static void __exit ccci_util_metadata_exit(void)\n{\n\tmtk_ccci_owned_smem_cleanup();\n\tmtk_ccci_owned_args_cleanup();', main)
        self.assertIn('memset(&tetris_owned_banks, 0, sizeof(tetris_owned_banks));', cleanup)

    def test_bank_snapshot_is_private_and_published_only_after_validation(self):
        owned = self.sources[PREFIX + 'owned_tags.h']
        self.assertLess(owned.index('tetris_metadata_semantics('), owned.index('tetris_owned_banks = *banks;'))
        self.assertLess(owned.index('tetris_owned_banks = *banks;'), owned.index('tetris_owned_tags = snapshot;'))
        self.assertIn('if (!s_init_done || !tetris_owned_tags)\n\t\treturn -ENODATA;', owned)
        self.assertIn('*out = tetris_owned_banks;', owned)
        self.assertNotIn('EXPORT_SYMBOL(mtk_ccci_owned_banks_copy)', self.patch)

    def test_plan_build_omits_mapping_and_publication_bodies(self):
        smem = self.sources[PREFIX + 'tetris_runtime_smem/smem.c']
        for forbidden in ('ioremap', 'iounmap', 'tetris_smem_map_private(',
                          'tetris_smem_publish_private(', 'tetris_smem_export_private('):
            self.assertNotIn(forbidden, smem)
        for name in ('tetris_smem_create', 'tetris_smem_preview', 'tetris_smem_destroy'):
            self.assertIn('int ' + name + '(', smem)
        owner = self.sources[PREFIX + 'owned_smem_plan.c']
        for call in ('mtk_ccci_owned_banks_copy', 'tetris_smem_from_arguments',
                     'tetris_smem_preview', 'tetris_smem_destroy'):
            self.assertIn(call + '(', owner)
        self.assertIn('tetris_runtime_smem/smem.o', self.sources[PREFIX + 'Makefile'])
        self.assertNotIn('EXPORT_SYMBOL', owner)
        extractor = candidate().load('packaged_pure_bodies',
            SMEM.parent / 'runtime-lifecycle/check_lifecycle.py')
        original = (SMEM / 'smem.c').read_text()
        for name in ('validate_rows', 'build_spans', 'populate_tables',
                     'tetris_smem_create', 'copy_layout', 'tetris_smem_preview'):
            self.assertIn(extractor.function(original, name)[0], smem)
        self.assertEqual(self.sources[PREFIX + 'tetris_runtime_smem/arguments.c'],
                         (SMEM / 'arguments.c').read_text())

    def test_native_fixture_uses_generated_import_and_actual_cleanup(self):
        fixture, boot, sources = fixture_sources(VENDOR)
        self.assertIn(sources[PREFIX + 'owned_tags.h'], fixture)
        self.assertIn('packaged_probe(&banks, ret);', fixture)
        self.assertIn('void mtk_ccci_owned_args_cleanup(void)', fixture)
        self.assertIn('#include "test_packaged_smem.c"', fixture)
        self.assertIn('kernel_import_probe(buffer,', boot)

    def test_boot_evidence_is_copied_without_access_permission(self):
        owner = self.sources[PREFIX + 'owned_smem_plan.c']
        self.assertIn('of_find_property(node, TETRIS_SMEM_BOOT_PROPERTY, &length)', owner)
        self.assertIn('length != (int)sizeof(wire)', owner)
        self.assertLess(owner.index('of_node_put(node)'), owner.index('tetris_smem_boot_decode('))
        self.assertIn('regions[i]->size > evidence.record[i].range_size', owner)
        self.assertIn('regions[i]->base_ap_view_phy != evidence.record[i].range_start', owner)
        self.assertLess(owner.index('ret = collect_boot_evidence(&banks)'),
                        owner.index('tetris_owned_smem_plan.ready = true'))
        self.assertEqual(self.sources[PREFIX + 'smem_boot_evidence/boot_evidence.c'],
                         (SMEM.parent / 'smem-boot-evidence/boot_evidence.c').read_text())
        self.assertIn('smem_boot_evidence/boot_evidence.o', self.sources[PREFIX + 'Makefile'])
        for forbidden in ('ioremap(', 'ioremap_wc(', 'arm_smccc_smc(', 'EXPORT_SYMBOL'):
            self.assertNotIn(forbidden, owner)
        fixture = (Path(__file__).parent / 'test_packaged_smem.c').read_text()
        for required in ('test_evidence_collection(&copied)', 'property_length = 0',
                         'property_read_error = -EIO', 'node_exists = false',
                         'acquired == released', 'compatible = false',
                         'memset(evidence_wire, 0xa5', 'put64(evidence_wire + 80 + 32, 4096)'):
            self.assertIn(required, fixture)

    def test_native_compilation_rejected_outside_ci(self):
        env = dict(os.environ)
        env.pop('CI', None)
        env.pop('GITHUB_ACTIONS', None)
        result = subprocess.run(['python3', '-B', str(Path(__file__).parent / 'check_packaged_smem.py'),
            '--vendor', str(VENDOR), '--uboot', '/nonexistent',
            '--stock-container', '/nonexistent'], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('GitHub CI-only', result.stderr)

    def test_resource_only_retains_owner_and_never_touches_smem(self):
        owner = self.sources[PREFIX + 'owned_smem_plan.c']
        claim = self.sources[PREFIX + 'smem_reservation.c']
        preview = self.sources[PREFIX + 'smem_extent_preview.c']
        self.assertIn('CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY', owner)
        self.assertIn('tetris_owned_smem_plan.owner = owner;', owner)
        self.assertIn('__module_get(THIS_MODULE);', owner)
        self.assertIn('tetris_owned_smem_plan.has_boot_evidence ?', owner)
        self.assertLess(owner.index('ret = collect_boot_evidence(&banks)'),
                        owner.index('tetris_smem_reserve_extents('))
        self.assertIn('while (reservation->count)', claim)
        self.assertIn('release_mem_region(held->start, resource_size(held))', claim)
        self.assertLess(claim.index('span->bytes > record->range_size'),
                        claim.index('request_mem_region('))
        self.assertIn('tetris_smem_release_extents(reservation);', claim)
        self.assertIn('owner->state != TETRIS_SMEM_VALIDATED', preview)
        self.assertIn('span->virtual', preview)
        self.assertLess(preview.index('plan.span[i] ='), preview.index('memcpy(output,'))
        for source in (owner, claim, preview):
            for forbidden in ('ioremap(', 'ioremap_wc(', 'memcpy_fromio(',
                              'arm_smccc_smc(', 'EXPORT_SYMBOL'):
                self.assertNotIn(forbidden, source)

    def test_resource_profile_uses_same_r181_exports_and_native_faults(self):
        script = (ROOT / 'ci/packaged-smem-objects.py').read_text()
        self.assertIn('-DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1', script)
        self.assertIn("saved / 'ccci-util-smem-reservation.ko'", script)
        self.assertIn("report['reservation_module'] = dict(report['linked_module']", script)
        fixture = (Path(__file__).parent / 'test_smem_reservation.c').read_text()
        self.assertIn('changed.span[1] = changed.span[0]', fixture)
        self.assertIn('claim_fail = i', fixture)
        self.assertIn('&competing) == -EBUSY', fixture)
        runner = (Path(__file__).parent / 'check_packaged_smem.py').read_text()
        self.assertIn('(4096, 0), (65536, 0), (4096, 1), (65536, 1)', runner)

    def test_only_ap_buffer_is_mapped_and_unmapped(self):
        handoff = self.sources[PREFIX + 'handoff.h']
        collect = handoff[handoff.index('static int tetris_collect_owned_metadata('):]
        self.assertEqual(collect.count('ioremap_wc('), 1)
        self.assertIn('ioremap_wc((phys_addr_t)base, 65536)', collect)
        self.assertIn('banks.tags.base != base', collect)
        self.assertIn('iounmap(mapped)', collect)
        fo = self.sources[PREFIX + 'ccci_util_lib_fo.c']
        collect = fo[fo.index('static int __init collect_lk_boot_arguments('):]
        owned = collect.index('tetris_collect_owned_metadata(node)')
        self.assertLess(owned, collect.index('"ccci,modem_info_v2"'))
        self.assertIn('of_node_put(node);\n\treturn ret;', collect[owned:])

    def test_patch_applies_after_shipping_util_adaptations(self):
        with tempfile.TemporaryDirectory(prefix='metadata-util-stack-') as temp:
            root = Path(temp)
            archive = subprocess.Popen(['git', '-C', str(VENDOR), 'archive',
                'ee2be53cb75670b548948636a0db1d1ff112bf12', PREFIX], stdout=subprocess.PIPE)
            unpack = subprocess.run(['tar', '-xf', '-', '-C', str(root)], stdin=archive.stdout,
                                    capture_output=True)
            archive.stdout.close()
            self.assertEqual(archive.wait(), 0)
            self.assertEqual(unpack.returncode, 0, unpack.stderr)
            for name in ('0039-vendor-ccci-util-linux-6.18-api.patch.vendor',
                         '0173-vendor-ccci-smem-map-span.patch.vendor'):
                applied = subprocess.run(['patch', '--batch', '-p1', '-i', str(PACKAGE / name)],
                                         cwd=root, capture_output=True, text=True)
                self.assertEqual(applied.returncode, 0, applied.stderr + applied.stdout)
            applied = subprocess.run(['git', 'apply', '--check', '-'], input=self.patch,
                                     text=True, cwd=root, capture_output=True)
            self.assertEqual(applied.returncode, 0, applied.stderr)

    def test_build_is_isolated_and_uses_real_kernel_exports(self):
        apkbuild = (PACKAGE / 'APKBUILD').read_text()
        start = apkbuild.index('_build_ccci_metadata_only() {')
        helper = apkbuild[start:apkbuild.index('\n}\n', start)]
        self.assertIn('root="$srcdir/tetris-modem-metadata"', helper)
        self.assertLess(helper.index('rm -rf -- "$root"'), helper.index('cp "$source"'))
        self.assertIn('cp "$source"/*.c "$source"/*.h "$source/Makefile" "$util/"', helper)
        self.assertIn('git -C "$root" apply --check', helper)
        self.assertIn('make -j', helper)
        self.assertIn('-C "$builddir" M="$util"', helper)
        self.assertIn('KBUILD_MODPOST_WARN=', helper)
        self.assertIn('-D' + MODE + '=1', helper)
        self.assertIn('modinfo -F vermagic', helper)
        self.assertIn('mtk_ccci_import_owned_tags$', helper)
        self.assertIn('mtk_ccci_validate_owned_handoff$', helper)
        self.assertNotIn('KBUILD_MODPOST_WARN=1', helper)

    def test_candidate_never_enters_shared_prepare_or_package(self):
        apkbuild = (PACKAGE / 'APKBUILD').read_text()
        prepare = apkbuild[apkbuild.index('prepare() {'):apkbuild.index('_build_', apkbuild.index('prepare() {'))]
        self.assertNotIn('ccci-owned-metadata.overlay', prepare)
        package = apkbuild[apkbuild.index('package() {'):apkbuild.index('\nsha512sums=')]
        self.assertNotIn('tetris-modem-metadata', package)
        self.assertNotIn('_build_ccci_metadata_only', package)
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('--modem --diagnostics --metadata', workflow)
        self.assertIn('test_package_metadata.py', workflow)

    def test_disabled_dt_identity_matches_pinned_b41(self):
        source = subprocess.check_output(['git', '-C', str(VENDOR), 'show',
            'ee2be53cb75670b548948636a0db1d1ff112bf12:arch/arm64/boot/dts/mediatek/mt6878.dts'], text=True)
        anchor = (PACKAGE / '0174-arm64-dts-mediatek-tetris-disabled-ccci-handoff.patch').read_text()
        for property in ('compatible = "mediatek,mddriver";',
                         'mediatek,ap-plat-info = <6878>;', 'mediatek,md-generation = <6299>;'):
            self.assertIn(property, source)
            self.assertIn(property, anchor)
        self.assertIn('+\t\tstatus = "disabled";', anchor)


if __name__ == '__main__':
    unittest.main()
