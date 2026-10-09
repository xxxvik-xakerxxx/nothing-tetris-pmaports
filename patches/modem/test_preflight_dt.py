#!/usr/bin/env python3
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from check_preflight_dt import check_native_baseline, validate_trees, reference_value, phandle_owners

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"


def cells(*values):
    return b"".join(value.to_bytes(4, "big") for value in values)


class PreflightDelta(unittest.TestCase):
    def setUp(self):
        self.spm = "/soc@0/syscon@1c001000"
        self.ifr = "/soc@0/syscon@10001000"
        self.nemi = "/soc@0/syscon@10270000"
        self.observer = self.spm + "/modem-preflight"
        self.gpu = "/soc@0/spmi@1c00d000/pmic@6"
        self.off = {
            "/": {"compatible": b"nothing,tetris\0mediatek,mt6878\0",
                  "model": b"Nothing CMF Phone 1 (native display)\0"},
            "/chosen": {},
            self.spm: {"compatible": b"mediatek,mt6878-scpsys\0syscon\0simple-mfd\0",
                       "reg": cells(0x1c001000, 0x1000)},
            self.ifr: {"compatible": b"mediatek,mt6878-infracfg-ao\0syscon\0",
                       "reg": cells(0x10001000, 0x1000), "phandle": cells(11)},
            self.nemi: {"compatible": b"mediatek,mt6878-nemicfg_ao_mem_reg_bus\0syscon\0",
                        "reg": cells(0x10270000, 0x1000), "phandle": cells(12), "status": b"disabled\0"},
            self.observer: {"compatible": b"mediatek,mt6878-modem-preflight\0",
                            "access-controllers": cells(11, 12), "status": b"disabled\0"},
            self.gpu: {"compatible": b"mediatek,mt6319-regulator\0", "status": b"disabled\0"},
        }
        self.on = copy.deepcopy(self.off)
        self.on["/"]["model"] = b"Nothing CMF Phone 1 (modem read-only preflight)\0"
        self.on["/chosen"]["tetris,modem-preflight-diagnostic"] = b""
        self.on[self.observer]["status"] = b"okay\0"
        self.normal = {path: copy.deepcopy(props) for path, props in self.off.items()
                       if path not in (self.nemi, self.observer)}

    def reject(self):
        with self.assertRaises(ValueError):
            validate_trees(self.off, self.on)

    def test_exact_delta(self):
        self.assertEqual(validate_trees(self.off, self.on), self.observer)
        self.assertEqual(check_native_baseline(self.normal, self.off), self.observer)

    def reject_baseline(self):
        with self.assertRaises(ValueError):
            check_native_baseline(self.normal, self.off)

    def test_baseline_existing_property_add_remove_change(self):
        for mutation in [lambda: self.off[self.spm].update({"new-property": b""}),
                         lambda: self.off[self.ifr].pop("compatible"),
                         lambda: self.off[self.ifr].update({"reg": cells(0x10002000, 0x1000)})]:
            saved = copy.deepcopy(self.off)
            mutation()
            self.reject_baseline()
            self.off = saved

    def test_baseline_existing_phandle_renumbering(self):
        self.off[self.ifr]["phandle"] = cells(20)
        self.off[self.observer]["access-controllers"] = cells(20, 12)
        self.assertEqual(check_native_baseline(self.normal, self.off), self.observer)

    def test_baseline_reference_target_change(self):
        for tree in (self.normal, self.off):
            tree["/client"] = {"pinctrl-0": cells(11), "reg": cells(11)}
        self.off["/client"]["pinctrl-0"] = cells(12)
        self.reject_baseline()

    def test_baseline_raw_integer_not_phandle(self):
        self.normal[self.ifr]["untyped-value"] = cells(11)
        self.off[self.ifr]["untyped-value"] = cells(20)
        self.off[self.ifr]["phandle"] = cells(20)
        self.off[self.observer]["access-controllers"] = cells(20, 12)
        self.reject_baseline()

    def test_reference_specifier_args_preserved(self):
        for tree, handle in ((self.normal, 11), (self.off, 20)):
            tree[self.ifr]["phandle"] = cells(handle)
            tree[self.ifr]["#clock-cells"] = cells(1)
            tree["/client"] = {"clocks": cells(handle, 7)}
        self.off[self.observer]["access-controllers"] = cells(20, 12)
        self.assertEqual(check_native_baseline(self.normal, self.off), self.observer)
        self.off["/client"]["clocks"] = cells(20, 8)
        self.reject_baseline()

    def test_typed_reference_malformed(self):
        self.off[self.ifr]["#clock-cells"] = cells(1)
        for data in (cells(11), cells(99, 1), b"\0"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                reference_value(self.off, phandle_owners(self.off), "clocks", data)

    def test_baseline_new_phandle_on_existing_node(self):
        self.off[self.spm]["phandle"] = cells(99)
        self.reject_baseline()

    def test_baseline_existing_node_removal(self):
        del self.off[self.gpu]
        self.reject_baseline()

    def test_baseline_extra_node(self):
        self.off[self.spm + "/extra-disabled-node"] = {"status": b"disabled\0"}
        self.reject_baseline()

    def test_baseline_exact_new_node_properties(self):
        for path in (self.observer, self.nemi):
            for prop, value in [("status", b"okay\0"), ("resets", cells(1)),
                                ("compatible", b"different,driver\0"), ("arbitrary", b"")]:
                with self.subTest(path=path, prop=prop):
                    saved = copy.deepcopy(self.off)
                    self.off[path][prop] = value
                    self.reject_baseline()
                    self.off = saved

    def test_baseline_wrong_new_resource(self):
        self.off[self.nemi]["reg"] = cells(0x10270000, 0x2000)
        self.reject_baseline()

    def test_baseline_missing_new_node_property(self):
        for path, properties in [(self.nemi, ("status", "compatible", "reg")),
                                 (self.observer, ("status", "compatible", "access-controllers"))]:
            for prop in properties:
                with self.subTest(path=path, prop=prop):
                    saved = copy.deepcopy(self.off)
                    del self.off[path][prop]
                    self.reject_baseline()
                    self.off = saved

    def test_baseline_missing_or_wrong_new_node(self):
        self.off[self.nemi + "-other"] = self.off.pop(self.nemi)
        self.reject_baseline()

    def test_baseline_missing_phandle(self):
        del self.off[self.nemi]["phandle"]
        self.reject_baseline()

    def test_baseline_reversed_refs(self):
        self.off[self.observer]["access-controllers"] = cells(12, 11)
        self.reject_baseline()

    def test_baseline_invalid_phandle_values(self):
        for value in (0, 0xffffffff, 11):
            with self.subTest(value=value):
                self.off[self.nemi]["phandle"] = cells(value)
                self.reject_baseline()

    def test_baseline_new_node_phandle_aliases(self):
        self.off[self.nemi]["linux,phandle"] = cells(12)
        self.off[self.observer]["phandle"] = cells(13)
        self.assertEqual(check_native_baseline(self.normal, self.off), self.observer)
        self.off[self.nemi]["linux,phandle"] = cells(99)
        self.reject_baseline()

    def test_baseline_unresolved_ref(self):
        self.off[self.observer]["access-controllers"] = cells(11, 99)
        self.reject_baseline()

    def test_baseline_malformed_phandle(self):
        self.off[self.nemi]["phandle"] = cells(12, 13)
        self.reject_baseline()

    def test_baseline_malformed_access_controllers(self):
        for value in (b"", b"\0\0\0", cells(11), cells(11, 11), cells(11, 12, 13)):
            with self.subTest(value=value):
                self.off[self.observer]["access-controllers"] = value
                self.reject_baseline()

    def test_baseline_wrong_identity(self):
        self.normal["/"]["compatible"] = self.off["/"]["compatible"] = b"other,phone\0mediatek,mt6878\0"
        self.reject_baseline()

    def test_baseline_wrong_existing_resource(self):
        self.normal[self.spm]["reg"] = self.off[self.spm]["reg"] = cells(0x1c002000, 0x1000)
        self.reject_baseline()

    def test_other_display_delta(self):
        self.on[self.spm]["unrelated-display-setting"] = cells(1)
        self.reject()

    def test_wrong_board(self):
        self.on["/"]["compatible"] = b"other,phone\0mediatek,mt6878\0"
        self.reject()

    def test_gpu_enabled_same_boot(self):
        for tree in (self.off, self.on):
            tree[self.gpu]["status"] = b"okay\0"
        self.reject()

    def test_gpu_diagnostic_combined(self):
        self.on["/chosen"]["tetris,vgpu-observe-diagnostic"] = b""
        self.reject()

    def test_power_provider_present_even_disabled(self):
        for tree in (self.off, self.on):
            tree[self.spm + "/power-controller-modem"] = {
                "compatible": b"mediatek,mt6878-modem-power-controller\0", "status": b"disabled\0"}
        self.reject()

    def test_managed_resources(self):
        for path, prop in [(self.observer, "power-domains"), (self.spm, "resets"),
                           (self.ifr, "clocks"), (self.nemi, "hwlocks")]:
            with self.subTest(path=path, prop=prop):
                saved_off, saved_on = copy.deepcopy(self.off), copy.deepcopy(self.on)
                self.off[path][prop] = self.on[path][prop] = cells(1)
                self.reject()
                self.off, self.on = saved_off, saved_on

    def test_wrong_resource_address_or_size(self):
        for path in [self.spm, self.ifr, self.nemi]:
            with self.subTest(path=path):
                original = self.off[path]["reg"]
                self.off[path]["reg"] = self.on[path]["reg"] = cells(0x10271000, 0x2000)
                self.reject()
                self.off[path]["reg"] = self.on[path]["reg"] = original

    def test_reversed_access_controllers(self):
        self.off[self.observer]["access-controllers"] = self.on[self.observer]["access-controllers"] = cells(12, 11)
        self.reject()

    def test_unresolved_phandle(self):
        self.on[self.observer]["access-controllers"] = cells(11, 99)
        self.reject()

    def test_duplicate_phandle(self):
        self.on[self.nemi]["phandle"] = cells(11)
        self.reject()

    def test_child_domain(self):
        for tree in (self.off, self.on):
            tree[self.observer + "/power-domain@0"] = {"reg": cells(0), "status": b"disabled\0"}
        self.reject()

    def test_nemi_device_enable(self):
        self.on[self.nemi]["status"] = b"okay\0"
        self.reject()

    def test_patch_without_gpu_dependency(self):
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("powercheck", ROOT / "scripts/check-mt6878-modem-power.py")
        power = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(power)
        power.FILES.update({"arch/arm64/boot/dts/mediatek/Makefile",
                           "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-modem-preflight-off.dts",
                           "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-modem-preflight.dts"})
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            target = out / "arch/arm64/boot/dts/mediatek/Makefile"
            target.parent.mkdir(parents=True)
            kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
                ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
            target.write_text((kernel / "arch/arm64/boot/dts/mediatek/Makefile").read_text())
            for name in ["0072-arm64-dts-mediatek-add-Nothing-Tetris-native-display-DTB.patch",
                         "0116-arm64-dts-tetris-modem-preflight-diagnostic.patch"]:
                selected = "".join(power.sections((PACKAGE / name).read_text()))
                subprocess.run(["git", "apply", "-"], cwd=out, input=selected, text=True, check=True)
            baseline = (target.parent / "mt6878-nothing-tetris-modem-preflight-off.dts").read_text()
            enabled = (target.parent / "mt6878-nothing-tetris-modem-preflight.dts").read_text()
            self.assertIn('#include "mt6878-disabled-modem-preflight.dtsi"', baseline)
            self.assertEqual(enabled.count('status = "okay";'), 1)
            self.assertIn("&md_preflight", enabled)
            self.assertNotIn("&mt6319_gpu", enabled)


if __name__ == "__main__":
    unittest.main()
