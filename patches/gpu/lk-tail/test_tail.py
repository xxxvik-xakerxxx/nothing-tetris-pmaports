#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Offline regression tests; fixtures are supplied privately, never embedded."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import audit_tail as audit


class TailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = audit.read_bounded(ARGS.snapshot, audit.PRIMARY_BYTES, True)
        cls.raw = audit.read_bounded(ARGS.lk, audit.LIMIT)
        size = struct.unpack_from("<I", cls.raw, 4)[0]
        cls.payload = cls.raw[512:512 + size]
        cls.report = audit.audit(cls.primary, cls.raw)
        cls.code = {}
        for _, start, end, _ in audit.WINDOWS:
            cls.code.update(audit.decode(cls.payload, start, end))

    def test_identity_and_tail_bounds(self):
        proof = self.report["local_proofs"]
        self.assertEqual(proof["tail_bytes"], 102680)
        self.assertEqual(proof["copy_words"], 64686)
        self.assertEqual(proof["tail_source_relative_to_mapping"], [0x261b8, 0x3f2d0])
        self.assertEqual(proof["tail_destination_relative_to_sram"], [0x261a0, 0x3f2b8])
        self.assertLess(0x3f2d0, 0x100000)

    def test_not_a_completed_writer_proof(self):
        for key in ("producer_resolved", "scratch_proven", "zero_proven",
                    "copy_or_padding_authorized", "activation_permitted"):
            self.assertIs(self.report["conclusion"][key], False)
        self.assertTrue(self.report["unexpanded_call_frontier"])
        self.assertFalse(self.report["coverage"]["whole_program_or_transitive_writer_proof"])

    def test_actual_branch_constant_excludes_high_allocation(self):
        caller = next(w for w in self.report["census"] if w["name"] == "caller")
        calls = {c["site"]: c for c in caller["calls"]}
        self.assertFalse(calls[0x1ecb0]["caller_reachable"])
        self.assertTrue(calls[0x1ed4c]["caller_reachable"])
        self.assertTrue(calls[0x1edbc]["caller_reachable"])

    def test_cache_is_not_zero_fill(self):
        cache = next(w for w in self.report["census"] if w["name"] == "cache")
        self.assertEqual(cache["calls"], [])
        self.assertEqual([(w["site"], w["operation"]) for w in cache["writers"]],
                         [(0x5e7c, "dc")])
        self.assertFalse(self.report["local_proofs"]["post_load_cache"]["fills_memory"])

    def test_callback_excludes_actions_but_retains_frontiers(self):
        proof = self.report["local_proofs"]["post_load_callback"]
        self.assertEqual(proof["rv33_action_calls"], [])
        for action in (0x7db5c, 0x7dbdc, 0x7dc5c, 0x7db90, 0x7dc10, 0x7dc90):
            self.assertNotIn(action, proof["reachable_sites"])
        for pc in (0x7db30, 0x7db48, 0x7dbc8, 0x7dc48, 0x7dce8):
            self.assertIn(pc, proof["reachable_sites"])

    def test_all_decode_and_store_census_is_bounded(self):
        self.assertEqual(len(self.report["census"]), len(audit.WINDOWS))
        for w in self.report["census"]:
            self.assertEqual(w["decoded_instructions"], (w["end_exclusive"] - w["start"]) // 4)
            for writer in w["writers"]:
                self.assertLessEqual(w["start"], writer["site"])
                self.assertLess(writer["site"], w["end_exclusive"])
        caller = next(w for w in self.report["census"] if w["name"] == "caller")
        self.assertIn(0x1ee14, [w["site"] for w in caller["writers"]])

    def test_indirect_branches_never_assumed_safe(self):
        windows = {w["name"]: w for w in self.report["census"]}
        mapper = windows["arch_map"]["exits"]
        self.assertEqual([e for e in mapper if e["kind"] == "br"], [])
        self.assertEqual(audit.mapper_tables(self.payload, self.code),
                         {0x7048: [0x7090, 0x704c, 0x7084, 0x708c],
                          0x7078: [0x7124, 0x707c, 0x7118, 0x7120]})
        self.assertIn({"site": 0x67f08, "kind": "br", "target": None},
                      windows["byte_reader_dispatch"]["exits"])

    def test_mapper_table_mutations_and_bad_edges(self):
        for table in (0xce0bc, 0xce0ac):
            changed = bytearray(self.payload)
            struct.pack_into("<i", changed, table, -0x10000)
            with self.assertRaisesRegex(ValueError, "mapper table changed"):
                audit.mapper_tables(changed, self.code)
        code = audit.decode(self.payload, 0x6f94, 0x71d4)
        with self.assertRaisesRegex(ValueError, "invalid jump table"):
            audit.cfg(code, 0x6f94, jump_edges={0x7048: [0x100]})

    def test_each_window_mutation_rejected(self):
        for name, start, _, _ in audit.WINDOWS:
            with self.subTest(window=name):
                changed = bytearray(self.raw)
                changed[512 + start] ^= 1
                with self.assertRaisesRegex(ValueError, "LK identity"):
                    audit.audit(self.primary, changed)

    def test_primary_mutation_and_extension_rejected(self):
        for data in (self.primary[:-1], self.primary + b"\0",
                     bytes([self.primary[0] ^ 1]) + self.primary[1:]):
            with self.assertRaisesRegex(ValueError, "primary identity"):
                audit.audit(data, self.raw)

    def test_container_framing(self):
        for offset, value in ((0, 0), (4, audit.LIMIT), (48, 0), (52, 511)):
            changed = bytearray(self.raw)
            struct.pack_into("<I", changed, offset, value)
            with self.assertRaises(ValueError):
                audit.audit(self.primary, changed)
        with self.assertRaises(ValueError):
            audit.audit(self.primary, self.raw[:511])

    def test_semantic_mutation_without_identity_guard(self):
        # These exercise the local proof itself, independently of the outer hash.
        for pc in (0x16ec0, 0x1ed8c, 0x1ee00, 0x1ee18, 0x5e7c, 0x7dc4c):
            with self.subTest(pc=hex(pc)):
                changed = dict(self.code)
                changed[pc] = self.code[0x16ec4]
                with self.assertRaises(ValueError):
                    audit.local_proofs(changed, self.payload)

    def test_unknown_name_rejected(self):
        changed = bytearray(self.payload)
        changed[0xb80f5] ^= 1
        with self.assertRaisesRegex(ValueError, "name mismatch"):
            audit.local_proofs(self.code, changed)

    def test_decode_bounds_and_version(self):
        for start, end in ((-4, 4), (1, 8), (0, 3), (4, 4), (0, len(self.payload) + 4)):
            with self.assertRaises(ValueError):
                audit.decode(self.payload, start, end)
        with self.assertRaisesRegex(ValueError, "budget"):
            audit.decode(self.payload, 0, (audit.MAX_INSTRUCTIONS + 1) * 4)
        with self.assertRaisesRegex(ValueError, "incomplete decode"):
            audit.decode(b"\xff" * 4, 0, 4)
        with patch.object(audit.capstone, "__version__", "6.0.0"):
            with self.assertRaisesRegex(ValueError, "5.0.6"):
                audit.decode(self.payload, 0x16ec0, 0x16ec8)

    def test_bad_cfg_decision_rejected(self):
        code = audit.decode(self.payload, 0x5e74, 0x5e94)
        with self.assertRaises(ValueError):
            audit.cfg(code, 0x5e74, {0x5e88: 0x100})
        with self.assertRaises(ValueError):
            audit.cfg(code, 0x5e74, {0x100: 0x104})

    def test_reports_contain_no_firmware_or_snapshot_path(self):
        text = json.dumps(self.report)
        self.assertNotIn(str(ARGS.snapshot), text)
        self.assertNotIn(self.primary[:32].hex(), text)
        self.assertNotIn("op_str", text)

    def test_private_file_and_alias_handling(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            data, symlink, hardlink = root / "data", root / "link", root / "hard"
            data.write_bytes(b"fixture")
            data.chmod(0o600)
            self.assertEqual(audit.read_bounded(data, 7, True), b"fixture")
            with self.assertRaises(ValueError):
                audit.read_bounded(data, 6)
            data.chmod(0o644)
            with self.assertRaises(ValueError):
                audit.read_bounded(data, 7, True)
            symlink.symlink_to(data)
            with self.assertRaises(OSError):
                audit.read_bounded(symlink, 7)
            os.link(data, hardlink)
            for output in (data, symlink, hardlink):
                with self.assertRaises(ValueError):
                    audit.write_report(output, self.report, (data,))
            output = root / "report.json"
            audit.write_report(output, self.report, (data,))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(output.read_text()), self.report)

    def test_cli_strict_gate_and_failure_preserve_previous_report(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            output = Path(directory) / "report.json"
            argv = ["audit_tail.py", "--snapshot", str(ARGS.snapshot), "--lk", str(ARGS.lk),
                    "--output", str(output), "--require-closure"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    audit.main()
            self.assertEqual(result.exception.code, 2)
            self.assertEqual(json.loads(output.read_text()), self.report)
            previous = output.read_bytes()
            bad = Path(directory) / "bad"
            bad.write_bytes(b"bad")
            bad.chmod(0o600)
            argv[2] = str(bad)
            with patch.object(sys, "argv", argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    audit.main()
            self.assertEqual(result.exception.code, 1)
            self.assertEqual(output.read_bytes(), previous)
            self.assertEqual(list(Path(directory).glob(".lk-tail-*")), [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--lk", required=True, type=Path)
    ARGS = parser.parse_args()
    unittest.main(argv=[sys.argv[0]], verbosity=2)
