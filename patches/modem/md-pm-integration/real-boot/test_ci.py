#!/usr/bin/env python3
"""CI admission/order and real patch checks, with no local native execution."""

import json
import os
import re
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import ci
import stage


class RealOnCITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pristine = stage.REPO.parent / ("linux-" + stage.LINUX)
        cls.temp = tempfile.TemporaryDirectory(prefix="tetris-real-on-ci-tests-")
        cls.kernel = Path(cls.temp.name)
        stage.baseline(cls.pristine, cls.kernel)
        rail_stage = ci.module("real_on_test_packaged_rail", "patches/modem/md-pmic-supplier/stage.py")
        rail_stage.packaged(cls.kernel)
        for name in ("drivers/regulator/core.c", "drivers/regulator/of_regulator.c"):
            target = cls.kernel / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cls.pristine / name, target)
        board = cls.kernel / ("arch/arm64/boot/dts/mediatek/" + stage.parent.BOARD + ".dts")
        board.parent.mkdir(parents=True, exist_ok=True)
        board.write_text(stage.parent.frozen(
            "patches/modem/drafts/runtime-hif-dt/mt6878-nothing-tetris-ccci-hif-resources.dts").decode()
            + stage.parent.SUPPLIER_DTS)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_current_r188_source_contract(self):
        self.assertEqual(ci.source_contract(self.pristine), json.loads(ci.CONTRACT.read_text()))

    def test_r188_prepared_kernel_and_actual_rail_inputs(self):
        prefix, delta, profile = ci.check(self.kernel, "r188")
        self.assertEqual(profile["kernel_package"], "7.2.1-r188")
        self.assertEqual(profile["connectivity_commit"], "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835")
        self.assertEqual([name for name, _ in prefix][-2:],
            ["0184-native-modem-single-ack.patch", "0187-native-modem-wakeup-sleep-veto.patch"])
        self.assertEqual([name for name, _ in delta], ["0185-native-modem-rails.patch",
            "0186-native-modem-rails-registration-dt.patch", "0188-native-modem-real-on.patch"])

    def test_packaged_normal_smoke_input_applies_complete_r188_rail_on_chain(self):
        with tempfile.TemporaryDirectory(prefix="tetris-real-on-packaged-") as directory:
            copy = Path(directory)
            stage.native.packaged(self.pristine, copy)
            fixture_paths = (stage.KCONFIG, stage.PREFIX + "Makefile",
                         "Documentation/devicetree/bindings/power/mediatek,power-controller.yaml",
                         "arch/arm64/boot/dts/mediatek/Makefile")
            for name in fixture_paths:
                target = copy / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.pristine / name, target)
            names = list(dict.fromkeys(re.findall(r"^\s+([\w.-]+\.patch)$",
                (stage.native.PACKAGE / "APKBUILD").read_text(), re.M)))
            for name in names:
                raw = (stage.native.PACKAGE / name).read_text(encoding="latin-1")
                selected = "".join(part for part in re.split(r"(?=^diff --git )", raw, flags=re.M)
                    if any(part.startswith("diff --git a/" + path + " b/" + path + "\n")
                           for path in fixture_paths))
                if selected:
                    ci.apply_source(copy, selected.encode())
            rail_stage = ci.module("real_on_test_packaged_rail_full", "patches/modem/md-pmic-supplier/stage.py")
            rail_stage.packaged(copy)
            prefix, delta, _ = ci.check(copy, "packaged")
            for name, data in prefix + delta:
                if name.startswith("0188"):
                    ci.apply_source(copy, data, strict=True, check_only=True)
                ci.apply_source(copy, data, strict=name.startswith("0188"))
            self.assertIn("cpu_hotplug_disable();", (copy / stage.ADOPT).read_text())
            self.assertIn("mt6878_md_real_boot_power_on : mt6878_md_adopt_transition",
                          (copy / stage.CFILE).read_text())
            self.assertIn("init_data->constraints.apply_uV = false;",
                          (copy / "drivers/regulator/mt6363-modem-regulator.h").read_text())

    def test_apply_rails_registration_and_real_on_after_wakeup(self):
        _, delta, _ = ci.check(self.kernel, "r188")
        with tempfile.TemporaryDirectory(prefix=".ci-apply-", dir=stage.HERE) as directory:
            copy = Path(directory) / "kernel"
            shutil.copytree(self.kernel, copy)
            for name, data in delta:
                if name.startswith("0188"):
                    stage.apply(copy, data.decode(), check=True)
                    stage.apply(copy, data.decode())
                else:
                    stage.native.apply(copy, data.decode())
            source = (copy / stage.ADOPT).read_text()
            self.assertIn("cpu_hotplug_disable();", source)
            self.assertIn("register_pm_notifier(&mt6878_md_sleep_notifier)", source)
            self.assertIn("!IS_ENABLED(CONFIG_PM_SLEEP)", source)
            self.assertIn("mt6878_md_real_boot_post_off(pd, owner)", source)
            self.assertIn("#define MT6878_MD_ACK BIT(30)",
                          (copy / (stage.PREFIX + "mt6878-modem-pm.h")).read_text())
            registration = (copy / "drivers/regulator/mt6363-modem-regulator.h").read_text()
            self.assertIn("init_data->constraints.apply_uV = false;", registration)
            self.assertIn("return mt6363_md_register(pdev, regmap);",
                          (copy / "drivers/regulator/mt6363-regulator.c").read_text())
            board = (copy / ("arch/arm64/boot/dts/mediatek/" + stage.parent.BOARD + ".dts")).read_text()
            self.assertIn('&mddriver {\n\tstatus = "disabled";', board)
            extra = board[board.index('#include "mt6878-modem-pmic-disabled.dtsi"'):]
            self.assertNotIn('status = "okay";', extra)
            children = (copy / "arch/arm64/boot/dts/mediatek/mt6878-modem-pmic-disabled.dtsi").read_text()
            self.assertEqual(children.count('status = "disabled";'), 3)

    def test_reject_missing_wakeup_or_mixed_real_on_base(self):
        source = self.kernel / stage.ADOPT
        before = source.read_text()
        try:
            source.write_text(before.replace("cpu_hotplug_disable();", "cpu_hotplug_enable();"))
            with self.assertRaises(ValueError):
                ci.check(self.kernel, "r188")
        finally:
            source.write_text(before)

    def test_no_local_prepare_build_or_subprocess_even_with_opt_in(self):
        with patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}), \
             patch.object(ci.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "CI-only"):
                ci.prepare(self.kernel, "r188", True)
            with self.assertRaisesRegex(ValueError, "CI-only"):
                ci.build(self.kernel, "r188", self.kernel / ".config",
                         self.kernel / "out", self.kernel / "report.json", True)
            run.assert_not_called()
        self.assertFalse((self.kernel / "report.json").exists())

    def test_compile_contract_has_both_variants_real_units_and_disabled_dtb(self):
        source = (stage.HERE / "ci.py").read_text()
        self.assertIn("for enabled in (False, True):", source)
        self.assertEqual(ci.OBJECTS, ("drivers/pmdomain/mediatek/mtk-pm-domains.o",
                                     "drivers/regulator/mt6363-regulator.o"))
        self.assertIn('disabled_consumer_rails(dt.read_tree(variant / DTB))', source)
        self.assertIn('result.update(status="passed", phase="complete")', source)
        self.assertIn('result.update(status="failed", error=str(error))', source)
        self.assertIn("SCSI_UFS_MEDIATEK_DBG", ci.DISABLED)
        self.assertTrue(set(stage.wakeup.SLEEP_API) <= set(ci.REQUIRED))

    def test_ir_callbacks_resolve_optimization_suffix_and_alias_pointer(self):
        ir = ('define internal i32 @md_on.llvm.123(ptr %p) { ret i32 0 }\n'
              '@md_on = internal alias i32(ptr), ptr @md_on.llvm.123\n'
              'store ptr @md_on, ptr %power_on\n')
        self.assertEqual(ci.ir_callbacks(ir, ("md_on",))["md_on"]["defined_symbol"], "md_on.llvm.123")
        for wrong in ('declare i32 @md_on(ptr)\nstore ptr @md_on, ptr %p\n',
                      'define internal i32 @md_on(ptr %p) { ret i32 0 }\n',
                      'define internal i32 @other(ptr %p) { ret i32 0 }\nstore ptr @other, ptr %p\n'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                ci.ir_callbacks(wrong, ("md_on",))

    def test_dt_requires_disabled_consumer_and_rails_but_preserves_live_provider(self):
        tree = {"/modem": {"status": b"disabled\0"},
                "/md-spm": {"status": b"okay\0"}, "/md-spm/power-domain@0": {"status": b"okay\0"}}
        for index, (supply, child) in enumerate((("md-vmodem-supply", "vbuck2"),
                ("md-vsram-supply", "vsram-modem"), ("md-vdigrf-supply", "vbuck1")), 1):
            value = index.to_bytes(4, "big")
            tree["/modem"][supply] = value
            tree["/regulators/" + child] = {"phandle": value, "status": b"disabled\0"}
        self.assertEqual(ci.disabled_consumer_rails(tree)["consumer"], "/modem")
        tree["/regulators/vbuck2"]["status"] = b"okay\0"
        with self.assertRaises(ValueError):
            ci.disabled_consumer_rails(tree)


if __name__ == "__main__":
    unittest.main()
