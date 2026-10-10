#!/usr/bin/env python3
"""Bound-parent source order and matching vendor resource checks; no compiler."""
import os
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = (HERE / "mt6878-gpueb-control.c").read_text()
        cls.body = cls.code.split("int mt6878_gpueb_control_prepare(", 1)[1].split("EXPORT_SYMBOL", 1)[0]

    def test_source_backed_resources(self):
        tree = Path(os.environ.get("TETRIS_DEVICE_MODULES_TREE", str(
            ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878")))
        source = subprocess.check_output(["git", "-C", str(tree), "show",
            "ee2be53cb75670b548948636a0db1d1ff112bf12:arch/arm64/boot/dts/mediatek/mt6878.dts"], text=True)
        node = source.split('compatible = "mediatek,gpueb"', 1)[1].split("};", 1)[0]
        for value in ("13c00000", "13c60000", "gpueb_base", "gpueb_reg_base", "mbox0"):
            self.assertIn(value, node.lower())
        self.assertIn("GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE - 1", self.body)
        self.assertIn("IRQ_TYPE_LEVEL_HIGH", self.body)

    def test_owned_preflight_before_resume(self):
        resume = self.body.index("mt6878_gpueb_mfg0_resume(control->power)")
        for operation in ("mt6878_gpueb_mfg0_prepare(parent", "platform_get_resource_byname",
                          "of_property_read_u32", "platform_get_irq_byname", "irq_get_trigger_type",
                          "mt6878_gpueb_sram_create", "*result = control"):
            self.assertLess(self.body.index(operation), resume)
        self.assertLess(resume, self.body.index("mt6878_gpueb_reset_provider_register"))
        self.assertLess(self.body.index("mt6878_gpueb_reset_provider_register"),
                        self.body.index("mt6878_gpueb_mfg0_finish"))

    def test_no_duplicate_bank_claim_or_execution(self):
        for call in ("request_mem_region(", "ioremap(", "request_irq(", "writel(",
                     "readl(", "rproc_boot(", "reset_control_assert(",
                     "mt6878_gpueb_reset_provider_stop(", "regulator_enable(", "arm_smccc"):
            self.assertNotIn(call, self.code)
        self.assertNotIn("platform_driver_register(", self.code)
        self.assertNotIn("platform_set_drvdata(", self.code)

    def test_failed_owner_cannot_be_retried_or_freed(self):
        self.assertIn("if (*result)\n\t\treturn -EALREADY", self.body)
        for call in ("mt6878_gpueb_mfg0_resume", "mt6878_gpueb_reset_provider_register"):
            tail = self.body.split(call, 1)[1].split("mt6878_gpueb_mfg0_finish", 1)[0]
            self.assertIn("return retain_failure(control, ret)", tail)
        retain = self.code.split("static int retain_failure", 1)[1].split(
            "int mt6878_gpueb_control_prepare", 1)[0]
        self.assertIn("mt6878_gpueb_sram_unknown_start", retain)
        self.assertIn("mt6878_gpueb_mfg0_quarantine", retain)
        for forbidden in ("kfree", "sram_destroy", "pm_runtime_put", "reset_provider_stop"):
            self.assertNotIn(forbidden, retain)

    def test_pre_resume_failure_finishes_scope(self):
        cleanup = self.body.split("finish:\n", 1)[1]
        self.assertLess(cleanup.index("mt6878_gpueb_mfg0_finish"), cleanup.index("kfree(control)"))
        self.assertIn("*result = control", cleanup)
        self.assertIn("mt6878_gpueb_mfg0_quarantine", cleanup)


if __name__ == "__main__":
    unittest.main()
