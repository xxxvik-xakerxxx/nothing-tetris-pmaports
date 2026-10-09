#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Offline regression tests; stock assets stay private and optional."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from audit_gpueb_allocation import trace
from audit_gpueb_b41 import signed_lk


class AllocationTests(unittest.TestCase):
    def test_wrong_identity_rejected(self):
        with self.assertRaises(ValueError):
            trace(b"\0" * 0x200000)

    @unittest.skipUnless(os.environ.get("TETRIS_B41_LK"), "private LK not supplied")
    def test_signed_exact_stock_and_no_zero_claim(self):
        code = signed_lk(Path(os.environ["TETRIS_B41_LK"]).read_bytes())
        result = trace(code)
        self.assertEqual(result["reservation"]["bytes"], 1048576)
        self.assertEqual(result["mapping"]["zero_allocated_descriptor_bytes"], 88)
        self.assertEqual(result["reader"]["temporary_header_allocation_bytes"], 512)
        self.assertEqual(result["reader"]["actual_backing_remaining_bytes"], 1048552)
        self.assertEqual(result["unauthenticated_copy_excess_bytes"], 102680)
        self.assertFalse(result["full_staging_zero_proven"])
        self.assertFalse(result["zero_tail_allowed"])
        self.assertFalse(result["zero_tail_is_bss_proven"])
        self.assertFalse(result["execution_allowed"])

    @unittest.skipUnless(os.environ.get("TETRIS_B41_LK"), "private LK not supplied")
    def test_instruction_mismatch_even_with_identity_mock(self):
        code = signed_lk(Path(os.environ["TETRIS_B41_LK"]).read_bytes())
        for offset in (0x1ec60, 0x1ecfc, 0x675ec, 0x74dfc, 0x1ed8c,
                       0x1ede4, 0x1edf8, 0x1ef04, 0x1ef10):
            modified = bytearray(code)
            modified[offset:offset + 4] = b"\0" * 4
            # Bypass identity ONLY in this negative fixture to reach ABI checks.
            with patch("audit_gpueb_allocation.hashlib.sha256") as digest:
                from audit_gpueb_b41 import LK_SHA
                digest.return_value.hexdigest.return_value = LK_SHA
                with self.assertRaises(ValueError):
                    trace(bytes(modified))


if __name__ == "__main__":
    unittest.main()
