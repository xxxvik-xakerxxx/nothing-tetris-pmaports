#!/usr/bin/env python3
"""Pinned static instructions and native-profile call chain. No C execution."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA


class ProfileSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = PinnedImage(MNLD.read_bytes(), MNLD_SHA)

    def test_nv_read_and_selection_are_real_not_absence_defaults(self):
        i = self.image
        self.assertEqual(i.read(0x1090d, 19), b"libcustom_nvram.so\0")
        self.assertEqual(i.read(0xa0d1, 28), b"iAP_CFG_CUSTOM_FILE_GPS_LID\0"[:28])
        self.assertEqual(i.imported_symbol(0x86fb0), (1026, b"NVM_GetFileDesc"))
        self.assertEqual(i.imported_symbol(0x86fb8), (1026, b"NVM_CloseFileDesc"))
        code = i.instructions(0x7b0d4, 0xb8)
        for address, instruction in {
            0x7b0dc: ("adr", "x8, #0x9bc24"),
            0x7b0fc: ("bl", "#0x85d00"),
            0x7b120: ("mov", "w3, #0x34"),
            0x7b124: ("smull", "x2, w8, w9"),
            0x7b12c: ("bl", "#0x85510"),
            0x7b168: ("strb", "wzr, [x21, #0x13]"),
            0x7b170: ("cbz", "x0, #0x7b1a0"),
            0x7b17c: ("mov", "w9, #1"),
            0x7b184: ("str", "w9, [x8]"),
        }.items():
            self.assertEqual(code[address], instruction)

    def test_profile_fields_and_interval_fallback(self):
        code = self.image.instructions(0x62bd8, 0x110)
        for address, instruction in {
            0x62bd8: ("str", "w8, [x20, #0x1c]"),
            0x62c14: ("add", "x13, x13, #0xc3c"),
            0x62c30: ("ldr", "w14, [x13]"),
            0x62c3c: ("ldrh", "w9, [x13, #4]"),
            0x62c44: ("ldrb", "w15, [x13, #9]"),
            0x62c48: ("stur", "w14, [x8, #5]"),
            0x62c4c: ("ldrb", "w13, [x13, #8]"),
            0x62c50: ("sturh", "w9, [x8, #1]"),
            0x62c54: ("strb", "w15, [x8, #0x11]"),
            0x62c58: ("strb", "w13, [x8]"),
            0x62cb0: ("cbnz", "w9, #0x62ce4"),
            0x62cb4: ("mov", "w8, #0x7d0"),
        }.items():
            self.assertEqual(code[address], instruction)
        self.assertEqual(0x9bc3c - 0x9bc24, 24)

    def test_actual_legacy_chip_strings_and_calibration_copy(self):
        code = self.image.instructions(0x62c18, 0x98)
        for address, instruction in {
            0x62c18: ("mov", "w12, #0x7830"),
            0x62c1c: ("mov", "w11, #0x3735"),
            0x62c24: ("movk", "w12, #0x3536, lsl #16"),
            0x62c2c: ("movk", "w11, #0x30, lsl #16"),
            0x62c38: ("add", "w15, w11, #0x100"),
            0x62c98: ("add", "x8, x8, #0xc48"),
            0x62c9c: ("ldr", "q0, [x8]"),
            0x62cac: ("stur", "q0, [x8, #0x28]"),
        }.items():
            self.assertEqual(code[address], instruction)
        self.assertEqual((0x35367830).to_bytes(4, "little"), b"0x65")
        self.assertEqual((0x00303735).to_bytes(4, "little"), b"570\0")
        self.assertEqual((0x00303735 + 0x100).to_bytes(4, "little"), b"580\0")
        self.assertEqual(0x9bc48 - 0x9bc24, 36)

    def test_composer_retains_real_queries_and_missing_engine_gates(self):
        source = (HERE / "platform_profile.c").read_text()
        self.assertIn("ret = b41_first_config_build(&base, &result)", source)
        self.assertIn("result.provenance[0x18] != B41_FIRST_CLOCK_RESULT", source)
        self.assertIn("result.provenance[0x13] != B41_FIRST_CLOCK_RESULT", source)
        self.assertIn("if (record_size != B41_PLATFORM_PROFILE_SIZE)", source)
        self.assertNotIn("xml_policy_missing = 0", source)
        self.assertNotIn("memset(&result", source)
        for forbidden in ("ioctl(", "write(", "mnl_run", "GPSDL_DEVICE", "cipher_key"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_platform_profile_source.py PINNED_MNLD")
    MNLD = Path(sys.argv.pop())
    unittest.main()
