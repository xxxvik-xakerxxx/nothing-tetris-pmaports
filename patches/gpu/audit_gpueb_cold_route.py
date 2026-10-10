#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline cold-start feasibility audit; never emits executable MMIO commands."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_gpueb_allocation import trace as allocation_trace
from audit_gpueb_b41 import signed_lk, MAX_LK, read_bounded
from audit_gpueb_lk import expect
from gpueb_firmware import require
from prepare_native import definition
from test_gpueb_power import vendor, PIN


def lifecycle(init, platform, wrapper, mailbox, genpd):
    probe = definition(init, "static int __mt_gpueb_pdrv_probe(struct platform_device *pdev)\n{")
    table = definition(platform, "static struct gpufreq_platform_fp platform_eb_fp = {")
    power = definition(wrapper, "int gpufreq_power_control(")
    irq = definition(mailbox, "static irqreturn_t mtk_mbox_isr(")
    attach = definition(genpd, "struct device *genpd_dev_pm_attach_by_id(")
    require("gpueb_ipi_init(pdev)" in probe and ".remove = NULL" in init,
            "vendor inherited-boot lifecycle changed")
    require(not any(api in probe for api in ("pm_runtime_", "clk_prepare_enable(",
            "regulator_enable(", "reset_control_")), "vendor bootstrap needs re-audit")
    require(".power_control" not in table and "CMD_POWER_CONTROL" in power and
            "gpufreq_ipi_to_gpueb(send_msg)" in power,
            "command 6 bootstrap assumption changed")
    require("mtk_mbox_clr_irq(mbdev, mbox, irq_temp)" in irq and
            "irq_temp = irq_temp | (0x1 << pin_recv->pin_index)" in irq and
            "for (i = 0; i < mbdev->recv_count; i++)" in irq,
            "whole-bank IRQ policy changed")
    require("IRQF_NO_SUSPEND | IRQF_TRIGGER_NONE" in mailbox and
            "IRQF_SHARED" not in mailbox, "vendor exclusive IRQ policy changed")
    require("num_domains, false)" in attach and
            "genpd_queue_power_off_work(dev_to_genpd(virt_dev))" in attach,
            "upstream attach side effects changed")
    return {"vendor_commit": PIN, "kernel_genpd_source_sha256":
            hashlib.sha256(genpd.encode()).hexdigest(),
            "command6_requires_running_gpueb": True,
            "vendor_probe_is_cold_boot_owner": False,
            "genpd_attach_is_passive": False,
            "irq_policy": "exclusive whole-bank; acknowledge decoded pin mask only"}


def cold_route(code):
    allocation = allocation_trace(code)
    # Verify register address construction, ordering and the actual READY poll.
    # These are audited stock instructions, NOT a proposed Linux write recipe.
    for check in (
        (0x1ed98, "tbnz", "w0, #0x1f, #0x1ee84"),
        (0x1edbc, "bl", "#0x5e74"),
        (0x5e74, "add", "x2, x0, x1"),
        (0x5e78, "and", "x3, x0, #0xffffffffffffffc0"),
        (0x5e7c, "dc", "civac, x3"),
        (0x5e80, "add", "x3, x3, #0x40"),
        (0x5e84, "cmp", "x3, x2"),
        (0x5e88, "b.lo", "#0x5e7c"),
        (0x5e8c, "dsb", "sy"),
        (0x5e90, "ret", ""),
        (0x1eda4, "mov", "x25, #0x1030"),
        (0x1edac, "movk", "x25, #0x13f9, lsl #16"),
        (0x1eda8, "mov", "x22, #0x600"),
        (0x1edb0, "movk", "x22, #0x13c6, lsl #16"),
        (0x1edd4, "mov", "w8, #0xf00"),
        (0x1eddc, "movk", "w8, #1, lsl #16"),
        (0x1edf0, "str", "w8, [x25]"),
        (0x1edf8, "str", "wzr, [x22]"),
        (0x1edfc, "bl", "#0x6a98c"),
        (0x1ee00, "mov", "w8, #0xf2bc"),
        (0x1ee04, "movk", "w8, #3, lsl #16"),
        (0x1ee08, "ldr", "w9, [x23], #4"),
        (0x1ee0c, "sub", "w8, w8, #4"),
        (0x1ee10, "cmp", "w8, #4"),
        (0x1ee14, "str", "w9, [x26], #4"),
        (0x1ee18, "b.hi", "#0x1ee08"),
        (0x1ee38, "str", "w19, [x23]"),
        (0x1ee3c, "str", "wzr, [x23, #4]"),
        (0x1ee40, "str", "wzr, [x23, #0x5c]"),
        (0x1ee44, "str", "w8, [x23, #0x18]"),
        (0x1eed4, "str", "w8, [x23, #0x48]"),
        (0x1eed8, "mov", "w8, #0xb"),
        (0x1eee0, "movk", "w8, #0x3f00, lsl #16"),
        (0x1eee8, "str", "w8, [x22]"),
        (0x1eedc, "mov", "w20, #0x7788"),
        (0x1eee4, "movk", "w20, #0x5566, lsl #16"),
        (0x1eeec, "ldr", "w8, [x23, #8]"),
        (0x1eef4, "b.ne", "#0x1ef18"),
    ):
        expect(code, *check)
    return {"stock_order": ["authenticated reader success",
            "clean+invalidate mapped 1 MiB: dc civac/64-byte lines; dsb sy",
            "MFG write 0x13f91030 = 0x10f00", "reset 0x13c60600 = 0",
            "clear SRAM 0x40000 bytes", "copy 258744 bytes",
            "initialize GPR0/1/23/6/18", "reset release = 0x3f00000b",
            "poll GPR2 = 0x55667788"],
            "authenticated_bytes": allocation["authenticated_primary_bytes"],
            "uncovered_copy_bytes": allocation["unauthenticated_copy_excess_bytes"],
            "launch_available": False,
            "first_blocker": "authenticated executable span/layout: 156064 != 258744",
            "remaining_prerequisites": [
                "persistent authenticated bytes: verified-erased supplies none",
                "EMI table construction/protection result and lifetime ownership before boot",
                "physical power/reset/clock supplier and OFF-on-failure proof",
                "whole-bank IRQ channel consumers before interrupt enable"],
            "next_safe_gate": "inspect authenticated plaintext format/segment metadata in transform window; erase afterwards; no SRAM/reset writes"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lk", required=True, type=Path)
    parser.add_argument("--kernel-tree", required=True, type=Path)
    args = parser.parse_args()
    prefix = "drivers/gpu/mediatek/"
    report = cold_route(signed_lk(read_bounded(args.lk, MAX_LK)))
    report["lifecycle"] = lifecycle(
        vendor(prefix + "gpueb/gpueb_init.c"),
        vendor(prefix + "gpufreq/v2/gpufreq_mt6878.c"),
        vendor(prefix + "gpufreq/v2/gpufreq_v2.c"),
        vendor("drivers/soc/mediatek/mtk-mbox.c"),
        (args.kernel_tree / "drivers/pmdomain/core.c").read_text())
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
