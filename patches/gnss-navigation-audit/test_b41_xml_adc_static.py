#!/usr/bin/env python3
"""Exact asset/consumer checks without Unicorn, native builds or execution."""
import hashlib
import io
from pathlib import Path
import re
import struct
import sys
import unittest
import xml.etree.ElementTree as ET
from elftools.elf.elffile import ELFFile

NAMES = ("IFB", "GGTO", "DCB", "L1Only", "L5Test", "DisableSignal", "GLP", "CAIC",
         "GnssMode", "Bluesky", "CoTMS", "SwitchTIA", "Blanking", "MDTime", "Time_Source",
         "PSO", "GNSSPower", "OSNMA", "SignalConfig")
LIB = XML = MNLD = None


def pinned(path, expected):
    size = path.stat().st_size
    if not 0 < size <= 16 * 1024 * 1024:
        raise ValueError("bounded pinned asset required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("independent asset pin mismatch")
    return data


def word_at(data, address):
    elf = ELFFile(io.BytesIO(data))
    for segment in elf.iter_segments():
        if segment["p_type"] == "PT_LOAD" and segment["p_vaddr"] <= address and \
                address + 4 <= segment["p_vaddr"] + segment["p_filesz"]:
            offset = segment["p_offset"] + address - segment["p_vaddr"]
            return struct.unpack_from("<I", data, offset)[0]
    raise ValueError("instruction not file-backed")


def branch_target(data, address):
    word = word_at(data, address)
    if word & 0xfc000000 != 0x94000000:
        raise ValueError("expected direct AArch64 BL")
    displacement = word & 0x3ffffff
    if displacement & 0x2000000:
        displacement -= 0x4000000
    return address + displacement * 4


class StaticTests(unittest.TestCase):
    def test_exact_stock_features_and_disabled_profiles(self):
        root = ET.fromstring(XML)
        features = root.findall("feature")
        self.assertEqual(tuple(feature.text.strip() for feature in features), NAMES)
        self.assertEqual([feature.text.strip() for feature in features if feature.findtext("config") == "0"],
                         ["L5Test", "CAIC", "Blanking", "PSO"])
        source = Path(__file__).with_name("b41_xml_globals.c").read_text()
        batch = source[source.index("int b41_xml_global_owner_apply_stock"):]
        table = batch[batch.index("names["):batch.index("};")]
        self.assertEqual(tuple(re.findall(r'"([^\"]+)"', table)), NAMES)

    def test_actual_set_tail_is_not_a_global_only_success(self):
        self.assertEqual(branch_target(LIB, 0x4fe430), 0x50c130)  # Actual checksum.
        self.assertEqual(word_at(LIB, 0x4fe460), 0x528000a2)  # mov w2,#5 category.
        self.assertEqual(branch_target(LIB, 0x4fe46c), 0x50c1d8)  # Actual output dispatch.
        self.assertEqual(branch_target(LIB, 0x4fe470), 0x5214b0)  # Optional log policy.

    def test_stock_snapshot_and_no_property_or_chip_defaults(self):
        source = Path(__file__).with_name("b41_xml_globals.c").read_text()
        batch = source[source.index("int b41_xml_global_owner_apply_stock"):]
        self.assertIn("inputs.chip_id = (uint32_t)le((const uint8_t *)target, 4)", batch)
        self.assertNotIn("inputs.chip_id = 6637", batch)
        self.assertNotIn("property_get", source)
        self.assertLess(batch.index("b41_xml_global_plan"), batch.index("o->global[i] = pending[i]"))
        self.assertIn("memcmp(before, o->global", batch)
        self.assertNotIn("xml_policy_missing = 0", source)

    def test_adc_wire_contract_and_real_retained_owner(self):
        source = Path(__file__).with_name("b41_slot0_adc.c").read_text()
        self.assertIn("word(packet, 260)", source)
        self.assertIn("word(packet + 4, 2)", source)
        self.assertIn("F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL", source)
        self.assertIn("fpathconf(fd, _PC_PIPE_BUF)", source)
        self.assertIn("pread(o->capture_fd", source)
        self.assertIn("if (o->state == B41_ADC_FAILED) return o->first_error", source)
        self.assertNotIn("ioctl(", source)
        self.assertNotIn("open(", source)
        self.assertNotIn("close(", source)
        # Producer string locations from the independently pinned mnld profile.
        elf = ELFFile(io.BytesIO(MNLD))
        for address, expected in ((0x14653, b"$PMTKJAM3,%d,%d"), (0x22082, b",%08X"),
                                  (0xdb2f, b"*%02X\r\n")):
            segment = next(s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD" and
                s["p_vaddr"] <= address < s["p_vaddr"] + s["p_filesz"])
            offset = segment["p_offset"] + address - segment["p_vaddr"]
            self.assertEqual(MNLD[offset:offset + len(expected) + 1], expected + b"\0")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: test_b41_xml_adc_static.py libmnl.so MNL_Config.xml mnld")
    LIB = pinned(Path(sys.argv[1]), "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90")
    XML = pinned(Path(sys.argv[2]), "7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31")
    MNLD = pinned(Path(sys.argv[3]), "285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83")
    unittest.main(argv=[sys.argv[0]])
