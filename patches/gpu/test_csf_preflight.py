#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Synthetic CSF framing/fault tests; no private firmware or hardware needed."""
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import csf_preflight as csf


def fixture(extra=b"", flags=0x40000003, va_end=csf.SHARED_VA + 4096):
    section = struct.pack("<6I", 24 << 8, flags, csf.SHARED_VA, va_end, 0, 0)
    end = 20 + len(section) + len(extra)
    return struct.pack("<IBBHIII", 0xc3f13a6e, 3, 0, 0, 0, 0, end) + section + extra


class CSF(unittest.TestCase):
    def test_supported_header_shared_region_and_no_activation(self):
        report = csf.parse(fixture())
        self.assertEqual(report["binary_header_version"], "0.3")
        self.assertEqual(report["shared_region"]["va_start"], csf.SHARED_VA)
        self.assertFalse(report["hardware_activation_permitted"])
        self.assertFalse(report["panthor_probe_is_read_only"])

    def test_optional_and_known_ignored_entries(self):
        for kind in (1, 2, 3, 4):
            report = csf.parse(fixture(struct.pack("<I", (4 << 8) | kind)))
            self.assertEqual(len(report["ignored_entries"]), 1)
        report = csf.parse(fixture(struct.pack("<I", 0x80000409)))
        self.assertEqual(report["ignored_entries"][0]["reason"], "unknown optional entry")
        with self.assertRaises(ValueError):
            csf.parse(fixture(struct.pack("<I", 0x00000409)))

    def test_invalid_entry_sizes_never_loop_or_overread(self):
        for size in (0, 1, 3, 5, 8, 252):
            with self.subTest(size=size), self.assertRaises(ValueError):
                csf.parse(fixture(struct.pack("<I", size << 8)))

    def test_header_mutations_and_truncations(self):
        image = fixture()
        for end in (0, 19, 20, len(image) - 1):
            with self.subTest(end=end), self.assertRaises(ValueError):
                csf.parse(image[:end])
        for offset in (0, 5, 6, 12, 16):
            changed = bytearray(image)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                csf.parse(changed)

    def test_unsafe_mapping_flags_and_page_size_rejected(self):
        for flags in (3, 0x40000043, 0x40000023):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                csf.parse(fixture(flags=flags))
        for size in (16384, 65536):
            with self.subTest(size=size), self.assertRaises(ValueError):
                csf.parse(fixture(), size)
        with self.assertRaises(ValueError):
            csf.parse(fixture(va_end=csf.SHARED_VA))

    def test_data_bounds_capacity_and_duplicate_va(self):
        for start, end in ((5, 4), (0, 100), (0, 45)):
            changed = bytearray(fixture())
            struct.pack_into("<II", changed, 36, start, end)
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                csf.parse(changed)
        with self.assertRaises(ValueError):
            csf.parse(fixture(fixture()[20:]))
        changed = bytearray(fixture() + bytes(5000))
        struct.pack_into("<II", changed, 36, 0, 5000)
        with self.assertRaises(ValueError):
            csf.parse(changed)

    def test_malformed_build_metadata(self):
        for start, count in ((0, 0), (0xffffffff, 32), (0, 0xffffffff)):
            entry = struct.pack("<3I", 0x80000c06, start, count)
            with self.subTest(start=start, count=count), self.assertRaises(ValueError):
                csf.parse(fixture(entry))

    def test_firmware_lookup_from_gpu_id_not_binary_version(self):
        self.assertEqual(csf.firmware_path(0xb0030000), "arm/mali/arch11.0/mali_csffw.bin")
        self.assertEqual(csf.firmware_path(0xa1070000), "arm/mali/arch10.1/mali_csffw.bin")
        for gpu_id in (-1, 1 << 32):
            with self.assertRaises(ValueError):
                csf.firmware_path(gpu_id)

    def test_changed_source_never_blessed(self):
        with patch.object(Path, "read_bytes", return_value=b"changed source"):
            with self.assertRaises(ValueError):
                csf.source_contract(Path("untrusted-kernel"))


if __name__ == "__main__":
    unittest.main()
