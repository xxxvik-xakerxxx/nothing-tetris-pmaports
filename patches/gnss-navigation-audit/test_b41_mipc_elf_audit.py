#!/usr/bin/env python3
"""Narrow structural/error fixtures, deliberately not MIPC runtime tests."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from b41_mipc_elf_audit import API, audit, bytes_at, export, read_elf


def image(name, undefined=False):
    # RET instructions solely exercise bounded disassembly of fixture metadata.
    # They are never executed and never establish a semantic service contract.
    return {"path": "/fixture/" + name, "sha256": "0" * 64,
            "dynamic": {"DT_NEEDED": ["libmipc.so"] if undefined else [],
                        "DT_SONAME": [name], "DT_RPATH": [], "DT_RUNPATH": []},
            "symbols": [{"name": n, "address": 0x1000 + 4 * i, "size": 4,
                         "type": "STT_FUNC", "binding": "STB_GLOBAL",
                         "visibility": "STV_DEFAULT", "undefined": undefined}
                        for i, n in enumerate(API)],
            "segments": [{"address": 0x1000, "flags": 5,
                          "data": b"\xc0\x03\x5f\xd6" * len(API)}]}


class AuditTests(unittest.TestCase):
    def test_required_readable_extent(self):
        value = image("libmipc.so")
        self.assertEqual(len(bytes_at(value, 0x1000, 4, True)), 4)
        for address, size in ((0xfff, 4), (0x101f, 4), (0x1000, -1)):
            with self.assertRaises(ValueError):
                bytes_at(value, address, size, True)
        value["segments"][0]["flags"] = 4
        with self.assertRaises(ValueError):
            export(value, API[0])

    def test_export_rejections(self):
        for key, invalid in (("undefined", True), ("type", "STT_OBJECT"),
                             ("binding", "STB_LOCAL"), ("visibility", "STV_HIDDEN"),
                             ("size", 0), ("size", 3), ("address", 0x1001),
                             ("address", 0x2000)):
            value = image("libmipc.so")
            value["symbols"][0][key] = invalid
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                export(value, API[0])
        value = image("libmipc.so")
        value["symbols"].append(copy.deepcopy(value["symbols"][0]))
        with self.assertRaises(ValueError):
            export(value, API[0])

    def test_dependency_contract_rejections(self):
        mnld, mnl = image("mnld", True), image("libmnl.so")
        mnld["dynamic"]["DT_NEEDED"] = ["/vendor/lib64/libmipc.so"]
        with self.assertRaises(ValueError):
            audit(mnld, mnl)
        mnld["dynamic"]["DT_NEEDED"] = ["libmipc.so", "libmipc.so"]
        with self.assertRaises(ValueError):
            audit(mnld, mnl)
        mnld["dynamic"]["DT_NEEDED"] = ["libmipc.so"]
        mnld["symbols"].pop()
        with self.assertRaises(ValueError):
            audit(mnld, mnl)

    def test_pin_and_malformed_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libmipc.so"
            path.write_bytes(b"not an ELF")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                read_elf(path, "0" * 64)
            from elftools.common.exceptions import ELFError
            with self.assertRaises(ELFError):
                read_elf(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_names_are_not_bounds_or_lifetime_proof(self):
        # Give the synthetic consumer fixture the real code interval solely to
        # exercise report creation, without claiming any source ABI equivalence.
        mnld, mnl, mipc = image("mnld", True), image("libmnl.so"), image("libmipc.so")
        mnld["segments"] = [{"address": 0x7f000, "flags": 5,
                             "data": b"\xc0\x03\x5f\xd6" * 1024}]
        report, status = audit(mnld, mnl, mipc)
        self.assertEqual(status, 0)
        self.assertFalse(report["engine_readiness"])
        self.assertEqual(report["contract"]["tag_word_required_readable_bytes"], 4)
        for key in ("tag_extent_at_least_4_proven", "source_c_signatures_proven",
                    "value_lifetime_until_response_deinit_proven",
                    "sync_response_ownership_proven", "raw_wire_framing_proven"):
            self.assertFalse(report["contract"][key])
        report, status = audit(mnld, mnl)
        self.assertEqual(status, 2)
        self.assertFalse(report["engine_readiness"])
        mipc["dynamic"]["DT_SONAME"] = ["libmipc_other.so"]
        with self.assertRaises(ValueError):
            audit(mnld, mnl, mipc)


if __name__ == "__main__":
    unittest.main()
