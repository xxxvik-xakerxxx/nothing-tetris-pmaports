#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned source, scopes and lifecycle checks. No native local compilation."""
import os
from pathlib import Path
import re
import subprocess
import unittest

from prepare_native import definition
from test_gpueb_power import vendor
from test_gpueb_session import vendor_tables

HERE = Path(__file__).resolve().parent
SCOPE = HERE / "mmio-scope"


class ScopeTests(unittest.TestCase):
    def test_exact_discrete_control_resources(self):
        node, _ = vendor_tables()
        entries = re.findall(r"<0 (0x[\da-fA-F]+) 0 (0x[\da-fA-F]+)>",
                             node.split("reg =", 1)[1].split(";", 1)[0])
        names = re.findall(r'"([^"\n]+)"', node.split("reg-names =", 1)[1].split(";", 1)[0])
        resources = {name: (int(base, 16), int(size, 16))
                     for name, (base, size) in zip(names, entries)}
        kernel = (SCOPE / "mt6878-gpueb-io.c").read_text()
        controls = re.findall(r'\{ "(mbox0_\w+)",\s*(0x[\da-f]+), GPUEB_IO_\w+ \}', kernel)
        self.assertEqual(len(controls), 4)
        for name, address in controls:
            self.assertEqual(resources[name], (int(address, 16), 4))
        self.assertNotIn("0x13c62084", kernel)
        self.assertNotIn("0x13c62088", kernel)
        self.assertIn("GIC_SPI 273 IRQ_TYPE_LEVEL_HIGH", node)

    def test_gpufreq_window_from_cumulative_vendor_slots(self):
        _, (send, recv) = vendor_tables()
        header = (SCOPE / "mt6878-gpueb-io-core.h").read_text()
        tx = send[0][2] * 4
        rx = sum(row[2] * 4 for row in send) + recv[0][2] * 4
        self.assertEqual((tx, rx, send[1][2], recv[1][2]), (0x10, 0xe8, 8, 8))
        self.assertIn("#define GPUEB_IO_TX 0x10U", header)
        self.assertIn("#define GPUEB_IO_RX 0xe8U", header)
        self.assertIn("#define GPUEB_IO_CHANNEL (1U << 1)", header)

    def test_vendor_irq_source_not_boot_power_proof(self):
        code = vendor("drivers/soc/mediatek/mtk-mbox.c")
        trigger = definition(code, "int mtk_mbox_trigger_irq(")
        self.assertIn("writel(irq, minfo->set_irq_reg)", trigger)
        isr = definition(code, "static irqreturn_t mtk_mbox_isr(")
        self.assertLess(isr.index("mtk_mbox_read(mbdev"), isr.index("/*clear irq status*/"))
        init = vendor("drivers/gpu/mediatek/gpueb/gpueb_init.c")
        probe = definition(init, "static int __mt_gpueb_pdrv_probe(struct platform_device *pdev)\n{")
        self.assertIn("gpueb_ipi_init(pdev)", probe)
        self.assertNotIn("rproc_boot(", probe)

    def test_spin_scope_and_no_activation_or_irq_claim(self):
        code = (SCOPE / "mt6878-gpueb-io.c").read_text()
        self.assertIn("spin_lock_irqsave(&scope->lock, flags)", code)
        self.assertNotIn("phase = GPUEB_IO_TRANSACTION", code)
        for forbidden in ("request_threaded_irq", "request_irq", "enable_irq",
                          "disable_irq", "rproc_boot", "memcpy_toio", "memset_io"):
            self.assertNotRegex(code, r"\b" + forbidden + r"\s*\(")
        for forbidden in ("regulator_", "clk_", "devm_"):
            self.assertNotIn(forbidden, code)
        irq = definition(code, "int mt6878_gpueb_io_request_irq(")
        self.assertIn("-EHOSTDOWN", irq)
        self.assertIn("-EOPNOTSUPP", irq)
        fault = definition(code, "int mt6878_gpueb_io_unknown_start(")
        self.assertLess(fault.index("spin_unlock_irqrestore"),
                        fault.index("mt6878_gpueb_adoption_unknown_start("))

    def test_quiescence_never_unlocks_uncertain_removal(self):
        core = (SCOPE / "mt6878-gpueb-io-core.c").read_text()
        close = definition(core, "int gpueb_io_can_destroy(")
        self.assertIn("core->physical_uncertain", close)
        self.assertIn("GPUEB_IO_QUARANTINED", close)
        quiesce = definition(core, "int gpueb_io_quiesce(")
        self.assertIn("core->physical_uncertain = 1", quiesce)
        kernel = (SCOPE / "mt6878-gpueb-io.c").read_text()
        destroy = definition(kernel, "int mt6878_gpueb_io_destroy(")
        self.assertLess(destroy.index("return ret"), destroy.index("release_prepared(scope)"))
        self.assertIn("default n", (SCOPE / "Kconfig").read_text())

    def test_native_fixture_and_ci_only_guards(self):
        fixture = (SCOPE / "test-io-core.c").read_text()
        self.assertIn('#include "mt6878-gpueb-io-core.c"', fixture)
        self.assertIn("failure <= 10", fixture)
        env = dict(os.environ, CI="false", CC="/nonexistent/compiler")
        for script in (HERE / "run_gpueb_mmio_scope_ci.sh", SCOPE / "smoke-kernel-ci.sh"):
            result = subprocess.run(["sh", str(script)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("CI-only", result.stderr)
            self.assertEqual(subprocess.run(["sh", "-n", str(script)]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
