#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("factory_gpueb", HERE / "extract_factory_gpueb.py")
factory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory)


class HookAssets(unittest.TestCase):
    def test_listing_exact_member_and_unsafe_faults(self):
        listing = "Path = firmware/gpueb.img\nSize = 532480\nFolder = -\n\n"
        self.assertEqual(factory.member(listing), "firmware/gpueb.img")
        for mutated in (listing + listing, listing.replace("532480", "2097152"),
                        listing.replace("firmware/", "../"),
                        listing.replace("Folder = -", "Folder = -\nSymbolic Link = foo")):
            with self.assertRaises(ValueError):
                factory.member(mutated)

    def test_factory_archive_matches_shared_modem_provenance(self):
        shared = HERE.parents[2] / "ci/extract-stock-modem.py"
        module_spec = importlib.util.spec_from_file_location("shared_modem_archive", shared)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        self.assertEqual(factory.ARCHIVE_SIZE, module.ARCHIVE_SIZE)
        self.assertEqual(factory.ARCHIVE_SHA, module.ARCHIVE_SHA256)
        self.assertEqual(factory.URL, module.BASE + "/" + module.ARCHIVE)

    def test_capture_storage_bounds_and_no_start(self):
        code = (HERE / "tetris_gpueb_flat_hook.c").read_text()
        for term in ('"gpueb_a"', "part.size > dev->lba - part.start", "blk_dread",
                     "tetris_gpueb_flat_retain", "tetris_gpueb_flat_publish",
                     "fdt_add_mem_rsv(final, address, capacity)", "images->ft_addr = final"):
            self.assertIn(term, code)
        self.assertIn("#include <cpu_func.h>", code)
        self.assertIn("old = images->ft_addr;", code)
        self.assertNotIn("map_sysmem(images->ft_addr", code)
        self.assertNotIn("unmap_sysmem(old)", code)
        self.assertIn("flush_dcache_range((unsigned long)final, (unsigned long)final + capacity)", code)
        success = code.split("images->ft_addr = final;", 1)[1].split("release:", 1)[0]
        self.assertNotIn("unmap_sysmem(final)", success)
        self.assertIn("unmap_sysmem(final)", code.split("release:", 1)[1])
        self.assertNotIn("writel(", code)
        self.assertNotIn("arm_smccc_smc(", code)
        self.assertIn("default n", (HERE / "Kconfig.flat-retention").read_text())

    def test_our_compile_warnings_are_strict(self):
        code = (HERE / "run-native-ci.sh").read_text()
        flags = code.split("set --", 1)[1].split("# Warning exceptions", 1)[0]
        self.assertIn("-Wall -Wextra -Werror", flags)
        self.assertNotIn("-Wno-", flags)
        owned = code.split('for source in "$board/tetris_scp_security.c"', 1)[1].split("done", 1)[0]
        self.assertNotIn("-Wno-", owned)


if __name__ == "__main__":
    unittest.main()
