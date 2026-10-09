#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Offline trace regression gate; supply the public hash-pinned stock LK input."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import unittest

import audit_gpueb_lk as lk


class Trace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = cls.path.read_bytes()
        cls.code = lk.original_lk(cls.container)

    def test_signed_original_rv33_call_not_xfile(self):
        report = lk.audit(self.code)
        self.assertEqual(report["secure_selector"], 1)
        self.assertEqual(report["transform_mode"], 0)
        self.assertEqual(report["smc"], "0xc2000133")
        self.assertIn("physical OFF unproven", report["timeout_cleanup"])
        self.assertFalse(report["activation_permitted"])

    def test_source_checked_word_fields(self):
        for word, result in ((0, (0, 0)), (0x10000, (1, 0)),
                             (0x210000, (1, 2)), (0xffffffff, (15, 15))):
            self.assertEqual(lk.split_signed_word(self.code, word), result)
        for word in (-1, 1 << 32):
            with self.assertRaises(ValueError):
                lk.split_signed_word(self.code, word)

    def test_protection_table_and_boot_ready_are_separate_contracts(self):
        report = lk.audit(self.code)
        self.assertEqual(report["protection_table"]["smc"], "0x82000415")
        self.assertEqual(report["protection_table"]["arguments"]["x4"], "12")
        self.assertEqual(report["protection_table"]["allocation_bytes"], "0x600000")
        self.assertFalse(report["protection_table"]["lk_checks_return"])
        self.assertEqual(report["ready"], {"gpr_offset": "0x8", "expected": "0x55667788"})
        self.assertNotEqual(report["protection_table"]["smc"], report["smc"])
        self.assertEqual(report["sram_clear_bytes"], "0x40000")
        self.assertEqual(report["sram_copy_bytes"], "0x3f2b8")

    def test_truncation_header_and_payload_mutants_rejected(self):
        for end in (0, 511, 512, 512 + len(self.code)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                lk.original_lk(self.container[:end])
        for offset in (0, 4, 8, 48, 52, 512 + 0x1ed94):
            data = bytearray(self.container)
            data[offset] ^= 255
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                lk.original_lk(bytes(data))

    def test_wrong_instruction_and_selector_pointer_rejected(self):
        with self.assertRaises(ValueError):
            lk.expect(self.code, 0x1ed94, "bl", "#0x49714")
        data = bytearray(self.code)
        data[0x19a680] ^= 1
        with self.assertRaises(ValueError):
            lk.split_signed_word(bytes(data), 0x10000)
        data = bytearray(self.code)
        data[0x94fec:0x94ff0] = bytes(4)
        with self.assertRaises(ValueError):
            lk.split_signed_word(bytes(data), 0x10000)

    def test_cli_is_static_and_never_claims_boot(self):
        before = self.path.read_bytes()
        result = subprocess.run([sys.executable, str(Path(lk.__file__)), str(self.path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["activation_permitted"])
        self.assertIn("no execution", report["scope"])
        self.assertEqual(before, self.path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lk", type=Path, required=True)
    args = parser.parse_args()
    Trace.path = args.lk
    unittest.main(argv=[__file__])
