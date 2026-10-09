#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned layout and production candidate static tests; never build locally."""
import os
from pathlib import Path
import re
import subprocess
import unittest

from prepare_native import definition
from test_gpueb_session import vendor_tables

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / "sram-owner"


class SramOwnerTests(unittest.TestCase):
    def test_pinned_vendor_resources_exact(self):
        node, _ = vendor_tables()  # git show ee2be53, injectable CI tree
        entries = re.findall(r"<0 (0x[\da-fA-F]+) 0 (0x[\da-fA-F]+)>",
                             node.split("reg =", 1)[1].split(";", 1)[0])
        names = re.findall(r'"([^"\n]+)"', node.split("reg-names =", 1)[1].split(";", 1)[0])
        self.assertEqual(len(names), len(entries))
        resources = {name: (int(base, 16), int(size, 16))
                     for name, (base, size) in zip(names, entries)}
        header = (CANDIDATE / "mt6878-gpueb-sram-core.h").read_text()
        constants = {name: int(value, 16) for name, value in
                     re.findall(r"#define (GPUEB_\w+) (0x[\da-fA-F]+)ULL", header)}
        base, size = resources["gpueb_base"]
        self.assertEqual((base, size), (constants["GPUEB_SRAM_BASE"], constants["GPUEB_SRAM_SIZE"]))
        for name, prefix in (("gpueb_gpr_base", "GPUEB_GPR"), ("mbox0_base", "GPUEB_MBOX")):
            address, length = resources[name]
            self.assertEqual(address - base, constants[prefix + "_OFFSET"])
            self.assertEqual(length, constants[prefix + "_SIZE"])
        self.assertEqual(constants["GPUEB_GPR_OFFSET"] + constants["GPUEB_GPR_SIZE"],
                         constants["GPUEB_MBOX_OFFSET"])
        self.assertEqual(constants["GPUEB_MBOX_OFFSET"] + constants["GPUEB_MBOX_SIZE"], size)

    def test_actual_resource_owner_no_activation(self):
        source = (CANDIDATE / "mt6878-gpueb-sram.c").read_text()
        self.assertEqual(source.count("request_mem_region("), 1)
        self.assertEqual(source.count("ioremap("), 1)
        for forbidden in ("devm_", "writel(", "readl(", "memset_io(", "memcpy_toio(",
                          "rproc_boot(", "platform_driver", "module_init", "regulator_", "clk_"):
            self.assertNotIn(forbidden, source)
        destroy = definition(source, "int mt6878_gpueb_sram_destroy(")
        self.assertLess(destroy.index("gpueb_sram_close("), destroy.index("iounmap("))
        self.assertLess(destroy.index("return ret;"), destroy.index("iounmap("))
        self.assertIn("default n", (CANDIDATE / "Kconfig").read_text())
        self.assertIn('\tbool "', (CANDIDATE / "Kconfig").read_text())

    def test_quarantine_has_no_software_off_escape(self):
        core = (CANDIDATE / "mt6878-gpueb-sram-core.c").read_text()
        close = definition(core, "int gpueb_sram_close(")
        self.assertIn("GPUEB_SRAM_QUARANTINED || core->clients", close)
        self.assertIn("return -EBUSY", close)
        header = (CANDIDATE / "mt6878-gpueb-sram.h").read_text()
        self.assertNotIn("void __iomem", header)
        self.assertNotIn("recover(", header)

    def test_native_fixture_uses_real_sources(self):
        fixture = (CANDIDATE / "test-sram-owner.c").read_text()
        for file in ("mt6878-gpueb-sram-core.c", "mt6878-gpueb-sram.c"):
            self.assertIn('#include "' + file + '"', fixture)
        self.assertIn("pthread_create", fixture)
        self.assertIn("releases == old_releases && unmaps == old_unmaps", fixture)

    def test_both_builders_reject_local_before_tools(self):
        env = dict(os.environ, CI="false", CC="/nonexistent/compiler")
        for script in (HERE / "run_gpueb_sram_owner_ci.sh", CANDIDATE / "smoke-kernel-ci.sh"):
            result = subprocess.run(["sh", str(script)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("CI-only", result.stderr)
            syntax = subprocess.run(["sh", "-n", str(script)], capture_output=True)
            self.assertEqual(syntax.returncode, 0)


if __name__ == "__main__":
    unittest.main()
