#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Offline tests. Private binaries remain external; no firmware fixtures emitted."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import audit_startup as audit


class Startup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = audit.read_bounded(cls.snapshot_path, audit.PRIMARY_BYTES, private=True)
        cls.lk = audit.read_bounded(cls.lk_path, audit.LK_LIMIT)
        cls.report = audit.audit(cls.primary, cls.lk)

    def test_actual_entry_selection_and_cold_dominance(self):
        selection = self.report["selection"]
        self.assertEqual(self.report["entry"], 0xac)
        self.assertEqual(selection["gpr"], 0x3fd78)
        self.assertEqual((selection["mask"], selection["warm_if_equal"]), (7, 7))
        self.assertEqual((selection["warm_target"], selection["cold_target"]), (0xcc, 0x144))
        self.assertEqual(selection["alternate_gpr"], 0x3fd20)
        dominance = self.report["caller_dominance"]
        self.assertTrue(dominance["proven"])
        self.assertFalse(dominance["unconditional_startup_proven"])
        self.assertIn("assumes callees return", dominance["scope"])
        self.assertEqual(dominance["barrier"]["call"], 0x268)

    def test_pc_relative_branch_jal_and_negative_jump(self):
        code = audit.decode_window(self.primary, 0xac, 0x354)
        helper = audit.decode_window(self.primary, 0x1da8, 0x1dbc)
        for pc, target in ((0xc4, 0xcc), (0xc8, 0x144), (0x150, 0x158),
                           (0x154, 0x1e84), (0x15c, 0x1e38), (0x268, 0x1eb0),
                           (0x310, 0x1da8), (0x328, 0x1da8), (0x344, 0x1da8),
                           (0x350, 0x13230)):
            with self.subTest(pc=pc):
                self.assertEqual(audit.relative_target(code[pc]), target)
                self.assertEqual(audit.relative_target(code[pc]), pc + audit.immediate(code[pc]))
        self.assertEqual(audit.relative_target(helper[0x1db4]), 0x1da8)

    def test_exact_fill_ranges_and_zero_snapshot(self):
        fills = self.report["fills"]
        self.assertEqual([(f["start"], f["end_exclusive"], f["word"]) for f in fills],
                         [(0x1b538, 0x2619c, 0), (0x1b538, 0x1b538, 0),
                          (0x18c00, 0x197f0, 0xabababab)])
        self.assertEqual(fills[0]["bytes"], 0xac64)
        self.assertEqual(fills[1]["bytes"], 0)
        self.assertEqual(self.report["stack_pointer"], 0x197f0)
        self.assertFalse(any(self.primary[0x1b538:0x2619c]))

    def test_tail_is_not_bss_or_upload_authorization(self):
        gap = self.report["layout_gap"]
        self.assertEqual((gap["start"], gap["end_exclusive"], gap["bytes"]),
                         (0x261a0, 0x3f2b8, 102680))
        self.assertEqual(gap["cold_fill_overlap_bytes"], 0)
        self.assertEqual(gap["bss_end_to_primary_end_bytes"], 4)
        self.assertEqual((gap["stock_clear_only_start"], gap["stock_clear_only_end_exclusive"]),
                         (0x3f2b8, 0x40000))
        self.assertFalse(self.report["conclusion"]["activation_permitted"])
        self.assertFalse(self.report["conclusion"]["all_required_initial_sram_text_data_proven"])
        self.assertEqual(self.report["conclusion"]["tail_initialization_producer"], "unresolved")

    def test_alternate_full_sram_reader_and_empty_early_copy(self):
        copy = self.report["alternate_tail_consumer"]
        self.assertEqual((copy["helper"], copy["load_instruction"]), (0x1e84, 0x1e68))
        self.assertEqual((copy["source_start"], copy["source_end_exclusive"]), (0, 0x40000))
        self.assertEqual(copy["destination_start"], 0x50000000)
        self.assertIn("GPR 0x3fd20 != 0", copy["condition"])
        self.assertEqual(self.report["early_copy"]["source_reads"], 0)
        self.assertEqual(self.report["post_copy_pointer_producers"]["values"], [0x3f2b8, 0x3f6b8])

    def test_unknown_vendor_instruction_remains_opaque(self):
        code = audit.decode_window(self.primary, 0x1eb0, 0x1ec4,
                                   (0x1eb0, 0x1eb4, 0x1eb8, 0x1ebc))
        self.assertIsNone(code[0x1eb0])
        self.assertEqual(code[0x1ec0].mnemonic, "ret")
        operand = self.report["opaque_warm_operand"]
        self.assertEqual((operand["instruction"], operand["a0_a1"]), (0x10810, 0x26158))
        self.assertIn("no inferred memory access", operand["semantics"])
        with self.assertRaises(ValueError):
            audit.decode_window(self.primary, 0x1eb0, 0x1ec4)

    def test_identity_rejects_mutations_every_region(self):
        for offset in (0, 4, 0x1c, 0xc4, 0x310, 0x1eb0, 0x10810,
                       0x1b537, 0x1b538, 0x2619c, audit.PRIMARY_BYTES - 1):
            mutant = bytearray(self.primary)
            mutant[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "identity"):
                audit.audit(mutant, self.lk)
        for data in (b"", self.primary[:-1], self.primary + b"\0"):
            with self.assertRaises(ValueError):
                audit.audit(data, self.lk)

    def test_semantic_mutations_rejected_independently_of_whole_hash(self):
        # Exercise semantic assertions rather than stopping at the identity gate.
        for offset in (0xc4, 0xc8, 0x150, 0x154, 0x15c, 0x268, 0x2fc, 0x300,
                       0x304, 0x308, 0x30c, 0x310, 0x324, 0x328, 0x340, 0x344,
                       0x34c, 0x1da8, 0x1dac, 0x1db0, 0x1db4, 0x1db8,
                       0x1e48, 0x1e54, 0x1e68, 0x1e78, 0x1e9c, 0x10080):
            mutant = bytearray(self.primary)
            mutant[offset:offset + 4] = self.primary[0x354:0x358]  # Known nop.
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                audit.prove_layout(mutant)
        for offset in (4, 0x1c, 0x1b538):
            mutant = bytearray(self.primary)
            mutant[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                audit.prove_layout(mutant)

    def test_cold_bypass_fails_dominance(self):
        code = audit.decode_window(self.primary, 0, 4)
        code.update(audit.decode_window(self.primary, 0xac, 0x354))
        # Mutated entry j +0x310 skips cold branch selection in the caller graph.
        bypass = ((0x310 & 0x7fe) << 20) | 0x6f
        code[0] = audit.decode_window(bypass.to_bytes(4, "little"), 0, 4)[0]
        dom = audit.caller_dominators(code)
        self.assertNotIn(0xc8, dom[0x310])
        self.assertNotIn(0x150, dom[0x310])
        middle = ((0xae & 0x7fe) << 20) | 0x6f
        code[0] = audit.decode_window(middle.to_bytes(4, "little"), 0, 4)[0]
        with self.assertRaisesRegex(ValueError, "instruction boundary"):
            audit.caller_dominators(code)

    def test_signed_negative_auipc_address(self):
        code = audit.decode_window(self.primary, 0x1df8, 0x1eb0)
        self.assertEqual(audit.address_pair(code, 0x1dfc, 0x1e00, "t0"), 4)
        with self.assertRaises(ValueError):
            audit.address_pair(code, 0x1dfc, 0x1e00, "a0")

    def test_decoder_boundaries_unknowns_and_budget(self):
        for start, end in ((-2, 4), (0, 3), (1, 4), (0, len(self.primary) + 2), (0, 2)):
            with self.subTest(bounds=(start, end)), self.assertRaises(ValueError):
                audit.decode_window(self.primary, start, end)
        with self.assertRaises(ValueError):
            audit.decode_window(b"\x1f\0\0\0", 0, 4)
        with self.assertRaises(ValueError):
            audit.decode_window(self.primary[0x1eb0:0x1eb4] +
                                self.primary[0x354:0x358], 0, 8)
        with self.assertRaises(ValueError):
            audit.decode_window(self.primary, 0xac, 0xb4, (0xae,))
        with self.assertRaises(ValueError):
            audit.decode_window(self.primary, 0xac, 0xb4, (0x100,))
        with self.assertRaises(ValueError):
            audit.decode_window(self.primary, 0xac, 0xb4, (0xac,))
        with patch.object(audit, "MAX_INSTRUCTIONS", 1), self.assertRaises(ValueError):
            audit.decode_window(self.primary, 0xac, 0xb4)
        with patch.object(audit.capstone, "__version__", "unsupported"), self.assertRaises(ValueError):
            audit.decoder()

    def test_lk_identity_and_header_mutations(self):
        for offset in (0, 4, 8, 48, 52, 512 + 0x1ee00, 512 + 0x1ee18):
            mutant = bytearray(self.lk)
            mutant[offset] ^= 255
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                audit.prove_lk(mutant)
        for end in (0, 511, 512, 1024):
            with self.assertRaises(ValueError):
                audit.prove_lk(self.lk[:end])

    def test_bounded_regular_private_input_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"synthetic")
            path.chmod(0o600)
            self.assertEqual(audit.read_bounded(path, 9, private=True), b"synthetic")
            with self.assertRaises(ValueError):
                audit.read_bounded(path, 8)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                audit.read_bounded(path, 9, private=True)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                audit.read_bounded(link, 9)
            fifo = Path(directory) / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                audit.read_bounded(fifo, 9)

    def test_atomic_private_output_and_failure_preserves_old_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text("old report", encoding="ascii")
            with patch.object(audit.os, "replace", side_effect=OSError), self.assertRaises(OSError):
                audit.write_atomic(path, self.report, (self.snapshot_path, self.lk_path))
            self.assertEqual(path.read_text(), "old report")
            self.assertEqual(list(Path(directory).iterdir()), [path])
            audit.write_atomic(path, self.report, (self.snapshot_path, self.lk_path))
            self.assertEqual(json.loads(path.read_text()), self.report)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_output_cannot_alias_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic"
            source.write_text("keep", encoding="ascii")
            hardlink = Path(directory) / "hardlink"
            os.link(source, hardlink)
            symlink = Path(directory) / "symlink"
            symlink.symlink_to(source)
            for target in (source, hardlink, symlink):
                with self.subTest(target=target.name), self.assertRaises(ValueError):
                    audit.write_atomic(target, {}, (source,))
            self.assertEqual(source.read_text(), "keep")

    def test_cli_no_input_mutation_no_raw_bytes_and_failed_audit_no_publish(self):
        before = hashlib.sha256(self.primary).hexdigest()
        base = [sys.executable, "-B", str(Path(audit.__file__)), "--snapshot",
                str(self.snapshot_path), "--lk", str(self.lk_path)]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            run = subprocess.run(base + ["--output", str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, "")
            report = json.loads(output.read_text())
            self.assertFalse(report["conclusion"]["activation_permitted"])
            self.assertEqual(report, self.report)
            self.assertNotIn("raw", output.read_text())
            keep = output.read_bytes()
            # Wrong existing input: no extra private firmware copy is needed.
            run = subprocess.run(base[:base.index("--snapshot")] +
                                 ["--snapshot", str(self.lk_path), "--lk", str(self.lk_path),
                                  "--output", str(output)], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, "")
            self.assertEqual(output.read_bytes(), keep)
            self.assertIn("no report published", run.stderr)
        self.assertEqual(hashlib.sha256(audit.read_bounded(
            self.snapshot_path, audit.PRIMARY_BYTES, private=True)).hexdigest(), before)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--lk", type=Path, required=True)
    args = parser.parse_args()
    Startup.snapshot_path, Startup.lk_path = args.snapshot, args.lk
    unittest.main(argv=[__file__], verbosity=2)
