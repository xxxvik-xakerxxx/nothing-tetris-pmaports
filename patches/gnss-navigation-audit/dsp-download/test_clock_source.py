#!/usr/bin/env python3
"""Immutable clock math/profile proof, never DSO or instruction execution."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA
from test_source import source


class ClockEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check(self, image, expected):
        for address, instruction in expected.items():
            self.assertEqual(image.instructions(address, 4)[address], instruction, hex(address))

    def test_complete_math_and_rounding_routines_are_pinned(self):
        for image, start, end, digest in (
            (self.lib, 0x4f05f4, 0x4f0a18, "19d5202a6ce2748d186f64279c20aaa7bf6cbe689e0d44139e94e2fec6ee812e"),
            (self.lib, 0x574f04, 0x574f28, "6b24525ddbd6d6f59f2b5806f4b59adb390c72230f0bd121f6b2e4621f39519f"),
            (self.mnld, 0x62b54, 0x62d0c, "4a449f5b4fc73d5ab5fc8d273f5e8a9ca67ffc896d9bcbe428b456f43f136d01"),
            (self.mnld, 0x62280, 0x62544, "cc522e7301b32898ce6f9d45c47ed1326c111e8fa02704ec0b3c0b59ab39e324"),
            (self.lib, 0x5523c0, 0x5524b0, "125d165d15f23622b7751840d6ffc1d6720a0b223a6e437fa93b49c4dff1014e"),
            (self.lib, 0x6628c0, 0x662960, "075f67a0ee9254b2c9e59f87e7158d3a76f9a9810eddfaf22eb1ae64736ae5b0"),
        ):
            self.assertEqual(hashlib.sha256(image.read(start, end - start)).hexdigest(), digest)

    def test_conversion_is_midpoint_with_positive_half_tie(self):
        self.check(self.lib, {
            0x574f04: ("fcvtms", "x8, d0"),
            0x574f08: ("fcvtps", "x9, d0"),
            0x574f0c: ("add", "x10, x9, x8"),
            0x574f10: ("scvtf", "d1, x10"),
            0x574f14: ("fmov", "d2, #0.50000000"),
            0x574f18: ("fmul", "d1, d1, d2"),
            0x574f1c: ("fcmp", "d1, d0"),
            0x574f20: ("csel", "x0, x8, x9, hi"),
            0x574f24: ("ret", ""),
        })

    def test_exact_literal_tables_and_binary64_timers(self):
        self.assertEqual(struct.unpack("<5H", self.lib.read(0x27c0e, 10)), (138, 220, 307, 97, 151))
        self.assertEqual(struct.unpack("<5H", self.lib.read(0x27c18, 10)), (121, 193, 265, 84, 131))
        self.assertEqual(struct.unpack("<Q", self.lib.read(0xa090, 8))[0], 0x41905e353f7ced91)
        self.assertEqual(struct.unpack("<Q", self.lib.read(0xa7e0, 8))[0], 0x41888d4fdf3b645a)
        self.assertEqual(struct.unpack("<d", self.lib.read(0xa7d8, 8))[0], 100000000000.0)

    def test_float_table_selection_and_integer_coefficient_are_distinct(self):
        self.check(self.lib, {
            0x4f06e0: ("cmp", "w22, w8"),
            0x4f0720: ("ucvtf", "s9, w22"),
            0x4f0728: ("fcmp", "s9, s0"),
            0x4f0744: ("fcmp", "s9, s0"),
            0x4f07b0: ("cmp", "w22, w8"),
            0x4f07f0: ("fcmp", "s9, s0"),
            0x4f0758: ("cmp", "w22, w8"),
            0x4f0778: ("add", "w9, w22, w9"),
            0x4f077c: ("cmp", "w9, w8"),
            0x4f0780: ("b.hs", "#0x4f078c"),
            0x4f0814: ("csel", "w27, wzr, w8, hi"),
            0x4f0834: ("lsr", "x10, x8, #0x2f"),
            0x4f0838: ("lsr", "x8, x9, #0x2c"),
        })

    def test_divider_fraction_and_output_order(self):
        self.check(self.lib, {
            0x4f0888: ("udiv", "w24, w8, w22"),
            0x4f088c: ("msub", "w8, w24, w22, w8"),
            0x4f089c: ("fmul", "d0, d0, d1"),
            0x4f08a0: ("fdiv", "d0, d0, d10"),
            0x4f0930: ("lsl", "w26, w24, #8"),
            0x4f0934: ("bfxil", "w26, w23, #0x10, #8"),
            0x4f0980: ("strh", "w27, [x19]"),
            0x4f0984: ("strh", "w26, [x19, #2]"),
            0x4f0990: ("strh", "w23, [x19, #4]"),
            0x4f0994: ("strh", "wzr, [x19, #6]"),
            0x4f0998: ("strh", "w8, [x19, #8]"),
            0x4f09a0: ("strh", "w28, [x19, #0xa]"),
            0x4f09a4: ("strh", "w21, [x19, #0xc]"),
            0x4f09ac: ("strh", "w8, [x19, #0xe]"),
            0x4f09b0: ("strh", "w24, [x19, #0x10]"),
            0x4f09b8: ("strh", "w9, [x19, #0x12]"),
            0x4f09bc: ("strh", "w25, [x19, #0x14]"),
            0x4f09c0: ("strh", "w8, [x19, #0x16]"),
            0x4f09c4: ("strh", "w22, [x19, #0x18]"),
            0x4f09c8: ("strh", "w0, [x19, #0x1a]"),
        })

    def test_ioctl11_constructor_not_ioctl30_frequency_literal(self):
        self.check(self.mnld, {
            0x62bec: ("cmp", "w8, #1"),
            0x62c04: ("b.ne", "#0x62cc4"),
            0x62c48: ("stur", "w14, [x8, #5]"),
            0x62c54: ("strb", "w15, [x8, #0x11]"),
            0x62cd4: ("strb", "wzr, [x8, #0x11]"),
            0x62cdc: ("stur", "w9, [x8, #5]"),
            0x62290: ("mov", "w1, #0xb"),
            0x62294: ("mov", "x2, xzr"),
            0x62298: ("bl", "#0x85880"),
            0x622a0: ("cmp", "w4, #0x51"),
            0x624f4: ("str", "w8, [x19, #0x18]"),
            0x62534: ("strb", "w20, [x19, #0x13]"),
            0x632e8: ("mov", "w1, #0x1e"),
            0x632ec: ("mov", "x2, xzr"),
            0x632f0: ("bl", "#0x85880"),
            0x63328: ("str", "w19, [sp, #0x90]"),
            0x6335c: ("add", "x8, x8, #0x304"),
            0x63368: ("ldp", "w19, w8, [x8]"),
            0x6336c: ("str", "w19, [x9, #8]"),
        })
        self.check(self.lib, {0x52e720: ("stp", "q1, q0, [x24, #0x10]"),
                              0x52e73c: ("stp", "q3, q2, [x24, #0x30]")})
        table = self.mnld.read(0x22fe8, 82)
        self.assertEqual(0x622c4 + table[0x51] * 4, 0x624bc)

    def test_v051_kernel_selectors_have_real_providers(self):
        config = source("plat/v051/inc/gps_dl_config.h")
        self.assertIn("#define GPS_DL_GET_PLATFORM_CLOCK_FREQ (1)", config)
        driver = source("linux/gps_each_device.c")
        self.assertIn("retval = gps_dl_link_get_clock_flag();", driver)
        self.assertIn("retval = gps_dl_clock_mng_get_platform_clock();", driver)
        clock = source("linux/gps_dl_linux_clock_mng.c")
        self.assertIn("dev_get_regmap(pdev->dev.parent, NULL)", clock)
        self.assertIn('"mediatek,mt6685-gps"', clock)
        self.assertIn("#define DCXO_DIGCLK_ELR 0x7f4", clock)
        self.assertIn("regmap_read(map, DCXO_DIGCLK_ELR, &value);", clock)
        self.assertIn("retval = 1; /*52M*/", clock)
        self.assertIn("retval = 0; /*26M*/", clock)
        self.assertIn("return -1;", clock)
        flags = source("hal/inc/gps_dl_hal.h")
        self.assertIn("GPSDL_CLOCK_FLAG_COTMS     (0x21)", flags)
        self.assertIn("GPSDL_CLOCK_FLAG_52M_COTMS (0x51)", flags)

    def test_effective_frequency_can_be_overridden_not_derived_from_adie(self):
        self.check(self.lib, {
            0x4f0648: ("ldrb", "w8, [x9, #0x13]"),
            0x4f0650: ("cmp", "w8, #0xfe"),
            0x4f0658: ("bl", "#0x5523c0"),
            0x4f0680: ("cmn", "w25, #1"),
            0x4f0684: ("csel", "w22, w22, w25, eq"),
            0x5523e4: ("bl", "#0x6628c0"),
            0x5523ec: ("b.eq", "#0x552414"),
            0x55241c: ("ldr", "w8, [x8, #0x18]"),
            0x55242c: ("csel", "w8, w9, w8, eq"),
            0x552440: ("bl", "#0x662820"),
            0x66293c: ("cmp", "w9, w12"),
            0x662940: ("b.ne", "#0x662958"),
            0x66294c: ("str", "w9, [x0]"),
            0x4f20f8: ("ldrb", "w9, [x26, #0x24]"),
            0x4f2130: ("mov", "w0, w28"),
            0x4f2134: ("mov", "w1, wzr"),
        })


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_clock_source.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
