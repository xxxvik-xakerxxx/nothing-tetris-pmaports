#!/usr/bin/env python3
"""Fault tests for cached-stock container boundaries; no archive/device needed."""
from pathlib import Path
import struct
import tempfile
import unittest
from audit_stock_lna_dt import table_entries, vendor_dtb


def table():
    fdt = struct.pack(">2I", 0xd00dfeed, 40) + bytes(32)
    return (struct.pack(">8I", 0xd7b7ab1e, 104, 32, 32, 1, 32, 2048, 0) +
            struct.pack(">8I", 40, 64, 0, 0, 0, 0, 0, 0) + fdt)


class BoundsTests(unittest.TestCase):
    def test_table_exact_bounds(self):
        self.assertEqual(len(table_entries(table())), 1)
        self.assertEqual(table_entries(table() + bytes(4096)), table_entries(table()))

    def test_reject_invalid_headers_and_entries(self):
        for offset, value in ((0, 0), (4, 1000), (8, 0), (12, 16), (16, 0),
                              (16, 33), (20, 0), (28, 1), (32, 39),
                              (36, 0), (36, 1000), (64, 0), (68, 41)):
            with self.subTest(offset=offset, value=value):
                data = bytearray(table())
                struct.pack_into(">I", data, offset, value)
                with self.assertRaises(ValueError):
                    table_entries(data)
        with self.assertRaises(ValueError):
            table_entries(bytes(31))

    def test_overlap_rejected(self):
        data = (struct.pack(">8I", 0xd7b7ab1e, 136, 32, 32, 2, 32, 2048, 0) +
                struct.pack(">8I", 40, 96, 0, 0, 0, 0, 0, 0) * 2 + table()[64:])
        with self.assertRaisesRegex(ValueError, "overlapping"):
            table_entries(data)

    def test_vendor_header_extraction_and_truncation(self):
        header = bytearray(4096)
        header[:8] = b"VNDRBOOT"
        struct.pack_into("<2I", header, 8, 4, 4096)
        struct.pack_into("<I", header, 24, 0)
        struct.pack_into("<2I", header, 2096, 2128, len(table()))
        with tempfile.TemporaryDirectory(prefix="gnss-vendor-header-") as directory:
            image = Path(directory) / "vendor_boot.img"
            image.write_bytes(header + table())
            self.assertEqual(vendor_dtb(image), (4096, table()))
            image.write_bytes(header + table()[:-1])
            with self.assertRaisesRegex(ValueError, "truncated"):
                vendor_dtb(image)
            struct.pack_into("<I", header, 12, 1000)
            image.write_bytes(header + table())
            with self.assertRaisesRegex(ValueError, "unsupported"):
                vendor_dtb(image)


if __name__ == "__main__":
    unittest.main()
