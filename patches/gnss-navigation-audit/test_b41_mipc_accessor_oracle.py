#!/usr/bin/env python3
"""Exact-library export/ABI assertions; optional bounded offline emulation."""
import os
from pathlib import Path
import unittest

from b41_mipc_accessor_oracle import inventory, run
from b41_mipc_elf_audit import API, read_elf
from b41_mipc_exact_contract import MIPC_SHA, NEEDED, contract


@unittest.skipUnless(os.environ.get("TETRIS_B41_MIPC_SO"), "exact stock asset not supplied")
class AccessorTests(unittest.TestCase):
    def setUp(self):
        self.image = read_elf(Path(os.environ["TETRIS_B41_MIPC_SO"]), MIPC_SHA)
        contract(self.image)

    def test_exact_export_inventory(self):
        data = inventory(self.image)
        self.assertEqual(data["needed"], NEEDED)
        self.assertEqual([s["name"] for s in data["required_exports"]], list(API))
        self.assertTrue(all(s["binding"] == "STB_GLOBAL" and s["visibility"] == "STV_DEFAULT"
                            and s["size"] > 0 for s in data["required_exports"]))
        imports = {s["name"] for s in data["imports"]}
        self.assertTrue({"mtk_property_get", "mtkLogE", "mtkLogD", "mtkLogI",
                         "pthread_create", "pthread_detach", "read", "close"} <= imports)
        self.assertNotIn("pthread_join", imports)
        self.assertEqual(data["hashmap_get_export"]["address"], 0xe730)
        self.assertFalse(data["engine_readiness"])
        self.assertFalse(data["dependency_files_audited"])

    @unittest.skipUnless(os.environ.get("TETRIS_MIPC_ACCESSOR_EMULATION") == "1",
                         "bounded offline Unicorn oracle not requested")
    def test_getter_instruction_vectors(self):
        data = run(self.image)
        self.assertEqual(data["accessor_vectors_passed"], 72)
        self.assertTrue(data["short_values_return_nonnull"])
        self.assertTrue(data["uint16_length_write_and_surrounding_canary_verified"])
        self.assertTrue(data["null_node_or_value_returns_null_and_length_zero"])
        self.assertFalse(data["parser_transport_or_engine_executed"])
        self.assertFalse(data["engine_readiness"])


if __name__ == "__main__":
    unittest.main()
