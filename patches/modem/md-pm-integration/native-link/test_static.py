#!/usr/bin/env python3
"""Local parser/source/patch tests only; no compile/link/target execution proofs."""
import argparse
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import abi
import link


class ABIParserTests(unittest.TestCase):
    # These scalar strings/bytes exercise parsers. They are NOT generated
    # symbol tables, executable fixtures or evidence of a successful build.
    def table(self):
        return abi.symvers("0x00000001\tapi\tvmlinux\tEXPORT_SYMBOL_GPL\t\n")

    def module(self):
        return {"metadata": {"name": ["consumer"], "license": ["GPL"],
                             "depends": [""], "vermagic": ["example"]},
                "imports": {"api": "STB_GLOBAL"}, "versions": {"api": 1, "module_layout": 2},
                "crc_mode": "enforced_by_inherited_config"}

    def test_config_duplicate_is_rejected(self):
        self.assertEqual(abi.config("CONFIG_ARM64=y\n# CONFIG_MODVERSIONS is not set\n")["MODVERSIONS"], "n")
        with self.assertRaises(ValueError):
            abi.config("CONFIG_CFI=y\nCONFIG_CFI=n\n")

    def test_no_security_or_abi_flag_fallback(self):
        shipping = abi.config((link.PACKAGE / "config-postmarketos-mediatek-mt6878.aarch64").read_text())
        self.assertEqual(shipping["MODVERSIONS"], "n")
        self.assertEqual(shipping["CFI"], "y")
        self.assertEqual(shipping["LTO_CLANG_THIN"], "y")
        for name, value in (("CFI", "n"), ("CFI_PERMISSIVE", "y"), ("LTO_CLANG_THIN", "n"),
                            ("MODVERSIONS", "y"), ("MODULE_ALLOW_MISSING_NAMESPACE_IMPORTS", "y")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                abi.security_profile(shipping, {**shipping, name: value})

    def test_export_parser_keeps_crc_owner_license_namespace(self):
        self.assertEqual(self.table()["api"], {"crc": 1, "owner": "vmlinux",
                                             "export": "EXPORT_SYMBOL_GPL", "namespace": ""})
        for data in ("", "0x1\tapi\tvmlinux\tEXPORT_SYMBOL_GPL\t\n",
                     "0x00000001 api vmlinux EXPORT_SYMBOL_GPL\n",
                     "0x00000001\tapi\tvmlinux\tignored\t\n"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                abi.symvers(data)

    def test_duplicate_and_ambiguous_exports_fail(self):
        with self.assertRaises(ValueError):
            abi.symvers("0x00000001\tapi\tvmlinux\tEXPORT_SYMBOL_GPL\t\n" * 2)
        with self.assertRaises(ValueError):
            abi.export_index({"kernel": self.table(), "other": self.table()})

    def test_basic_arm64_version_parser(self):
        data = struct.pack("<Q56s", 0x12345678, b"api\0")
        versions, status = abi.decode_versions(data, None, None, {"MODVERSIONS": "y", "BASIC_MODVERSIONS": "y"})
        self.assertEqual(versions, {"api": 0x12345678})
        self.assertEqual(status, "enforced_by_inherited_config")
        with self.assertRaises(ValueError):
            abi.decode_versions(data[:-1], None, None, {"MODVERSIONS": "y", "BASIC_MODVERSIONS": "y"})

    def test_extended_versions_include_c_literal_terminator(self):
        cfg = {"MODVERSIONS": "y", "EXTENDED_MODVERSIONS": "y"}
        self.assertEqual(abi.decode_versions(None, struct.pack("<II", 1, 2), b"first\0second\0\0", cfg)[0],
                         {"first": 1, "second": 2})
        with self.assertRaises(ValueError):
            abi.decode_versions(None, struct.pack("<II", 1, 2), b"first\0\0", cfg)

    def test_disabled_crc_cannot_be_reported_as_enforced(self):
        self.assertEqual(abi.decode_versions(None, None, None, {"MODVERSIONS": "n"}),
                         ({}, "disabled_by_inherited_config"))
        with self.assertRaises(ValueError):
            abi.decode_versions(struct.pack("<Q56s", 1, b"api"), None, None, {"MODVERSIONS": "n"})

    def test_actual_crc_mismatch_is_a_failure(self):
        exports = abi.export_index({"kernel": {**self.table(), "module_layout":
            {"crc": 2, "owner": "vmlinux", "export": "EXPORT_SYMBOL", "namespace": ""}}})
        cfg = {"MODVERSIONS": "y"}
        self.assertEqual(abi.closure(self.module(), exports, cfg)["crc_count"], 2)
        bad = self.module()
        bad["versions"]["api"] = 3
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            abi.closure(bad, exports, cfg)

    def test_missing_and_stale_crc_rows_fail(self):
        exports = abi.export_index({"kernel": self.table()})
        with self.assertRaises(ValueError):
            abi.closure(self.module(), exports, {"MODVERSIONS": "y"})
        bad = self.module()
        bad["versions"] = {"api": 1}
        with self.assertRaises(ValueError):
            abi.closure(bad, exports, {"MODVERSIONS": "y"})

    def test_missing_strong_import_and_wrong_dep_fail(self):
        with self.assertRaisesRegex(ValueError, "strong import"):
            abi.closure(self.module(), {}, {"MODVERSIONS": "y"})
        bad = self.module()
        bad["metadata"]["depends"] = ["invented_owner"]
        with self.assertRaisesRegex(ValueError, "dependency closure"):
            abi.closure(bad, abi.export_index({"kernel": self.table()}), {"MODVERSIONS": "y"})

    def test_namespace_uses_only_d84_tail_glob(self):
        self.assertTrue(abi.namespace_allowed("module:foo,consumer*", "consumer", set()))
        self.assertFalse(abi.namespace_allowed("module:cons?mer", "consumer", set()))
        self.assertFalse(abi.namespace_allowed("DMA_BUF", "consumer", set()))
        self.assertTrue(abi.namespace_allowed("DMA_BUF", "consumer", {"DMA_BUF"}))

    def test_core_composition_requires_actual_native_object(self):
        value = "/owned/eccci/fsm/ccci_tetris_native_start.o\n/owned/eccci/fsm/modem_sys1.o\n"
        self.assertEqual(len(link.native_composition(value)), 2)
        for wrong in ("", value + "/owned/eccci/fsm/ccci_tetris_owner.o\n",
                      value + "/owned/eccci/hif/ccci_tetris_hif_owned.o\n"):
            with self.assertRaises(ValueError):
                link.native_composition(wrong)

    def test_native_exports_must_be_actual_gpl_provider(self):
        with self.assertRaises(ValueError):
            link.require_exports(self.table(), ("missing",), "vmlinux")
        with self.assertRaises(ValueError):
            link.require_exports(self.table(), ("api",), "another_module")

    def test_local_build_guard_precedes_mutation_and_compiler(self):
        with tempfile.TemporaryDirectory(prefix="tetris-native-link-guard-") as directory:
            target = Path(directory) / "must-not-exist"
            with patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}), \
                 patch.object(link.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "CI-only"):
                    link.build(argparse.Namespace(destination=target, enable_native_link=True))
                run.assert_not_called()
            self.assertFalse(target.exists())

    def test_permissive_modpost_environment_is_not_accepted(self):
        _, real, _ = link.helpers()
        with patch.object(real, "require_ci"), patch.dict(os.environ, {"KBUILD_MODPOST_WARN": "1"}):
            with self.assertRaisesRegex(ValueError, "override forbidden"):
                link.require_ci(real)

    def test_no_r181_table_backend_or_runtime_operation_in_build(self):
        source = (link.HERE / "link.py").read_text()
        for wrong in ("EXPORTS_SHA", "CONFIG_SHA", "backend_sources()", "--link-r181", "insmod", "fastboot",
                      "KBUILD_MODPOST_WARN=1", "KBUILD_MODPOST_NOFINAL=1", "-DCONFIG_CFI=0", "scripts/config"):
            self.assertNotIn(wrong, source)
        self.assertIn('"vmlinux", "modules"', source)
        self.assertIn('"KBUILD_EXTRA_SYMBOLS=" + str(util / "Module.symvers")', source)
        self.assertIn('"CFI"', (link.HERE / "abi.py").read_text())

    def test_manifest_closes_all_owned_files(self):
        link.verify_manifest()

    def test_artifact_collection_is_selected_not_entire_output(self):
        source = (link.HERE / "link.py").read_text()
        collection = source.split('artifacts = destination / "artifacts"', 1)[1].split("except Exception", 1)[0]
        self.assertNotIn("copytree", collection)
        self.assertNotIn('copyfile(configured / "vmlinux"', collection)
        self.assertNotIn('copyfile(configured / ".config"', collection)
        self.assertIn('artifacts / "native-supplier.o"', collection)
        self.assertIn('"kernel-output/**"', collection)

    def test_selector_flags_cannot_reenable_forbidden_runtime_profile(self):
        source = (link.HERE / "link.py").read_text()
        for selector in ("OF_OVERLAY", "OF_UNITTEST", "KEXEC", "KEXEC_FILE", "KEXEC_CORE"):
            self.assertIn('"' + selector + '"', source.split("def recorded_inputs", 1)[1].split("def reconstruct_kernel", 1)[0])

    def test_relative_input_components_are_normalized_without_accepting_symlinks(self):
        with tempfile.TemporaryDirectory(prefix="tetris-native-link-path-") as directory:
            root = Path(directory).resolve()
            (root / "input").mkdir()
            self.assertEqual(link.input_path(root / "input/../input"), root / "input")
            (root / "alias").symlink_to(root / "input", target_is_directory=True)
            for path in (root / "alias", root / "alias/../input"):
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "symlink"):
                    link.input_path(path)

    def test_composite_gpl_declarations_are_not_ambiguous_identity(self):
        image = self.module()
        image["metadata"]["license"] = ["GPL", "GPL"]
        image["versions"] = {}
        image["crc_mode"] = "disabled_by_inherited_config"
        table = self.table()
        table["api"]["crc"] = 0
        self.assertEqual(abi.closure(image, abi.export_index({"kernel": table}), {"MODVERSIONS": "n"})["crc_count"], 0)
        for licenses in ([], ["GPL", "Proprietary"]):
            image["metadata"]["license"] = licenses
            with self.assertRaisesRegex(ValueError, "license"):
                abi.closure(image, abi.export_index({"kernel": table}), {"MODVERSIONS": "n"})


class SourceClosureTests(unittest.TestCase):
    def test_real_complete_vendor_provider_and_native_overlay_application(self):
        vendor = link.ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878"
        pristine = link.ROOT.parent / ("linux-" + link.LINUX)
        result = link.source_check(vendor, pristine)
        self.assertEqual(result["vendor_commit"], link.VENDOR)
        self.assertEqual(result["linux_commit"], link.LINUX)
        self.assertGreater(result["source_count"], 100)
        self.assertEqual(set(result["provider_patches_sha256"]), {"metadata", "mapped_copy"})


if __name__ == "__main__":
    unittest.main()
