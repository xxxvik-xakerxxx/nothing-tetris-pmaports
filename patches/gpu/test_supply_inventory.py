#!/usr/bin/env python3
"""Static GPU supply regression checks; native compilation belongs in CI."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
DRIVER = "drivers/regulator/mt6363-regulator.c"
HEADER = "include/linux/mfd/mt6363/registers.h"
NATIVE = "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dts"
SUPPLIES = "arch/arm64/boot/dts/mediatek/mt6878-tetris-gpu-supplies.dtsi"


def patch(name):
    return (PATCHES / name).read_text()


def new_file(text, path):
    """Extract an existing added-file fixture without a kernel checkout."""
    tail = text.split("+++ b/" + path + "\n", 1)[1]
    lines = tail.splitlines()[1:]
    content = []
    for line in lines:
        if not line.startswith("+"):
            break
        content.append(line[1:])
    return "\n".join(content) + "\n"


class SupplyInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="tetris-gpu-supplies-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.tree = Path(cls.tmp.name)
        inputs = {
            DRIVER: "0008-connectivity-mt6878-mt6631-connsys.patch",
            HEADER: "0003-mfd-mt6363-keys-mt6375-telemetry.patch",
            NATIVE: "0072-arm64-dts-mediatek-add-Nothing-Tetris-native-display-DTB.patch",
        }
        for path, source in inputs.items():
            target = cls.tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_file(patch(source), path))
        header_patch = patch("0008-connectivity-mt6878-mt6631-connsys.patch")
        header_patch = "--- a/" + HEADER + "\n" + header_patch.split(
            "--- a/" + HEADER + "\n", 1)[1].split("\n--- a/", 1)[0] + "\n"
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"], cwd=cls.tree,
                       input=header_patch, text=True, capture_output=True, check=True)
        for name in (
            "0030-regulator-mediatek-mt6878-gpu-rails.patch",
            "0112-arm64-dts-tetris-disabled-gpu-supplies.patch",
        ):
            result = subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1"], cwd=cls.tree,
                input=patch(name), text=True, capture_output=True,
            )
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
        cls.driver = (cls.tree / DRIVER).read_text()
        cls.supplies = (cls.tree / SUPPLIES).read_text()

    def test_disabled_child_released_before_skip(self):
        # Check the actual patched production block, not a copied predicate.
        block = self.driver.split("of_get_child_by_name", 1)[1]
        self.assertRegex(block, r"available = of_device_is_available\(np\);")
        self.assertLess(block.index("of_node_put(np)"), block.index("if (!available)"))
        self.assertLess(block.index("if (!available)"), block.index("devm_regulator_register"))
        self.assertNotIn("if (!np)", block)

    def test_voltage_selector_and_settle_time(self):
        rail = self.driver.split('.name = "vsram-cpum"', 1)[1].split("},", 1)[0]
        self.assertIn(".enable_time = 180", rail)
        self.assertIn(".vsel_mask = GENMASK(6, 0)", rail)
        self.assertIn("REGULATOR_LINEAR_RANGE(400000, 0, 0x7f, 6250)", self.driver)
        self.assertEqual(400000 + 127 * 6250, 1193750)

    def test_board_inventory_stays_disabled(self):
        self.assertEqual(self.supplies.count('status = "disabled";'), 3)
        self.assertNotIn('status = "okay"', self.supplies)
        for unsafe in ("regulator-always-on", "regulator-boot-on", "regulator-initial-mode",
                       "-supply", "opp-table", "vbuck1 {", "vbuck4 {"):
            self.assertNotIn(unsafe, self.supplies)
        self.assertIn("reg = <0x6 SPMI_USID>", self.supplies)
        self.assertIn("mediatek,buck1-mode-mask = <0x1>", self.supplies)
        self.assertIn('"mediatek,mt6319-regulator",', self.supplies)
        self.assertIn('"mediatek,mt6315-regulator";', self.supplies)

    def test_native_board_includes_inventory_once(self):
        text = (self.tree / NATIVE).read_text()
        self.assertEqual(text.count('#include "mt6878-tetris-gpu-supplies.dtsi"'), 1)

    def test_provider_filters_remain_required(self):
        text = patch("0110-regulator-mt6315-register-described-rails.patch")
        self.assertIn("of_device_is_available(child)", text)
        self.assertIn("if (!(mask & BIT(i)))", text)
        self.assertIn("return mask ? mask : -ENODEV;", text)

    def test_partial_provider_cannot_write_unowned_phases(self):
        kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        source = kernel / "drivers/regulator/mt6315-regulator.c"
        binding = "Documentation/devicetree/bindings/regulator/mt6315-regulator.yaml"
        if not source.exists():
            self.skipTest("Set TETRIS_KERNEL_TREE to the unpatched pinned kernel for stack check")
        for relative in ("drivers/regulator/mt6315-regulator.c", binding):
            target = self.tree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((kernel / relative).read_text())
        for name in (
            "0108-regulator-mt6315-board-mode-mask.patch",
            "0109-regulator-mt6315-stop-mode-change-on-read-error.patch",
            "0110-regulator-mt6315-register-described-rails.patch",
            "0111-regulator-mt6315-fail-closed-shutdown.patch",
            "0113-regulator-mt6315-reject-unowned-phase-mask.patch",
        ):
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                    cwd=self.tree, input=patch(name), text=True,
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (self.tree / "drivers/regulator/mt6315-regulator.c").read_text()
        probe = text.split("static int mt6315_regulator_probe", 1)[1]
        guard = "mt6315_mode_mask_owned(dev, mask,"
        self.assertIn(guard, probe)
        self.assertLess(probe.index(guard), probe.index("devm_regulator_register"))
        self.assertIn("BUCK mode mask includes unowned rails", probe)
        self.assertNotIn("modeset_mask[MT6315_VBUCK1] &=", probe)

    def test_existing_dt_has_no_explicit_phase_override(self):
        kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        directory = kernel / "arch/arm64/boot/dts/mediatek"
        if not directory.is_dir():
            self.skipTest("Set TETRIS_KERNEL_TREE for existing-provider DT audit")
        providers = 0
        for path in directory.iterdir():
            if path.suffix not in (".dts", ".dtsi", ".dtso"):
                continue
            text = path.read_text()
            if '"mediatek,mt6315-regulator"' in text:
                providers += text.count('"mediatek,mt6315-regulator"')
                self.assertNotIn("mediatek,buck1-mode-mask", text, path)
        self.assertGreater(providers, 0)

    def test_patch_hunk_counts(self):
        for name in ("0030-regulator-mediatek-mt6878-gpu-rails.patch",
                     "0112-arm64-dts-tetris-disabled-gpu-supplies.patch",
                     "0113-regulator-mt6315-reject-unowned-phase-mask.patch"):
            lines = patch(name).splitlines()
            for index, line in enumerate(lines):
                match = re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", line)
                if not match:
                    continue
                old = new = 0
                for body in lines[index + 1:]:
                    if not body or body.startswith(("@@", "diff ", "---", "-- ")):
                        break
                    if body.startswith(" "):
                        old += 1
                        new += 1
                    elif body.startswith("+"):
                        new += 1
                    elif body.startswith("-"):
                        old += 1
                    else:
                        break
                self.assertEqual((old, new), (int(match[2]), int(match[4])), (name, line))


if __name__ == "__main__":
    unittest.main()
