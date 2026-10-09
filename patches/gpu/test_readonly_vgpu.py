#!/usr/bin/env python3
"""Check the next-snapshot read-only observer without altering r176 fixtures."""
import subprocess
import unittest

from test_supply_inventory import SupplyInventory, patch, SUPPLIES
from prepare_native import definition


class ReadOnlyObserver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SupplyInventory.setUpClass()
        cls.addClassCleanup(SupplyInventory.tmp.cleanup)
        check = SupplyInventory("test_partial_provider_cannot_write_unowned_phases")
        check.test_partial_provider_cannot_write_unowned_phases()
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                       cwd=SupplyInventory.tree,
                       input=patch("0114-regulator-mt6315-read-only-vgpu-observer.patch"),
                       text=True, capture_output=True, check=True)
        cls.source = (SupplyInventory.tree / "drivers/regulator/mt6315-regulator.c").read_text()

    def test_regmap_write_boundary(self):
        block = definition(self.source, "static bool mt6315_vgpu_writeable_reg(")
        self.assertIn("return false;", block)
        self.assertEqual(block.count("return "), 1)
        config = definition(self.source, "static const struct regmap_config mt6315_vgpu_observer_config")
        self.assertIn(".cache_type = REGCACHE_NONE", config)
        self.assertIn(".writeable_reg = mt6315_vgpu_writeable_reg", config)
        self.assertIn(".readable_reg = mt6315_vgpu_readable_reg", config)

    def test_observer_bypasses_constraint_and_shutdown_writes(self):
        observer = definition(self.source, "static int mt6315_observe_vgpu(")
        self.assertIn("&mt6315_vgpu_observer_config", observer)
        for forbidden in ("regmap_write", "regmap_update_bits", "regulator_register"):
            self.assertNotIn(forbidden, observer)
        probe = definition(self.source, "static int mt6315_regulator_probe(")
        self.assertLess(probe.index("return mt6315_observe_vgpu(pdev)"),
                        probe.index("mt6315_described_rails(dev)"))
        shutdown = definition(self.source, "static void mt6315_regulator_shutdown(")
        self.assertLess(shutdown.index("return;"), shutdown.index("mt6315_prepare_poweroff"))

    def test_dt_stays_disabled(self):
        source = (SupplyInventory.tree / SUPPLIES).read_text()
        self.assertEqual(source.count('status = "disabled";'), 3)
        self.assertIn("mediatek,observe-vgpu-only;", source)
        self.assertNotIn('status = "okay";', source)


if __name__ == "__main__":
    unittest.main()
