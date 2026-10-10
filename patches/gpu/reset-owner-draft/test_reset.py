#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static production API/source validation. No local native compilation."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prepare_native import definition
from test_gpueb_power import vendor, ROOT


class Reset(unittest.TestCase):
    def setUp(self):
        self.code = (HERE / "mt6878-gpueb-reset.c").read_text()

    def test_concrete_prepare_without_power_transition(self):
        body = definition(self.code, "struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(")
        for token in ("pm_runtime_get_if_in_use(&parent->dev)", "GPUEB_WINDOW_GPR",
                      "GPUEB_WINDOW_MBOX", "MT6878_POWER_DOMAIN_MFG0_SHUTDOWN",
                      '"mediatek,mt6878-power-controller"', "request_mem_region(",
                      "request_irq(irq, unexpected_irq, IRQF_NO_AUTOEN",
                      "try_module_get(THIS_MODULE)"):
            self.assertIn(token, body)
        for token in ("writel(", "readl(", "pm_runtime_resume", "pm_runtime_set_active",
                      "regulator_enable", "clk_prepare_enable", "IRQF_SHARED"):
            self.assertNotIn(token, body)

    def test_reset_mmio_and_error_are_serialized(self):
        body = definition(self.code, "int mt6878_gpueb_reset_hold(")
        lock = body.index("spin_lock_irqsave(")
        self.assertLess(lock, body.index("ret = scope->first_error;"))
        self.assertLess(body.index("scope->reset_written = true;"), body.index("writel(0,"))
        self.assertLess(body.index("readl("), body.index("spin_unlock_irqrestore("))
        self.assertEqual(body.count("writel("), 1)
        self.assertIn("scope->first_error = -EIO;", body)
        self.assertGreater(body.index("mt6878_gpueb_sram_unknown_start("),
                           body.index("spin_unlock_irqrestore("))

    def test_no_false_off_or_start(self):
        for token in ("arm_smccc", "enable_irq(", "memset_io(", "memcpy_toio(",
                      "BOOTREADY", "0x3f00000b", "rproc_ops", "of_genpd_add_provider"):
            # No executable start/provider code exists in this reset checkpoint.
            if token != "BOOTREADY":
                self.assertNotIn(token, self.code)
        body = definition(self.code, "int mt6878_gpueb_reset_destroy(")
        self.assertLess(body.index("if (scope->reset_written || ret)"), body.index("free_irq("))
        self.assertIn("return ret ?: -EBUSY;", body)
        self.assertIn("module_put(THIS_MODULE)", body)

    def test_source_backed_bank(self):
        text = vendor("arch/arm64/boot/dts/mediatek/mt6878.dts")
        start = text.index('compatible = "mediatek,gpueb"')
        node = text[start:start + 5500]
        self.assertIn("0x13c60000", node)
        self.assertIn("0x2000", node)
        self.assertIn("GIC_SPI 273 IRQ_TYPE_LEVEL_HIGH", node)
        self.assertIn('"gpueb_reg_base"', node)
        self.assertIn('"mbox0"', node)

    def test_actual_kernel_pm_api(self):
        tree = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        api = (tree / "include/linux/pm_runtime.h").read_text()
        self.assertIn("pm_runtime_get_if_in_use(struct device *dev)", api)
        code = (tree / "drivers/base/power/runtime.c").read_text()
        get = definition(code, "int pm_runtime_get_if_in_use(")
        self.assertIn("pm_runtime_get_conditional(dev, false)", get)

    @unittest.skipUnless(os.environ.get("TETRIS_B41_LK"), "private LK not supplied")
    def test_actual_reset_and_copy_loop(self):
        from audit_gpueb_b41 import signed_lk
        from audit_gpueb_lk import expect
        code = signed_lk(Path(os.environ["TETRIS_B41_LK"]).read_bytes())
        for check in ((0x1edb0, "movk", "x22, #0x13c6, lsl #16"),
                      (0x1eda8, "mov", "x22, #0x600"),
                      (0x1edf8, "str", "wzr, [x22]"),
                      (0x1ee00, "mov", "w8, #0xf2bc"),
                      (0x1ee04, "movk", "w8, #3, lsl #16"),
                      (0x1ee0c, "sub", "w8, w8, #4"),
                      (0x1ee10, "cmp", "w8, #4"),
                      (0x1ee18, "b.hi", "#0x1ee08")):
            expect(code, *check)
        remaining = 0x3f2bc
        iterations = 0
        while True:
            iterations += 1
            remaining -= 4
            if remaining <= 4:
                break
        self.assertEqual(iterations, 64686)
        self.assertEqual(iterations * 4 - 156064, 102680)

    def test_shell(self):
        result = subprocess.run(["sh", "-n", str(HERE / "smoke-kernel-ci.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
