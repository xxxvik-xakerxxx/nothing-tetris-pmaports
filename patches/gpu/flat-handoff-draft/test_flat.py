#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Static draft gates. These do not replace CI compilation or native faults."""
import os
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from audit_gpueb_b41 import signed_lk
from audit_gpueb_cold_route import cold_route
from audit_gpueb_lk import ROOT_PIN
import gpueb_firmware as fw

C = (HERE / "tetris_gpueb_flat.c").read_text()


class Flat(unittest.TestCase):
    def test_no_stock_excess_or_execution(self):
        self.assertIn("#define FLAT_BYTES 156064U", C)
        self.assertNotIn("TETRIS_GPUEB_LK_COPY_BYTES", C)
        self.assertNotRegex(C, r"\b(writel|readl|rproc_boot|arm_smccc_smc)\s*\(")
        self.assertNotIn("gpueb_inspect_segments", C)

    def test_auth_before_allocation_and_copy(self):
        ordered = ["ret = tetris_gpueb_authenticate(",
                   "if (!reviewed(metadata.plaintext))", "image = calloc(",
                   "ret = lmb_alloc_mem(", "ret = tetris_scp_crypto_check_image(",
                   "writable = 1;", "memcpy(image->mapping,",
                   "ret = tetris_scp_crypto_decrypt(", "*result = image;"]
        positions = [C.index(s) for s in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("metadata.wrapped, metadata.ciphertext, metadata.plaintext", C)

    def test_no_plaintext_publication_or_abi_prefix_claim(self):
        self.assertNotRegex(C, r"\b(fdt_setprop|printf|debug)\s*\(")
        self.assertIn("image->info.sram_offset = 0;", C)
        self.assertNotIn("+ 24", C)

    def test_exact_profile_bytes(self):
        block = C.split("static const u8 profiles[][32] = {", 1)[1].split("\n};", 1)[0]
        raw = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", block))
        self.assertEqual(len(raw), 64)
        self.assertEqual(raw[:32].hex(), "9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7")
        self.assertEqual(raw[32:].hex(), "4cd3ac60605b30f92988a7606e95b7e4f82d70513bbd12923a0e562e9fc31702")

    def test_fail_erase_and_no_retry(self):
        failure = C.split("\nunmap:\n", 1)[1].split("\nint tetris_gpueb_flat_describe", 1)[0]
        self.assertIn("if (writable)", failure)
        self.assertLess(failure.index("erase(image->mapping"), failure.index("unmap_sysmem("))
        self.assertEqual(C.count("tetris_scp_crypto_decrypt("), 1)
        self.assertIn("erase(&metadata, sizeof(metadata));", failure)

    def test_actual_allocation_not_single_address_check(self):
        self.assertIn("LMB_MEM_ALLOC_MAX, RESERVE_ALIGN, &base", C)
        self.assertIn("RESERVE_BYTES, RESERVE_FLAGS", C)
        self.assertNotIn("lmb_is_reserved_flags", C)
        self.assertIn("RESERVE_FLAGS | LMB_NONOTIFY", C)
        self.assertIn("overlaps(image->mapping, RESERVE_BYTES, protected[i]", C)
        self.assertIn("if (*result)\n\t\treturn -EALREADY;", C)

    @unittest.skipUnless(os.environ.get("TETRIS_B41_LK"), "private LK not supplied")
    def test_actual_signed_lk_no_expansion(self):
        route = cold_route(signed_lk(Path(os.environ["TETRIS_B41_LK"]).read_bytes()))
        self.assertEqual(route["uncovered_copy_bytes"], 102680)
        self.assertFalse(route["launch_available"])

    @unittest.skipUnless(os.environ.get("TETRIS_GPUEB_CONTAINER"), "signed container not supplied")
    def test_actual_signed_primary(self):
        data = Path(os.environ["TETRIS_GPUEB_CONTAINER"]).read_bytes()
        fw.inspect(data, ROOT_PIN)
        sections = fw.sections(data)
        self.assertEqual(len(sections[0].payload), 156064)
        _, fields = fw.certificate(sections[2].payload)
        signed_digest = fw.bits(fw.metadata(fields, 4, 2), 32).hex()
        self.assertIn(signed_digest, (
            "9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7",
            "4cd3ac60605b30f92988a7606e95b7e4f82d70513bbd12923a0e562e9fc31702"))


if __name__ == "__main__":
    unittest.main()
