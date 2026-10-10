#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Static contract gates only; execution/sanitizers require the CI runner."""
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
PUB = (HERE / "tetris_gpueb_flat_publish.c").read_text()
LINUX = (HERE / "gpueb-flat-analysis.c").read_text()


class Publication(unittest.TestCase):
    def test_only_copy_is_committed(self):
        self.assertEqual(PUB.count("memcpy(fdt, copy, capacity)"), 1)
        self.assertLess(PUB.index("ret = build(copy, &info)"), PUB.index("memcpy(fdt, copy, capacity)"))
        self.assertLess(PUB.index("memcpy(fdt, copy, capacity)"), PUB.index("*image = NULL"))
        self.assertNotRegex(PUB, r"fdt_setprop\w*\(fdt,.*chosen")
        self.assertIn("fdt_check_full", PUB)

    def test_abort_erases_and_keeps_failed_discard_owner(self):
        abort = PUB.split("\nabort:\n")[1]
        self.assertIn("released = tetris_gpueb_flat_discard(*image)", abort)
        self.assertIn("if (!released)\n\t\t*image = NULL", abort)
        self.assertIn("return ret;", abort)

    def test_reserved_memory_contract(self):
        for term in ("no-map", "memory-region", "nothing,authenticated-bytes",
                     "nothing,plaintext-sha256", "fdt_generate_phandle", "reservations("):
            self.assertIn(term, PUB)
        self.assertNotIn('"reusable"', PUB)
        self.assertIn("fdt_address_cells(fdt, parent) != 2", PUB)
        self.assertIn("fdt_num_mem_rsv", PUB)
        self.assertIn("fdt_get_mem_rsv", PUB)
        self.assertIn("gpueb-authenticated@%llx", PUB)

    def test_no_mmio_and_bounded_private_read(self):
        self.assertNotRegex(LINUX, r"\b(readl|writel|ioremap|rproc_boot)\s*\(")
        self.assertIn("IORESOURCE_SYSTEM_RAM", LINUX)
        self.assertIn("MEMREMAP_WB", LINUX)
        self.assertIn("size != 156064 || size > memory->size", LINUX)
        self.assertIn("CAP_SYS_RAWIO", LINUX)
        self.assertIn(".mode = 0600", LINUX)
        self.assertIn("analysis->snapshot, analysis->size", LINUX)

    def test_digest_before_publication_and_boot_lifetime(self):
        self.assertLess(LINUX.index("crypto_shash_digest("), LINUX.index("misc_register("))
        self.assertIn("suppress_bind_attrs = true", LINUX)
        self.assertIn("try_module_get(THIS_MODULE)", LINUX)
        self.assertIn("kvfree_sensitive(analysis->snapshot, size)", LINUX)

    def test_native_is_actual_sources_and_sanitized(self):
        runner = (HERE / "run-native-ci.sh").read_text()
        for term in ("fsanitize=address,undefined", "tetris_scp_security.c",
                     "tetris_scp_crypto.c", "tetris_gpueb_layout.c", "-lfdt"):
            self.assertIn(term, runner)
        self.assertIn('#include "tetris_gpueb_flat.c"', (HERE / "test-native.c").read_text())
        self.assertNotIn("TETRIS_GPUEB_PRIVATE_FACTORY_PLAIN", PUB)


if __name__ == "__main__":
    unittest.main()
