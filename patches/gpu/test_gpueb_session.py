#!/usr/bin/env python3
"""Pinned source/layout and session ownership checks; no hardware or compilation."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_supply_inventory import PATCHES, ROOT, new_file, validate_hunk_counts
from test_gpueb_power import vendor, require_exact_application, NAME as POWER_PATCH
from prepare_native import definition

NAME = "0120-mailbox-mediatek-mt6878-gpueb-session.patch"
DRIVER = "drivers/pmdomain/mediatek/mt6878-gpueb-session.c"
MAILBOX = "drivers/mailbox/mtk-gpueb-mailbox.c"


def source():
    return new_file((PATCHES / NAME).read_text(), DRIVER)


def vendor_tables():
    dts = vendor("arch/arm64/boot/dts/mediatek/mt6878.dts")
    node = definition(dts, "gpueb: gpueb@13c00000 {")
    tables = []
    for prop, width in (("send-table", 3), ("recv-table", 5)):
        text = node.split(prop + " =", 1)[1].split(";", 1)[0]
        rows = [tuple(int(n, 0) for n in row.split())
                for row in re.findall(r"<([^>]+)>", text)]
        assert all(len(row) == width and row[1] == 0 for row in rows)
        tables.append(rows)
    return node, tables


class Session(unittest.TestCase):
    def test_hunk_counts(self):
        validate_hunk_counts((PATCHES / NAME).read_text(), NAME)

    def test_exact_application_after_frozen_power_patch(self):
        kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            for relative in (MAILBOX,
                             "Documentation/devicetree/bindings/mailbox/mediatek,mt8196-gpueb-mbox.yaml",
                             "drivers/pmdomain/mediatek/Makefile",
                             "drivers/pmdomain/mediatek/Kconfig"):
                target = tree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((kernel / relative).read_text())
            for name in (POWER_PATCH, NAME):
                result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                        cwd=tree, input=(PATCHES / name).read_text(),
                                        capture_output=True, text=True)
                require_exact_application(result)
            self.assertEqual((tree / DRIVER).read_text(), source())

    def test_mailbox_variant_matches_vendor_cumulative_slots(self):
        node, (send, recv) = vendor_tables()
        self.assertIn("mbox-size = <160>", node)
        self.assertIn("slot-size = <4>", node)
        self.assertIn("GIC_SPI 273 IRQ_TYPE_LEVEL_HIGH", node)
        text = (PATCHES / NAME).read_text()
        variant = text.split("+static const struct mtk_gpueb_mbox_variant mtk_gpueb_mbox_mt6878", 1)[1]
        rows = re.findall(r'\{ "[^"\n]+",\s*(\d+),\s*(0x[\da-f]+),\s*(\d+),\s*(0x[\da-f]+),\s*(\d+) \}', variant)
        self.assertEqual(len(rows), 11)
        tx, rx = 0, sum(row[2] * 4 for row in send)
        for index, row in enumerate(rows):
            actual = tuple(int(value, 0) for value in row)
            self.assertEqual(actual, (index, tx, send[index][2] * 4, rx, recv[index][2] * 4))
            tx += send[index][2] * 4
            rx += recv[index][2] * 4
        self.assertLessEqual(rx, 160 * 4)
        for address in ("0x13c3fd80", "0x13c62004", "0x13c62074", "0x13c62000", "0x13c62078"):
            self.assertIn(address, node)

    def test_shared_status_offsets_from_exact_source(self):
        text = vendor("drivers/gpu/mediatek/gpufreq/v2/include/gpufreq_v2.h")
        prefix = text.split("struct gpufreq_shared_status {", 1)[1].split("unsigned int active_sleep_control;", 1)[0]
        fields = re.findall(r"(?:unsigned int|int) (\w+);", prefix)
        self.assertEqual(fields.index("power_count") * 4, 0x1c)
        self.assertEqual(fields.index("power_control") * 4, 0xc4)
        code = source()
        self.assertIn("#define GPUEB_STATUS_POWER_COUNT 0x1c", code)
        self.assertIn("#define GPUEB_STATUS_POWER_CONTROL 0xc4", code)
        node, _ = vendor_tables()
        self.assertIn("<0 0x4000>", node)
        common = vendor("drivers/gpu/mediatek/gpueb/include/gpueb_common.h")
        self.assertIn("GPUEB_SRAM_GPR13 = 13", common)
        self.assertIn("SRAM_GPR_SIZE_4B                    (0x4)", common)

    def test_real_transport_lifecycle_no_forged_readiness(self):
        code = source()
        for required in ("rproc_get_by_phandle", "rproc_boot", "rproc_shutdown",
                         "of_reserved_mem_lookup", "request_mem_region", "ioremap_wc",
                         "mbox_request_channel_byname", "mbox_send_message",
                         "wait_for_completion_timeout", "mutex_lock(&s->request_lock)"):
            self.assertIn(required, code)
        for forbidden in ("proven =", "MT6878_GPUEB_REQUIRED", "regulator_enable(",
                          "clk_prepare_enable(", "of_genpd_add_provider", "request_firmware("):
            self.assertNotIn(forbidden, code)
        self.assertNotIn("arch/arm64/boot/dts", (PATCHES / NAME).read_text())
        probe = definition(code, "static int gpueb_probe(")
        self.assertLess(probe.index("rproc_boot("), probe.index("mbox_request_channel_byname("))
        self.assertLess(probe.index("gpueb_init_message("), probe.index("memset_io("))
        self.assertLess(probe.index("gpueb_exchange("), probe.index("s->initialized = true"))
        release = definition(code, "static bool gpueb_release(")
        self.assertLess(release.index("return false;"), release.index("mbox_free_channel("))
        self.assertIn("RPROC_OFFLINE", release)

    def test_rx_fault_checked_atomically_before_request_arm(self):
        exchange = definition(source(), "static int gpueb_exchange(")
        locked = exchange.split("spin_lock_irqsave(&s->rx_lock, flags);", 1)[1]
        self.assertLess(locked.index("if (s->error)"), locked.index("reinit_completion("))
        self.assertLess(locked.index("return ret;"), locked.index("s->waiting = true"))
        self.assertLess(exchange.index("s->waiting = true"), exchange.index("mbox_send_message("))
        rx = definition(source(), "static void gpueb_rx(")
        self.assertLess(rx.index("if (!message)"), rx.index("memcpy(s->reply"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    if args.extract:
        code = source()
        defines = "\n".join(line for line in code.splitlines() if line.startswith("#define GPUEB_"))
        args.extract.write_text(defines + "\n" +
                                definition(code, "struct mt6878_gpueb_session {") +
                                definition(code, "static int gpueb_fail(") +
                                definition(code, "static void gpueb_rx(") +
                                definition(code, "static int gpueb_exchange(") +
                                definition(code, "static bool gpueb_shared_range_valid(") +
                                definition(code, "static int gpueb_init_message("))
    else:
        unittest.main(argv=[__file__])
