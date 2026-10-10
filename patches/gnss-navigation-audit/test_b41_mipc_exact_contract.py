#!/usr/bin/env python3
"""Offline exact-asset assertions and dependency-closure fault fixtures."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

from b41_mipc_elf_audit import read_elf
from b41_mipc_exact_contract import MIPC_SHA, NEEDED, contract, dependency_closure


def fixture(name, needed=(), symbols=()):
    return {"path": "/fixture/" + name, "sha256": "fixture-only",
            "dynamic": {"DT_NEEDED": list(needed), "DT_SONAME": [name]},
            "symbols": list(symbols)}


class ContractTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TETRIS_B41_MIPC_SO"), "exact stock asset not supplied")
    def test_exact_library_contract(self):
        image = read_elf(Path(os.environ["TETRIS_B41_MIPC_SO"]), MIPC_SHA)
        result = contract(image)
        self.assertEqual(result["length_output"]["type"], "uint16_t*")
        self.assertFalse(result["accessor_guarantees_four_bytes"])
        self.assertFalse(result["deinit_is_rx_join_ack"])
        self.assertFalse(result["vendor_parser_fully_bounds_safe"])
        self.assertFalse(result["engine_readiness"])
        bad = copy.deepcopy(image)
        bad["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            contract(bad)
        for segment in bad["segments"]:
            if segment["address"] <= 0xf260 < segment["address"] + len(segment["data"]):
                offset = 0xf260 - segment["address"]
                data = bytearray(segment["data"])
                data[offset:offset + 4] = b"\0" * 4
                segment["data"] = bytes(data)
        bad["sha256"] = MIPC_SHA
        with self.assertRaisesRegex(ValueError, "opcode mismatch"):
            contract(bad)

    def test_missing_real_closure(self):
        result = dependency_closure(fixture("libmipc.so", NEEDED), [])
        self.assertEqual(result["missing"], sorted(NEEDED))
        self.assertFalse(result["file_and_symbol_name_closure_complete"])

    def test_nested_closure_cycle_and_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("liba.so", "libb.so"):
                (root / name).touch()
            required = {"name": "real_service", "undefined": True, "binding": "STB_GLOBAL",
                        "visibility": "STV_DEFAULT"}
            supplied = {**required, "undefined": False}
            base = fixture("libmipc.so", ["liba.so"], [required])
            records = {"liba.so": fixture("liba.so", ["libb.so"]),
                       "libb.so": fixture("libb.so", ["liba.so"], [supplied])}
            result = dependency_closure(base, [root], lambda path: records[path.name])
            self.assertTrue(result["file_and_symbol_name_closure_complete"])
            self.assertFalse(result["engine_readiness"])
            self.assertFalse(result["symbol_versions_and_runtime_abi_proven"])
            records["libb.so"]["symbols"] = []
            result = dependency_closure(base, [root], lambda path: records[path.name])
            self.assertEqual(result["unresolved_required_symbol_names"],
                             {"libmipc.so": ["real_service"]})
            self.assertFalse(result["file_and_symbol_name_closure_complete"])

    def test_ambiguous_and_wrong_soname(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            roots = [Path(a), Path(b)]
            for root in roots:
                (root / "liba.so").touch()
            base = fixture("libmipc.so", ["liba.so"])
            def forbidden_read(path):
                self.fail("ambiguous library must not be silently selected")
            result = dependency_closure(base, roots, forbidden_read)
            self.assertIn("liba.so", result["ambiguous"])
            result = dependency_closure(base, roots[:1], lambda path: fixture("libwrong.so"))
            self.assertIn("liba.so", result["rejected"])

    def test_no_path_substitution(self):
        result = dependency_closure(fixture("libmipc.so", ["../liba.so"]), [])
        self.assertIn("../liba.so", result["rejected"])
        self.assertFalse(result["file_and_symbol_name_closure_complete"])


if __name__ == "__main__":
    unittest.main()
