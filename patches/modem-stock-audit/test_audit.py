"""Synthetic parser tests. No vendor execution, files or Capstone required."""
import struct
import unittest

from audit import BASE, SIZE, address_candidates, cstring, payload, registry


class AuditTests(unittest.TestCase):
    def test_reject_unpinned_and_truncated_container(self):
        for data in (b"", b"\0" * 512, b"\0" * (SIZE + 512)):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                payload(data)

    def test_string_bounds(self):
        for offset in (-1, 4):
            with self.assertRaises(ValueError):
                cstring(b"abc\0", offset)
        with self.assertRaises(ValueError):
            cstring(b"abc", 0)
        self.assertEqual(cstring(b"abc\0", 0), "abc")

    def test_registry_preserves_duplicate_callbacks(self):
        data = bytearray(SIZE)
        data[0x100:0x105] = b"test\0"
        for off in (0x199a30, 0x199a48):
            struct.pack_into("<IIQQ", data, off, 0x88610020, 0, BASE + 4, BASE + 0x100)
        result = registry(data)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["unique_ids"], 1)
        self.assertEqual(result["end"], "0x199a60")
        struct.pack_into("<Q", data, 0x199a50, BASE + SIZE)
        with self.assertRaises(ValueError):
            registry(data)

    def test_no_registry_without_anchor(self):
        with self.assertRaises(ValueError):
            registry(bytes(SIZE))

    def test_adr_positive_and_negative_immediate(self):
        data = bytearray(0xa0040)
        # ADR x0, PC+0x100 at offset 0; ADR x0, PC-0x100 at 0x200.
        struct.pack_into("<I", data, 0, 0x10000000 | (0x40 << 5))
        struct.pack_into("<I", data, 0x200, 0x10000000 | (0x7ffc0 << 5))
        self.assertEqual(address_candidates(data, 0x100),
                         [{"adr": "0x0"}, {"adr": "0x200"}])


if __name__ == "__main__":
    unittest.main()
