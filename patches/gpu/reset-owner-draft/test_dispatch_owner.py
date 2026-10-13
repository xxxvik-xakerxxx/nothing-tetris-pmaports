#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exact-source lifetime and ordering checks; no native code execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prepare_native import definition
from test_gpueb_power import vendor, ROOT


class DispatchOwner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = (HERE / "mt6878-gpueb-reset.c").read_text()

    def test_exact_vendor_consumer_boundary(self):
        evidence = json.loads((HERE / "RESOURCE-CONTRACT.json").read_text())
        path = "drivers/gpu/mediatek/gpueb/gpueb_init.c"
        init = vendor(path)
        self.assertEqual(hashlib.sha256(init.encode()).hexdigest(),
                         evidence["source"]["files_sha256"][path])
        probe = definition(init, "static int __mt_gpueb_pdrv_probe(struct platform_device *pdev)\n{")
        self.assertLess(probe.index("gpueb_ipi_init(pdev)"),
                        probe.index("gpueb_reserved_mem_init(pdev)"))
        self.assertIn(".remove = NULL", init)
        pins = evidence["dispatch_vendor_consumers"]
        self.assertEqual(pins["commit"], "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835")
        tree = Path(os.environ.get("TETRIS_VENDOR_MODULES_TREE", str(
            ROOT.parent / "android_kernel_modules_nothing_mt6878")))
        path = "met_drv_v3/common/tinysys/v1/gpueb/gpueb_met_ipi_handle.c"
        code = subprocess.check_output(["git", "show", pins["commit"] + ":" + path],
                                       cwd=tree, text=True)
        self.assertEqual(hashlib.sha256(code.encode()).hexdigest(), pins["files_sha256"][path])
        receive = definition(code, "void start_gpueb_ipi_recv_thread(")
        self.assertIn("!gpueb_ipidev_symbol->ipi_inited", receive)
        self.assertIn('"CH_IPIR_C_MET"', receive)
        self.assertIn('"CH_IPIS_C_MET"', receive)
        self.assertIn("mtk_ipi_register_symbol", receive)
        start = definition(code, "void gpueb_start(")
        self.assertIn("MET_OP_START", start)
        self.assertIn("met_ipi_to_gpueb_command(", start)
        self.assertNotIn("0x3f00000b", start)

    def test_acquire_seals_all_consumers_and_real_lifetime(self):
        acquire = definition(self.code, "struct mt6878_gpueb_dispatch *mt6878_gpueb_reset_dispatch_acquire(")
        publish = acquire.index("scope->dispatch_owner = dispatch")
        for token in ("scope->first_error", "scope->dispatch_quiesced || scope->reset_written",
                      "scope->dispatch_owner || scope->dispatch_active", "parent != scope->parent",
                      "scope->registered != BIT(GPUEB_MBOX_CHANNELS) - 1", "dispatch_identity(scope)",
                      "mt6878_gpueb_sram_check_parent(scope->sram, parent)",
                      "!irqd_irq_disabled(irq_data)", "scope->irq_contained",
                      "try_module_get(module)", "pm_runtime_get_if_in_use(parent)",
                      "get_device(parent)"):
            self.assertIn(token, acquire)
            self.assertLess(acquire.index(token), publish)
        self.assertLess(acquire.index("mutex_lock("), acquire.index("scope->registered !="))
        self.assertLess(acquire.index("try_module_get("), acquire.index("pm_runtime_get_if_in_use("))
        self.assertIn("ret = ret ?: -EAGAIN", acquire)
        self.assertIn("module_put(module)", acquire)
        self.assertLess(acquire.index("module_put(module)"), publish)
        self.assertIn("kfree(dispatch)", acquire)
        for token in ("readl(", "writel(", "enable_irq(", "pm_runtime_resume", "arm_smccc"):
            self.assertNotIn(token, acquire)
        bind = definition(self.code, "int mt6878_gpueb_reset_bind_channel(")
        self.assertLess(bind.index("if (scope->dispatch_owner)"), bind.index("try_module_get("))

    def test_dispatch_checks_all_driver_identities_before_mmio(self):
        identity = definition(self.code, "static int dispatch_identity(")
        self.assertIn("scope->parent->driver != scope->parent_driver", identity)
        self.assertIn("scope->channels[i].device->driver != scope->channels[i].driver", identity)
        self.assertEqual(identity.count("suppress_bind_attrs"), 2)
        for signature, transaction in (
                ("static irqreturn_t mailbox_irq_thread(", "mt6878_gpueb_sram_read_transaction("),
                ("int mt6878_gpueb_reset_trysend(", "mt6878_gpueb_sram_send_transaction(")):
            body = definition(self.code, signature)
            self.assertIn("!scope->dispatch_owner", body)
            self.assertLess(body.index("dispatch_identity(scope)"), body.index(transaction))
        before = definition(self.code, "static int tx_before(")
        self.assertLess(before.index("readl(scope->mbox_maps[GPUEB_MBOX_RECV])"),
                        before.index("scope->dispatch_used = true"))
        thread = definition(self.code, "static irqreturn_t mailbox_irq_thread(")
        self.assertLess(thread.index("scope->dispatch_used = true"),
                        thread.index("mt6878_gpueb_sram_read_transaction("))

    def test_release_keeps_owner_published_through_drain_and_uncertainty(self):
        release = definition(self.code, "int mt6878_gpueb_reset_dispatch_release(")
        self.assertLess(release.index("mt6878_gpueb_reset_drain_irq(scope)"),
                        release.index("mutex_lock("))
        self.assertLess(release.index("scope->dispatch_used || scope->reset_written"),
                        release.index("scope->dispatch_owner = NULL"))
        self.assertLess(release.index("return ret ?: -EBUSY"),
                        release.index("pm_runtime_put_noidle("))
        self.assertLess(release.index("mt6878_gpueb_sram_unknown_start("),
                        release.index("return ret ?: -EBUSY"))
        self.assertLess(release.rindex("mutex_unlock("), release.index("module_put("))
        self.assertLess(release.index("put_device("), release.index("kfree(dispatch)"))
        destroy = definition(self.code, "int mt6878_gpueb_reset_destroy(")
        self.assertLess(destroy.index("if (scope->dispatch_owner)"),
                        destroy.index("mt6878_gpueb_reset_drain_irq(scope)"))
        drain = definition(self.code, "int mt6878_gpueb_reset_drain_irq(")
        self.assertLess(drain.index("scope->dispatch_used = true"),
                        drain.index("scope->dispatch_active = false"))

    def test_no_permission_producer_or_new_native_runner(self):
        self.assertNotRegex(self.code, r"dispatch_active\s*=\s*(?:true|1)")
        self.assertNotIn("enable_irq(", self.code)
        header = (HERE / "mt6878-gpueb-reset.h").read_text()
        self.assertNotRegex(header, r"bool\s+(?:ready|active|enabled|authenticated)")
        fixture = (HERE / "test-mailbox.c").read_text()
        for token in ("test_dispatch_lifetime", "test_dispatch_callback_drain",
                      "test_concurrent_acquire", "fixture_pm_get_result = -EIO",
                      "fixture_module_fail = &client_module", "fail_alloc = 1",
                      "mt6878_gpueb_reset_dispatch_acquire", "pthread_cond_wait"):
            self.assertIn(token, fixture)
        release = definition(fixture, "static void *concurrent_release(")
        self.assertIn("mt6878_gpueb_reset_dispatch_release(scope.dispatch_owner)", release)
        callback = definition(fixture, "static void test_dispatch_callback_drain(")
        self.assertIn("mt6878_gpueb_reset_destroy(&scope) == -EBUSY", callback)
        self.assertIn("result == -EBUSY && scope.dispatch_owner", callback)


if __name__ == "__main__":
    unittest.main()
