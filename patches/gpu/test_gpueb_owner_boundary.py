#!/usr/bin/env python3
"""Extract actual patched release code; verify pinned SRAM ownership boundaries."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_supply_inventory import PATCHES, ROOT, validate_hunk_counts
from test_gpueb_session import source, DRIVER, vendor_tables
from test_gpueb_power import require_exact_application
from prepare_native import definition

NAME = "0122-mailbox-mediatek-gpueb-quarantine-failed-boot.patch"


def patched_source():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / DRIVER
        target.parent.mkdir(parents=True)
        target.write_text(source())
        result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                cwd=tmp, input=(PATCHES / NAME).read_text(),
                                capture_output=True, text=True)
        require_exact_application(result)
        return target.read_text()


class OwnerBoundary(unittest.TestCase):
    def test_core_start_error_is_not_physical_off_proof(self):
        kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        core = (kernel / "drivers/remoteproc/remoteproc_core.c").read_text()
        start = definition(core, "static int rproc_start(")
        failure = start.split("ret = rproc->ops->start(rproc);", 1)[1].split(
            "/* Start any subdevices", 1)[0]
        self.assertIn("goto unprepare_subdevices", failure)
        self.assertNotIn("ops->stop", failure)
        self.assertLess(start.index("stop_rproc:"), start.index("unprepare_subdevices:"))

    def test_exact_patch_application(self):
        validate_hunk_counts((PATCHES / NAME).read_text(), NAME)
        code = patched_source()
        probe = definition(code, "static int gpueb_probe(")
        self.assertLess(probe.index("s->boot_attempted = true"), probe.index("rproc_boot("))
        release = definition(code, "static bool gpueb_release(")
        self.assertLess(release.index("s->boot_attempted && !s->boot_ref"),
                        release.index("rproc_shutdown("))
        self.assertLess(release.index("return false;"), release.index("iounmap("))

    def test_source_proven_sram_three_nonoverlapping_slices(self):
        node, _ = vendor_tables()
        # These are validation constants from the pinned DT, never live addresses.
        resources = re.findall(r"<0 (0x[0-9a-fA-F]+) 0 (0x[0-9a-fA-F]+)>",
                               node.split("reg =", 1)[1].split(";", 1)[0])
        names = re.findall(r'"([^"\n]+)"', node.split("reg-names =", 1)[1].split(";", 1)[0])
        regs = {name: (int(base, 16), int(size, 16))
                for name, (base, size) in zip(names, resources)}
        self.assertEqual(len(regs), len(names))
        base, size = regs["gpueb_base"]
        gpr, gpr_size = regs["gpueb_gpr_base"]
        mailbox, mailbox_size = regs["mbox0_base"]
        self.assertEqual(gpr - base, 0x3fd1c)
        self.assertEqual(gpr_size, 0x64)
        self.assertEqual(gpr + gpr_size, mailbox)
        self.assertEqual(mailbox + mailbox_size, base + size)
        self.assertEqual(mailbox_size, 0x280)
        # A whole-SRAM owner claim necessarily overlaps both existing consumers.
        for start, length in ((gpr, gpr_size), (mailbox, mailbox_size)):
            self.assertTrue(base < start + length and start < base + size)
        code = patched_source()
        self.assertIn("request_mem_region(res->start, resource_size(res)", code)
        self.assertNotIn("devm_ioremap(", code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    if args.extract:
        code = patched_source()
        args.extract.write_text(definition(code, "struct mt6878_gpueb_session {") +
                               definition(code, "static bool gpueb_release("))
    else:
        unittest.main(argv=[__file__])
