#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""B4.1 binary contract gate; external hash-pinned LK/ATF inputs required."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import audit_gpueb_b41 as b41


class B41(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lk_raw = b41.read_bounded(cls.lk_path, b41.MAX_LK)
        cls.atf_raw = b41.read_bounded(cls.atf_path, 900752)
        cls.lk = b41.signed_lk(cls.lk_raw)
        cls.atf = b41.pinned_atf(cls.atf_raw)

    def test_signed_lk_and_independent_atf_identity(self):
        report = b41.trace(self.lk, self.atf)
        self.assertEqual(report["lk_sha256"], b41.LK_SHA)
        self.assertEqual(report["atf_sha256"], b41.ATF_SHA)
        self.assertEqual(report["selector"], 1)
        self.assertEqual(report["mode"], 0)
        self.assertFalse(report["execution_permitted"])

    def test_callback_does_not_select_or_expand_rv33(self):
        report = b41.trace(self.lk, self.atf)
        self.assertEqual(report["post_load_callback"]["names"], ["pvmfw", "atf", "tee"])
        self.assertFalse(report["post_load_callback"]["rv33_selected"])
        self.assertEqual(report["stock_copy_bytes"], 258744)
        self.assertNotEqual(report["stock_copy_bytes"], 156064)
        self.assertIn("no expansion-size ABI", report["transform"])

    def test_smc_descriptor_is_not_an_execution_command(self):
        report = b41.trace(self.lk, self.atf)
        self.assertEqual(report["smc"], "0xc2000133")
        self.assertEqual(report["smc_arguments"], {"x1": 1, "x2_x3_x4_x5_x6_x7": 0})
        self.assertEqual(report["descriptor"]["image_bytes"], "+0x48/u32")
        self.assertEqual(report["descriptor"]["wrapped_bytes"], "+0x58/u32")

    def test_resolved_producers_do_not_supply_an_expanded_extent(self):
        report = b41.producer_bounds(self.lk, self.atf)
        self.assertEqual(report["authenticated_success_transform"],
                         "0x93068 -> 0x931d0 -> 0x91fa0")
        self.assertEqual(report["success_skips_fallback_transform"],
                         "0x7508c -> 0x750cc")
        self.assertIn("0x680c8", report["partition_byte_callback"])
        self.assertIn("bounded memcpy", report["partial_block_destination"])
        self.assertIn("0x36478", report["ufs_read_callback"])
        self.assertIn("0x37fec", report["atf_cipher_callback"])
        self.assertEqual(report["cipher_dma_extent"],
                         "original count; output PA + original count - 1")
        self.assertEqual(report["tail_initialization_producer"],
                         "unresolved in pinned stock control path")
        self.assertFalse(report["execution_permitted"])

    def test_producer_trace_rejects_wrong_identity(self):
        with self.assertRaises(ValueError):
            b41.producer_bounds(self.lk[:-1], self.atf)
        with self.assertRaises(ValueError):
            b41.producer_bounds(self.lk, self.atf[:-1])

    def test_producer_instruction_and_callback_mutants_rejected(self):
        cases = (("lk", (0x7508c, 0x931d0, 0x68acc, 0x68b40,
                          0x68088, 0x68198, 0x681f0, 0x6832c,
                          0x3ad4c, 0x367d8, 0x364e0)),
                 ("atf", (0x24d14, 0x59f0, 0x464f8, 0x5a9c,
                           0x3806c, 0x14ac, 0x14b8, 0x14c0, 0x1594)))
        for name, offsets in cases:
            for offset in offsets:
                lk, atf = bytearray(self.lk), bytearray(self.atf)
                changed = lk if name == "lk" else atf
                changed[offset:offset + 4] = b"\0" * 4
                # Bypass only the hash gate to exercise actual ABI assertions.
                with self.subTest(binary=name, offset=hex(offset)), \
                        patch.object(b41.hashlib, "sha256") as digest:
                    digest.return_value.hexdigest.side_effect = (b41.LK_SHA, b41.ATF_SHA)
                    with self.assertRaises(ValueError):
                        b41.producer_bounds(bytes(lk), bytes(atf))

    def test_wrong_lk_and_truncations_rejected(self):
        for end in (0, 511, 512, 512 + len(self.lk)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                b41.signed_lk(self.lk_raw[:end])
        for offset in (0, 4, 8, 48, 512 + 0x1ed94):
            changed = bytearray(self.lk_raw)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                b41.signed_lk(bytes(changed))

    def test_atf_and_instruction_mutants_rejected(self):
        for end in (0, 511, 512, len(self.atf_raw) - 1):
            with self.subTest(end=end), self.assertRaises(ValueError):
                b41.pinned_atf(self.atf_raw[:end])
        changed = bytearray(self.atf_raw)
        changed[512 + 0x2c0c0] ^= 1
        with self.assertRaises(ValueError):
            b41.pinned_atf(bytes(changed))
        with self.assertRaises(ValueError):
            b41.expect(self.lk, 0x7e348, "b", "#0x920e4")

    def test_cli_does_not_modify_inputs_or_expose_contents(self):
        result = subprocess.run([sys.executable, b41.__file__, "--lk", str(self.lk_path),
                                 "--atf", str(self.atf_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["execution_permitted"])
        self.assertEqual(b41.read_bounded(self.lk_path, b41.MAX_LK), self.lk_raw)
        self.assertEqual(b41.read_bounded(self.atf_path, 900752), self.atf_raw)
        self.assertNotIn("wrapped_material", report)
        self.assertNotIn("plaintext", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lk", type=Path, required=True)
    parser.add_argument("--atf", type=Path, required=True)
    args = parser.parse_args()
    B41.lk_path, B41.atf_path = args.lk, args.atf
    unittest.main(argv=[__file__])
