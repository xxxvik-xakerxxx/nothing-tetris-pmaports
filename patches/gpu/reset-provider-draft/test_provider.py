#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned-source/static gates; these do not execute C or establish hardware OFF."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prepare_native import definition
from test_gpueb_power import vendor, ROOT


class Provider(unittest.TestCase):
    def setUp(self):
        self.code = (HERE / "mt6878-gpueb-reset-provider.c").read_text()

    def test_real_provider_and_no_successful_disabled_stub(self):
        body = definition(self.code, "struct mt6878_gpueb_reset_provider *mt6878_gpueb_reset_provider_register(")
        self.assertLess(body.index("!IS_ENABLED(CONFIG_RESET_CONTROLLER)"), body.index("kzalloc("))
        for token in ("reset_controller_register(&provider->controller)",
                      "provider->controller.nr_resets = 1;", "cells != 1",
                      "parent->dev.driver->suppress_bind_attrs", "try_module_get(parent_module)"):
            self.assertIn(token, body)
        ops = self.code.split("static const struct reset_control_ops provider_ops = {", 1)[1].split("};", 1)[0]
        self.assertIn(".assert = provider_assert", ops)
        for operation in (".deassert", ".reset", ".status"):
            self.assertNotIn(operation, ops)

    def test_single_resource_owner_no_independent_claim(self):
        self.assertIn("mt6878_gpueb_reset_prepare(parent, sram)", self.code)
        for token in ("request_mem_region(", "request_irq(", "ioremap(", "readl(",
                      "writel(", "pm_runtime_resume", "pm_runtime_set_active", "IRQF_SHARED",
                      "arm_smccc", "regulator_enable", "clk_prepare_enable", "devm_"):
            self.assertNotIn(token, self.code)

    def test_quarantine_precedes_exact_helper_assertion(self):
        body = definition(self.code, "static int assert_owned(")
        self.assertLess(body.index("provider->first_error"), body.index("mt6878_gpueb_reset_hold("))
        self.assertLess(body.index("provider->asserted"), body.index("mt6878_gpueb_reset_hold("))
        self.assertLess(body.index("mt6878_gpueb_sram_unknown_start("), body.index("mt6878_gpueb_reset_hold("))
        self.assertEqual(body.count("mt6878_gpueb_reset_hold("), 1)
        helper = (HERE.parent / "reset-owner-draft/mt6878-gpueb-reset.c").read_text()
        self.assertIn("writel(0, scope->registers + 0x600)", helper)
        self.assertIn("request_irq(irq, unexpected_irq, IRQF_NO_AUTOEN", helper)

    def test_stop_never_reports_off_or_frees(self):
        body = definition(self.code, "int mt6878_gpueb_reset_provider_stop(")
        self.assertIn("if (!provider->asserted)", body)
        self.assertIn("mt6878_gpueb_reset_drain_irq(provider->scope)", body)
        self.assertIn("first_failure(provider, -EBUSY)", body)
        self.assertNotIn("return 0;", body)
        for token in ("reset_destroy", "sram_destroy", "module_put", "kfree", "pm_runtime_put"):
            self.assertNotIn(token, body)
        self.assertNotIn("reset_controller_unregister", self.code)

    def test_failed_registration_preserves_first_error_and_quarantine(self):
        body = definition(self.code, "struct mt6878_gpueb_reset_provider *mt6878_gpueb_reset_provider_register(")
        branch = body.split("if (cleanup) {", 1)[1].split("goto put_parent;", 1)[0]
        self.assertIn("mt6878_gpueb_sram_unknown_start(sram)", branch)
        self.assertIn("return ERR_PTR(ret)", branch)
        self.assertNotIn("kfree(", branch)
        self.assertNotIn("module_put(", branch)

    def test_vendor_inherits_lk_not_a_remoteproc_stop(self):
        init = vendor("drivers/gpu/mediatek/gpueb/gpueb_init.c")
        self.assertIn(".remove = NULL", init)
        self.assertIn("gpueb_ipi_init(pdev)", init)
        self.assertNotIn("rproc_alloc(", init)
        self.assertNotIn("request_firmware(", init)
        debug = vendor("drivers/gpu/mediatek/gpueb/gpueb_debug.c")
        self.assertIn("GPUEB_SMC_OP_TRIGGER_WDT            = 0", debug)
        self.assertIn("GPUACP_SMC_OP_CPUPM_PWR             = 1", debug)
        dt = vendor("arch/arm64/boot/dts/mediatek/mt6878.dts")
        gpueb = dt.split("gpueb: gpueb@13c00000", 1)[1].split("gpueb-diagnosis-mode", 1)[0]
        self.assertIn("0x13c60000 0 0x2000", gpueb)
        self.assertIn("GIC_SPI 273 IRQ_TYPE_LEVEL_HIGH", gpueb)
        self.assertIn('"PWR"', dt)

    def test_remoteproc_stop_error_prevents_resource_cleanup(self):
        tree = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        core = (tree / "drivers/remoteproc/remoteproc_core.c").read_text()
        shutdown = definition(core, "int rproc_shutdown(")
        stop = definition(core, "static int rproc_stop(")
        self.assertLess(shutdown.index("atomic_inc(&rproc->power)"), shutdown.index("rproc_resource_cleanup("))
        self.assertIn("goto out;", shutdown.split("atomic_inc(&rproc->power)", 1)[1].split("rproc_resource_cleanup", 1)[0])
        self.assertLess(stop.index("rproc_stop_subdevices("), stop.index("rproc->ops->stop("))
        self.assertLess(stop.index("if (ret)", stop.index("rproc->ops->stop(")), stop.index("rproc->state = RPROC_OFFLINE"))

    def test_ci_only_object_runner_and_default_off(self):
        self.assertIn("default n", (HERE / "Kconfig").read_text())
        runner = HERE / "smoke-kernel-ci.sh"
        self.assertEqual(subprocess.run(["sh", "-n", str(runner)], capture_output=True).returncode, 0)
        env = dict(os.environ, CI="false")
        self.assertEqual(subprocess.run(["sh", str(runner)], env=env, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
