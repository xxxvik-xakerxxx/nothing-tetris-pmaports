#!/usr/bin/env python3
"""SHA-pinned static bootstrap-field producers; no native execution."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

import capstone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA


class BootstrapFieldEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check(self, expected, image=None):
        image = self.lib if image is None else image
        for address, instruction in expected.items():
            self.assertEqual(image.instructions(address, 4)[address], instruction, hex(address))

    def test_pins_cover_all_producers_and_out_of_line_branches(self):
        self.assertEqual(capstone.__version__, "5.0.6")
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(self.mnld.data, LIB_SHA)
        for image, start, end, digest in (
            (self.mnld, 0x62b54, 0x62d0c, "4a449f5b4fc73d5ab5fc8d273f5e8a9ca67ffc896d9bcbe428b456f43f136d01"),
            (self.mnld, 0x62280, 0x62544, "cc522e7301b32898ce6f9d45c47ed1326c111e8fa02704ec0b3c0b59ab39e324"),
            (self.lib, 0x4f0e8c, 0x4f0f90, "5f9918ebd678dc7d5452fedc2e186b2fd7bbd74a8055aae16038b6185a97c0f1"),
            (self.lib, 0x4f2094, 0x4f213c, "d7af45fd69fca0890998218554da544126ff1794c21358310e3d0bc00e88c3e3"),
            (self.lib, 0x4f2824, 0x4f28c4, "00191e238eb53e35a48f3ad987f8db021a5255fadf4a8a90093385965e44f7e8"),
            (self.lib, 0x4f29b8, 0x4f2ad8, "1e874290572767cd51470b884458f82273d6a03225ce6f145fac0e0bf04653da"),
            (self.lib, 0x4f3000, 0x4f3014, "64560afd9914fe71be4a44266361f1418b9903a8681602e74a04ce435549017f"),
            (self.lib, 0x5523c0, 0x5524b0, "125d165d15f23622b7751840d6ffc1d6720a0b223a6e437fa93b49c4dff1014e"),
            (self.lib, 0x662820, 0x6628c0, "76bef5abc74233e746d0172e5bcf4124be8532d9097d30c1dd1673326e887a27"),
            (self.lib, 0x6628c0, 0x662960, "075f67a0ee9254b2c9e59f87e7158d3a76f9a9810eddfaf22eb1ae64736ae5b0"),
            (self.lib, 0x5211a4, 0x5211e4, "86c7b3986edfab389bad2dc15bd02763d7b04d7590bedd2178b794a25e33d70e"),
            (self.lib, 0x5cc564, 0x5cc9a0, "50dcb5ceb0635fe80a435f2fa314778a961323708e60647dfd4b143f3ec196ce"),
            (self.lib, 0x4ce055, 0x4ce10c, "f6734b53d0559bd76c9b0bb92f490f4b92c3d7ca98ac2c7d284e638867ce327c"),
        ):
            self.assertEqual(hashlib.sha256(image.read(start, end - start)).hexdigest(), digest)

    def test_real_input_locations_not_adie_or_pmic_aliases(self):
        for got, target in ((0x6e6668, 0x717cb3), (0x6e6670, 0x717cb6),
                            (0x6e6650, 0x717cb7), (0x6e6658, 0x717cb8),
                            (0x6e6688, 0x7178b0), (0x6e85c0, 0x8ca018),
                            (0x6e69d0, 0x75c99c)):
            self.assertEqual(struct.unpack("<Q", self.lib.read(got, 8))[0], target)
        self.check({
            0x62be0: ("ldr", "w8, [x8, #0x22c]"),
            0x62c30: ("ldr", "w14, [x13]"),
            0x62c44: ("ldrb", "w15, [x13, #9]"),
            0x62c48: ("stur", "w14, [x8, #5]"),
            0x62c54: ("strb", "w15, [x8, #0x11]"),
            0x63368: ("ldp", "w19, w8, [x8]"),
            0x6336c: ("str", "w19, [x9, #8]"),
        }, self.mnld)

    def test_private_records_validate_decoded_sum_return_raw_word(self):
        # Both getters have the identical decoder, at different record offsets.
        for origin, offset in ((0x662820, 0x166c), (0x6628c0, 0x1674)):
            expected = {
                0x00: ("mov", f"w9, #0x{offset:x}"),
                0x10: ("mov", f"w10, #0x{offset - 4:x}"),
                0x1c: ("eor", "w9, w9, w11"),
                0x2c: ("madd", "w12, w9, w11, w12"),
                0x38: ("eor", "w13, w13, w14"),
                0x40: ("and", "w12, w12, #0xffff"),
                0x54: ("eor", "w15, w15, w16"),
                0x6c: ("ldr", f"w12, [x8, #0x{offset - 4:x}]"),
                0x78: ("add", "w9, w9, w10"),
                0x7c: ("cmp", "w9, w12"),
                0x84: ("ldr", f"w9, [x8, #0x{offset:x}]"),
                0x8c: ("str", "w9, [x0]"),
                0x98: ("mov", "w0, wzr"),
            }
            self.check({origin + relative: instruction for relative, instruction in expected.items()})

    def test_frequency_priority_sentinel_and_exact_adjustment(self):
        self.check({
            0x4f0654: ("b.ne", "#0x4f0688"),
            0x4f0680: ("cmn", "w25, #1"),
            0x4f0684: ("csel", "w22, w22, w25, eq"),
            0x5523e4: ("bl", "#0x6628c0"),
            0x5523ec: ("b.eq", "#0x552414"),
            0x5523f0: ("ldr", "w0, [sp, #4]"),
            0x55242c: ("csel", "w8, w9, w8, eq"),
            0x552440: ("bl", "#0x662820"),
            0x552448: ("b.eq", "#0x5523f0"),
            0x552450: ("mov", "w9, #0xaaab"),
            0x55245c: ("lsr", "x9, x9, #0x21"),
            0x552460: ("add", "w9, w9, w9, lsl #1"),
            0x552464: ("sub", "w8, w8, w9"),
            0x552480: ("movk", "x8, #0x408c, lsl #48"),
            0x552490: ("movk", "x8, #0xc08c, lsl #48"),
            0x552494: ("ucvtf", "d0, d0"),
            0x55249c: ("fadd", "d0, d0, d1"),
            0x5524a0: ("fcvtzu", "w8, d0"),
        })
        self.assertEqual(float.fromhex("0x1.c6fffffffffffp+9"),
                         struct.unpack("<d", struct.pack("<Q", 0x408c6fffffffffff))[0])

    def test_clock_mode_is_branch_constructed_not_raw_clock_flag(self):
        self.check({
            0x4f20d8: ("cmp", "w10, #2"),
            0x4f20dc: ("b.hi", "#0x4f20e4"),
            0x4f20f0: ("cmp", "w9, #2"),
            0x4f20f4: ("b.lo", "#0x4f210c"),
            0x4f20fc: ("cmp", "w9, #1"),
            0x4f2104: ("orr", "w28, w8, #4"),
            0x4f2110: ("cmp", "w9, #1"),
            0x4f2114: ("csel", "w28, w10, w8, eq"),
            0x4f211c: ("and", "w28, w8, #0xfffffffb"),
            0x4f2134: ("mov", "w1, wzr"),
        })

    def test_profile_override_mask_signed_chip_ids_and_lna_bytes(self):
        self.check({
            0x4f2828: ("cmp", "w9, #5"),
            0x4f283c: ("mov", "w9, #0x27"),
            0x4f2844: ("strb", "w9, [x8]"),
            0x4f2854: ("and", "w8, w8, #0xf"),
            0x4f2870: ("b.eq", "#0x4f287c"),
            0x4f2880: ("mov", "w9, #0x9a90"),
            0x4f2888: ("cmp", "w9, #0x22"),
            0x4f289c: ("movk", "x10, #5, lsl #16"),
            0x4f28a0: ("movk", "x10, #4, lsl #32"),
            0x4f3004: ("movk", "w9, #0xfffe, lsl #16"),
            0x4f29e0: ("mov", "w11, #-0x988f"),
            0x4f29f8: ("ldr", "w10, [x26, #0x54]"),
            0x4f2a14: ("mov", "w12, #-0x99ce"),
            0x4f2a34: ("mov", "w8, #0xa"),
            0x4f2a3c: ("csel", "w11, w11, w8, eq"),
            0x4f2a58: ("mov", "w10, #-0x98db"),
            0x4f2a64: ("mov", "w10, #-0x989f"),
        })
        mask_ids = {(index - 0x9a90) & 0xffffffff for index in range(35)
                    if (0x400050007 >> index) & 1}
        self.assertEqual(mask_ids, {0xffff6570, 0xffff6571, 0xffff6572,
                                   0xffff6580, 0xffff6582, 0xffff6592})

    def test_feature_predicate_and_b2_use_actual_producers(self):
        self.check({
            0x52b9e0: ("ldp", "w9, w10, [x19, #0x10]"),
            0x52b9f4: ("str", "w10, [x11, #0xeec]"),
            0x5211b4: ("add", "x0, x8, #0x1ae"),
            0x5211b8: ("mov", "w1, #0x296"),
            0x5211bc: ("bl", "#0x6e4a80"),
            0x5211c8: ("cmp", "x0, #4"),
            0x5211d0: ("cmn", "w8, #1"),
            0x5211d8: ("and", "w0, w9, w8"),
            0x4f2a94: ("csinc", "w24, w8, wzr, ne"),
            0x4f2a98: ("tbz", "w9, #6, #0x4f2ab0"),
            0x4f2a9c: ("mov", "w0, #0xb2"),
            0x4f2aac: ("csel", "w24, w24, w8, eq"),
            0x5cc57c: ("adrp", "x9, #0x4ce000"),
            0x5cc580: ("add", "x9, x9, #0x55"),
            0x5cc584: ("adr", "x10, #0x5cc594"),
            0x5cc8ec: ("mov", "w9, #-0x9877"),
            0x5cc8f4: ("cset", "w0, eq"),
        })
        entry = self.lib.read(0x4ce055 + 0xb2 - 1, 1)[0]
        self.assertEqual(0x5cc594 + 4 * entry, 0x5cc8e0)
        self.check({0x6e4a84: ("ldr", "x17, [x16, #0xc38]")})
        self.assertEqual(self.lib.imported_symbol(0x6e8c38), (1026, b"__strlen_chk"))

    def test_selector_initialization_and_later_policy_are_distinct(self):
        self.check({
            0x52ea3c: ("ldr", "w9, [x24, #0x30]"),
            0x52ea64: ("cmp", "x8, #0x190"),
            0x52ea6c: ("mov", "w8, #1"),
            0x52ea74: ("ldr", "w8, [x10, x8]"),
            0x52ea80: ("strb", "w8, [x26]"),
            0x52ea94: ("ldr", "w8, [x24, #0x38]"),
            0x52eab8: ("bl", "#0x6e4b80"),
            0x52ead4: ("lsr", "w9, w9, #1"),
            0x52ead8: ("and", "w9, w9, #2"),
            0x52eadc: ("strb", "w9, [x10]"),
            0x4fcbcc: ("strb", "w8, [x24]"),
            0x4fcbe8: ("strb", "w9, [x25]"),
            0x4fcc04: ("strb", "w9, [x26]"),
        })

    def test_baud_destination_is_high_byte_and_unknown_is_stock_zero(self):
        self.check({
            0x4f0f10: ("mov", "w8, #1"),
            0x4f0f30: ("mov", "w8, #8"),
            0x4f0f50: ("strb", "wzr, [sp, #0xcc]"),
            0x4f0f54: ("strb", "wzr, [sp, #0xc8]"),
            0x4f0f5c: ("mov", "w8, #7"),
            0x4f0f64: ("mov", "w8, #3"),
            0x4f0f6c: ("mov", "w8, #9"),
            0x4f0f74: ("mov", "w8, #4"),
            0x4f0f7c: ("mov", "w8, #6"),
            0x4f0f84: ("mov", "w8, #2"),
            0x4f0f88: ("strb", "wzr, [sp, #0xcc]"),
            0x4f0f8c: ("strb", "w8, [sp, #0xc8]"),
            0x4f2688: ("ldrb", "w8, [sp, #0xcc]"),
            0x4f2690: ("ldrb", "w8, [sp, #0xc8]"),
        })


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_bootstrap_fields_source.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
