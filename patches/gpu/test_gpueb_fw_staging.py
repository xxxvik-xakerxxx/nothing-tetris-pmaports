#!/usr/bin/env python3
"""Exact patch and production-helper extraction for CI-only native staging tests."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_supply_inventory import PATCHES, ROOT, new_file, validate_hunk_counts
from test_gpueb_power import require_exact_application

NAME = "0123-remoteproc-mediatek-gpueb-firmware-staging.patch"
DRIVER = "drivers/remoteproc/mtk_gpueb_fw.c"
HEADER = "include/linux/soc/mediatek/mt6878-gpueb-firmware.h"


def source():
    return new_file((PATCHES / NAME).read_text(), DRIVER)


class Staging(unittest.TestCase):
    def test_exact_application(self):
        validate_hunk_counts((PATCHES / NAME).read_text(), NAME)
        kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            for relative in ("drivers/remoteproc/Kconfig", "drivers/remoteproc/Makefile"):
                target = tree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((kernel / relative).read_text())
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                    cwd=tree, input=(PATCHES / NAME).read_text(),
                                    capture_output=True, text=True)
            require_exact_application(result)
            self.assertEqual((tree / DRIVER).read_text(), source())

    def test_ingress_is_not_boot_authentication_or_dma(self):
        code = source()
        for required in ("request_firmware(&firmware, name, dev)",
                         "release_firmware(firmware)", "image->firmware = firmware",
                         "memset(sections, 0, sizeof(parsed))", "*out = NULL"):
            self.assertIn(required, code)
        for forbidden in ("rproc_boot(", "writel(", "ioremap", "dma_", "clk_",
                          "regulator_", "platform_driver", "arm_smccc", "ELF"):
            self.assertNotIn(forbidden, code)
        patch = (PATCHES / NAME).read_text()
        self.assertNotIn("arch/arm64/boot/dts", patch)
        self.assertIn("depends on FW_LOADER", patch)
        self.assertNotIn("default y", patch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    if args.extract:
        patch = (PATCHES / NAME).read_text()
        header = new_file(patch, HEADER)
        code = header + source()
        args.extract.write_text("\n".join(line for line in code.splitlines()
                                         if not line.startswith(("#include", "EXPORT_SYMBOL_GPL",
                                                                 "MODULE_DESCRIPTION", "MODULE_LICENSE"))) + "\n")
    else:
        unittest.main(argv=[__file__])
