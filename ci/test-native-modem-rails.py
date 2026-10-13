#!/usr/bin/env python3
"""Static source, package-copy, patch-application and full-tree negative tests."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


rails = module("rails_stage", "ci/stage-native-modem-rails.py")
KERNEL = Path(os.environ.get("TETRIS_KERNEL_TREE", str(ROOT.parent / ("linux-" + rails.LINUX))))
VENDOR = Path(os.environ.get("TETRIS_VENDOR_TREE", str(ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878")))
parent = rails.parent_stage()
parent_tests = module("rails_parent_tests", "ci/test-native-modem-image.py")
supplier = module("rails_supplier", "patches/modem/md-pmic-supplier/stage.py")
ints = parent_tests.hif_test.ints
PMIC = "/soc@0/spmi@1cc04000/pmic@4"
REG = PMIC + "/regulators"
CI = {"CI": "true", "GITHUB_ACTIONS": "true"}


def snapshot(tree):
    return {str(path.relative_to(tree)): rails.digest(path.read_bytes())
            for path in tree.rglob("*") if path.is_file()}


def fixture(activate):
    normal, baseline = parent_tests.ImageTests().fixture()
    additional = {
        "/topckgen": {"compatible": b"mediatek,mt6878-topckgen\0syscon\0",
                      "reg": ints([0x10000000, 0x1000]), "phandle": ints([7]), "#clock-cells": ints([1])},
        PMIC.rsplit("/", 1)[0]: {"compatible": b"mediatek,mt6878-spmi\0", "#address-cells": ints([2]),
                                 "#size-cells": ints([0]), "reg": ints([0x1cc04000, 0x900, 0x1cc01000, 0x100])},
        PMIC: {"compatible": b"mediatek,mt6363\0", "reg": ints([4, 0])},
        REG: {"compatible": b"mediatek,mt6363-regulator\0"},
        REG + "/vcn13": {"regulator-name": b"mt6363-vcn13\0", "regulator-min-microvolt": ints([900000]),
                         "regulator-max-microvolt": ints([1810000]), "phandle": ints([101])},
        REG + "/vrfio18": {"regulator-name": b"mt6363-vrfio18\0", "regulator-min-microvolt": ints([600000]),
                           "regulator-max-microvolt": ints([2100000]), "phandle": ints([102])},
        "/connectivity": {"vcn13-supply": ints([101]), "vrfio18-supply": ints([102]), "status": b"okay\0"},
        "/usb": {"status": b"okay\0"}, "/scp": {"status": b"okay\0"},
        "/gpu": {"status": b"disabled\0"}, "/camera": {"status": b"disabled\0"},
    }
    normal.update(copy.deepcopy(additional))
    baseline.update(copy.deepcopy(additional))
    candidate = copy.deepcopy(baseline)
    handles = {}
    for i, (name, (label, minimum)) in enumerate(rails.CHILDREN.items(), 200):
        handles[name] = i
        candidate[REG + "/" + name] = {
            "phandle": ints([i]), "status": b"okay\0" if activate else b"disabled\0",
            "regulator-name": label.encode() + b"\0", "regulator-min-microvolt": ints([minimum]),
            "regulator-max-microvolt": ints([1193750]), "regulator-enable-ramp-delay": ints([180]),
            "regulator-allowed-modes": ints([0, 2]),
        }
    candidate["/modem"]["ccci-topckgen"] = ints([7])
    for name, (rail, voltage) in rails.SUPPLIES.items():
        candidate["/modem"][name + "-supply"] = ints([handles[rail]])
        candidate["/modem"][name] = ints([voltage, voltage])
    return normal, baseline, candidate


class NativeRails(unittest.TestCase):
    def prepare_package(self, tree):
        for relative in (parent.KERNEL, parent.DEVICE):
            shutil.copytree(ROOT / "pmaports" / relative, tree / relative)
        with patch.dict(os.environ, CI):
            parent.stage(tree, tree / "parent.json")
        return tree / "parent.json", tree / "rails.json"

    def prepare_kernel(self, tree):
        supplier.packaged(tree)
        for path in rails.CORE_HASHES:
            destination = tree / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(KERNEL / path, destination)
        board = tree / (rails.PREFIX + parent.BOARD + ".dts")
        board.parent.mkdir(parents=True, exist_ok=True)
        board.write_text(rails.board_source(parent))
        return board

    def test_exact_source_evidence_and_real_pmic(self):
        data, manifest, evidence = rails.inputs()
        self.assertEqual(rails.digest(data), rails.PATCH_SHA)
        vendor = VENDOR
        texts = {}
        for name, record in evidence["sources"].items():
            if record["revision"] == rails.VENDOR:
                source = subprocess.check_output(["git", "-C", str(vendor), "show",
                                                   rails.VENDOR + ":" + record["path"]])
            elif record["revision"] == rails.LINUX:
                source = (KERNEL / record["path"]).read_bytes()
            else:
                source = (ROOT / record["path"]).read_bytes()
            self.assertEqual(rails.digest(source), record["sha256"], name)
            texts[name] = source.decode()
        for name, (rail, voltage) in rails.SUPPLIES.items():
            self.assertIn(name + "-supply = <&" + rails.CHILDREN[rail][0] + ">;", texts["vendor-board"])
            self.assertIn(name + f" = <{voltage} {voltage}>;", texts["vendor-board"])
        self.assertIn("ccci-topckgen = <&topckgen_clk>;", texts["vendor-board"])
        self.assertIn('compatible = "mediatek,mt6878-topckgen", "syscon";', texts["vendor-board"])

    def test_registration_uses_single_mutable_parse_without_const_cast(self):
        original = (rails.HERE / Path(rails.HELPER).name).read_text()
        revised = rails.registration_header(original)
        self.assertEqual(revised.count("of_get_regulator_init_data("), 1)
        self.assertIn("struct regulator_init_data *init_data;", revised)
        self.assertIn("init_data->constraints.apply_uV = false;", revised)
        self.assertNotIn("config.init_data->constraints.apply_uV", revised)
        self.assertNotIn("(struct regulator_init_data *)", revised)
        self.assertEqual(rails.registration_base(revised), original)
        for label, minimum in rails.CHILDREN.values():
            body = texts["vendor-pmic-dt"].split('regulator-name = "' + label + '";', 1)[1].split("};", 1)[0]
            self.assertIn(f"regulator-min-microvolt = <{minimum}>;", body)
            self.assertIn("regulator-max-microvolt = <1193750>;", body)
        self.assertEqual(manifest["stock_consumer_mapping"]["md-vmodem"]["rail"], "vbuck2")

    def test_core_clamp_is_suppressed_without_counterfeit_permissions(self):
        _, _, evidence = rails.inputs()
        kernel = KERNEL
        core = (kernel / evidence["sources"]["linux-core"]["path"]).read_text()
        of = (kernel / evidence["sources"]["linux-of"]["path"]).read_text()
        self.assertIn("if (constraints->min_uV && constraints->max_uV)\n\t\tconstraints->apply_uV = true;", of)
        clamp = core.split("static int machine_constraints_voltage", 1)[1].split("/* constrain machine-level", 1)[0]
        self.assertIn("if (rdev->constraints->apply_uV &&", clamp)
        self.assertIn("current_uV < rdev->constraints->min_uV", clamp)
        self.assertIn("_regulator_do_set_voltage(", clamp)
        header = (rails.HERE / "mt6363-modem-regulator.h").read_text()
        self.assertIn("!enable && !state->owns_enable", header)
        self.assertIn("state->registering", header)
        self.assertIn("states[i].desc.of_match = NULL;", header)
        self.assertIn("if (!dev->of_node || !desc->of_match)\n\t\treturn NULL;", of)
        self.assertIn("init_data = config->init_data;", core)
        self.assertLess(header.index("if (!config.init_data)"), header.index("devm_regulator_register("))
        additions = "\n".join(line[1:] for line in rails.integration_patch(True).decode().splitlines()
                              if line.startswith("+") and not line.startswith("+++"))
        self.assertEqual(additions.count("constraints.apply_uV = false;"), 1)
        for forbidden in ("valid_ops_mask", "return 0;", "regmap_", "regulator-boot-on", "regulator-always-on",
                          "regulator-initial-mode", "regulator-fixed", "power-domains"):
            self.assertNotIn(forbidden, additions)

    def test_actual_patch_application_both_modes_and_all_existing_provider_blocks(self):
        for activate in (False, True):
            with self.subTest(activate=activate), tempfile.TemporaryDirectory() as directory:
                tree = Path(directory)
                board = self.prepare_kernel(tree)
                before = snapshot(tree)
                result = rails.check_kernel(tree, activate)
                self.assertEqual(snapshot(tree), before)
                data, manifest, _ = rails.inputs()
                rails.apply(tree, data)
                for path, sha in manifest["staged_after_sha256"].items():
                    self.assertEqual(rails.digest((tree / path).read_bytes()), sha)
                rails.apply(tree, rails.integration_patch(activate))
                self.assertEqual(rails.registration_base((tree / rails.HELPER).read_text()),
                                 (rails.HERE / Path(rails.HELPER).name).read_text())
                driver = (tree / supplier.DRIVER).read_text()
                restored = driver.replace('#include "mt6363-modem-regulator.h"\n\n', "", 1)
                restored = restored.replace("return mt6363_md_register(pdev, regmap);", "return 0;", 1)
                restored = restored.removesuffix('\n#include "mt6363-modem-regulator-test.h"\n')
                self.assertEqual(rails.digest(restored.encode()), manifest["prepared_before_sha256"][supplier.DRIVER])
                text = board.read_text()
                self.assertTrue(text.startswith(rails.board_source(parent)))
                self.assertEqual(text.count('status = "okay";') - rails.board_source(parent).count('status = "okay";'),
                                 3 if activate else 0)
                self.assertIn('&mddriver {\n\tstatus = "disabled";', text)
                self.assertEqual(result["native_patch_sha256"], rails.PATCH_SHA)
                with self.assertRaisesRegex(ValueError, "provider differs|already present"):
                    rails.check_kernel(tree, activate)

    def test_prepared_drift_rejected_without_writes(self):
        for target in (supplier.DRIVER, supplier.BINDING, rails.PREFIX + parent.BOARD + ".dts", *rails.CORE_HASHES):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                tree = Path(directory)
                self.prepare_kernel(tree)
                path = tree / target
                path.write_text(path.read_text() + "\n/* drift */\n")
                before = snapshot(tree)
                with self.assertRaises(ValueError):
                    rails.check_kernel(tree)
                self.assertEqual(snapshot(tree), before)

    def test_local_and_repository_staging_refused(self):
        with patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "CI-only"):
                rails.stage(ROOT / "pmaports", Path("unused"), Path("unused2"), True)
        with patch.dict(os.environ, CI):
            for path in (ROOT, ROOT / "pmaports", ROOT / "worktrees/future"):
                with self.assertRaisesRegex(ValueError, "repository/shipping"):
                    rails.stage(path, Path("unused"), Path("unused2"), True)

    def test_future_copy_additive_order_and_all_other_inputs_preserved(self):
        shipping_before = snapshot(ROOT / "pmaports" / parent.KERNEL)
        for activate in (False, True):
            with self.subTest(activate=activate), tempfile.TemporaryDirectory() as directory:
                tree = Path(directory)
                parent_report, report = self.prepare_package(tree)
                before = snapshot(tree)
                with patch.dict(os.environ, CI):
                    result = rails.stage(tree, parent_report, report, activate)
                after = snapshot(tree)
                changed = {name for name in before if before[name] != after[name]}
                self.assertEqual(changed, {parent.KERNEL + "/APKBUILD"})
                self.assertEqual(after.keys() - before.keys(),
                                 {parent.KERNEL + "/" + rails.DRIVER_PATCH,
                                  parent.KERNEL + "/" + rails.DT_PATCH, "rails.json"})
                apk = (tree / parent.KERNEL / "APKBUILD").read_text()
                self.assertIn("pkgrel=185\n", apk)
                self.assertIn("\t0184-native-modem-single-ack.patch\n\t" + rails.DRIVER_PATCH + "\n\t" + rails.DT_PATCH + "\n", apk)
                self.assertEqual(result["native_children_available"], activate)
                self.assertFalse(result["modem_consumer_enabled"])
                self.assertEqual(result["changes"][rails.DRIVER_PATCH], rails.PATCH_SHA)
                staged_before = snapshot(tree)
                with patch.dict(os.environ, CI), self.assertRaisesRegex(ValueError, "already staged"):
                    rails.stage(tree, parent_report, tree / "again.json", activate)
                self.assertEqual(snapshot(tree), staged_before)
        self.assertEqual(snapshot(ROOT / "pmaports" / parent.KERNEL), shipping_before)

    def test_bad_parent_and_output_collision_leave_copy_unchanged(self):
        for fault in ("manifest", "parent-patch", "config", "connectivity", "fit", "report", "symlink"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                tree = Path(directory)
                parent_report, report = self.prepare_package(tree)
                package = tree / parent.KERNEL
                if fault == "manifest":
                    data = json.loads(parent_report.read_text())
                    data["kernel_package"] = "7.2.1-r183"
                    parent_report.write_text(json.dumps(data))
                elif fault in ("parent-patch", "config", "connectivity"):
                    names = {"parent-patch": "0184-native-modem-single-ack.patch",
                             "config": "config-postmarketos-mediatek-mt6878.aarch64",
                             "connectivity": "0008-connectivity-mt6878-mt6631-connsys.patch"}
                    path = package / names[fault]
                    path.write_text(path.read_text().replace("# CONFIG_SUSPEND is not set", "CONFIG_SUSPEND=y")
                                    if fault == "config" else path.read_text() + "drift\n")
                elif fault == "fit":
                    path = tree / parent.DEVICE / "boot_image.its"
                    path.write_text(path.read_text().replace(parent.BOARD, "wrong-board"))
                elif fault == "report":
                    report = package / "APKBUILD"
                else:
                    path = package / "APKBUILD"
                    path.unlink()
                    path.symlink_to(ROOT / "pmaports" / parent.KERNEL / "APKBUILD")
                before = snapshot(tree)
                with patch.dict(os.environ, CI), self.assertRaises(ValueError):
                    rails.stage(tree, parent_report, report, True)
                self.assertEqual(snapshot(tree), before)

    def test_full_dt_chain_both_modes(self):
        for activate in (False, True):
            with self.subTest(activate=activate):
                result = rails.validate(*fixture(activate), activate=activate)
                self.assertEqual(result["pmic"], PMIC)
                self.assertEqual(result["native_children_available"], activate)

    def test_every_unrelated_node_property_and_inventory_preserved(self):
        normal, baseline, candidate = fixture(True)
        for path, props in baseline.items():
            for prop in props.keys() - {"phandle", "linux,phandle"}:
                with self.subTest(path=path, prop=prop):
                    bad = copy.deepcopy(candidate)
                    bad[path].pop(prop)
                    with self.assertRaises(ValueError):
                        rails.validate(normal, baseline, bad, True)
            with self.subTest(remove=path):
                bad = copy.deepcopy(candidate)
                bad.pop(path)
                with self.assertRaises(ValueError):
                    rails.validate(normal, baseline, bad, True)
        bad = copy.deepcopy(candidate)
        bad[REG + "/fake-vmodem"] = {"compatible": b"regulator-fixed\0"}
        with self.assertRaises(ValueError):
            rails.validate(normal, baseline, bad, True)

    def test_unsafe_rail_properties_wrong_owner_voltage_top_and_modem_activation(self):
        faults = [(REG + "/vbuck2", key, b"") for key in
                  ("regulator-boot-on", "regulator-always-on", "regulator-initial-mode",
                   "regulator-allow-set-load", "regulator-state-mem", "gpio")]
        faults += [(REG + "/vbuck2", "status", b"disabled\0"),
                   (REG + "/vbuck2", "regulator-min-microvolt", ints([800000])),
                   (REG + "/vbuck2", "regulator-max-microvolt", ints([800000])),
                   ("/modem", "md-vmodem-supply", ints([200])),
                   ("/modem", "md-vsram-supply", ints([101])),
                   ("/modem", "md-vdigrf-supply", ints([202])),
                   ("/modem", "md-vmodem", ints([700000, 700000])),
                   ("/modem", "ccci-topckgen", ints([42])),
                   ("/modem", "ccci-topckgen", ints([7, 0])),
                   ("/modem", "ccci-topckgen", ints([999])),
                   ("/modem", "status", b"okay\0"),
                   ("/modem", "power-domains", ints([7, 0]))]
        for path, prop, value in faults:
            with self.subTest(path=path, prop=prop):
                normal, baseline, candidate = fixture(True)
                candidate[path][prop] = value
                with self.assertRaises(ValueError):
                    rails.validate(normal, baseline, candidate, True)
        with self.assertRaises(ValueError):
            rails.validate(*fixture(True), activate=False)

    def test_typed_phandle_renumbering_and_alias_errors(self):
        normal, baseline, candidate = fixture(True)
        candidate["/topckgen"]["phandle"] = ints([70])
        candidate["/display"]["clocks"] = ints([70, 19])
        candidate["/modem"]["ccci-topckgen"] = ints([70])
        candidate[REG + "/vcn13"]["phandle"] = ints([110])
        candidate["/connectivity"]["vcn13-supply"] = ints([110])
        rails.validate(normal, baseline, candidate, True)
        candidate[REG + "/vcn13"]["linux,phandle"] = ints([101])
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            rails.validate(normal, baseline, candidate, True)
        normal, baseline, candidate = fixture(True)
        for tree in (normal, baseline, candidate):
            tree["/unused-owner"] = {"phandle": ints([310]), "status": b"disabled\0"}
        candidate["/unused-owner"].pop("phandle")
        with self.assertRaisesRegex(ValueError, "ownership"):
            rails.validate(normal, baseline, candidate, True)


if __name__ == "__main__":
    unittest.main()
