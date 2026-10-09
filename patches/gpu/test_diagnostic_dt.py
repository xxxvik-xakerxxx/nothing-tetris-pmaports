#!/usr/bin/env python3
import copy
import unittest
import os
from pathlib import Path
import subprocess

from check_diagnostic_dt import validate_trees
import test_readonly_vgpu as readonly
import test_supply_inventory as inventory


class DiagnosticDelta(unittest.TestCase):
    def setUp(self):
        self.observer = "/soc/spmi@1c00d000/pmic@6"
        self.normal = {
            "/": {"compatible": b"nothing,tetris\0mediatek,mt6878\0", "model": b"Nothing CMF Phone 1\0"},
            "/chosen": {},
            self.observer: {"compatible": b"mediatek,mt6319-regulator\0mediatek,mt6315-regulator\0",
                            "reg": b"\0\0\0\x06\0\0\0\0", "status": b"disabled\0",
                            "mediatek,observe-vgpu-only": b""},
            self.observer + "/regulators": {},
            self.observer + "/regulators/vbuck2": {"status": b"disabled\0"},
            "/soc/spmi@1c00d000/pmic@4/regulators/vsram-cpum": {"status": b"disabled\0"},
        }
        self.diagnostic = copy.deepcopy(self.normal)
        self.diagnostic["/"]["model"] = b"Nothing CMF Phone 1 (VGPU read-only diagnostic)\0"
        self.diagnostic["/chosen"]["tetris,vgpu-observe-diagnostic"] = b""
        self.diagnostic[self.observer]["status"] = b"okay\0"

    def test_exact_delta(self):
        self.assertEqual(validate_trees(self.normal, self.diagnostic), self.observer)

    def test_wrong_board_rejected(self):
        self.diagnostic["/"]["compatible"] = b"other,phone\0mediatek,mt6878\0"
        with self.assertRaises(ValueError):
            validate_trees(self.normal, self.diagnostic)

    def test_wrong_usid_rejected(self):
        self.normal[self.observer]["reg"] = b"\0\0\0\x05\0\0\0\0"
        with self.assertRaises(ValueError):
            validate_trees(self.normal, self.diagnostic)

    def test_rail_activation_rejected(self):
        self.diagnostic[self.observer + "/regulators/vbuck2"]["status"] = b"okay\0"
        with self.assertRaises(ValueError):
            validate_trees(self.normal, self.diagnostic)

    def test_missing_observer_flag_rejected(self):
        del self.diagnostic[self.observer]["mediatek,observe-vgpu-only"]
        with self.assertRaises(ValueError):
            validate_trees(self.normal, self.diagnostic)

    def test_new_gpu_node_rejected(self):
        self.diagnostic["/soc/gpu@13000000"] = {"status": b"okay\0"}
        with self.assertRaises(ValueError):
            validate_trees(self.normal, self.diagnostic)

    def test_diagnostic_patch_applies_without_fuzz(self):
        readonly.ReadOnlyObserver.setUpClass()
        try:
            kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
                inventory.ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
            relative = "arch/arm64/boot/dts/mediatek/Makefile"
            target = inventory.SupplyInventory.tree / relative
            target.write_text((kernel / relative).read_text())
            text = inventory.patch("0072-arm64-dts-mediatek-add-Nothing-Tetris-native-display-DTB.patch")
            start = text.index("diff --git a/" + relative)
            section = text[start:].split("\ndiff --git ", 1)[0] + "\n"
            for content in (section, inventory.patch("0115-arm64-dts-tetris-vgpu-observer-diagnostic.patch")):
                result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                        cwd=inventory.SupplyInventory.tree,
                                        input=content, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = (target.parent / "mt6878-nothing-tetris-vgpu-observe.dts").read_text()
            self.assertEqual(source.count('status = "okay"'), 1)
            self.assertIn('#include "mt6878-nothing-tetris-native.dts"', source)
            self.assertIn("mediatek,observe-vgpu-only;", source)
            self.assertNotIn("&mt6363_vsram_cpum", source)
        finally:
            inventory.SupplyInventory.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
