#!/usr/bin/env python3
"""Pinned static navigation producers/consumers. No instruction execution."""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "gnss-navigation-audit"))
from test_b41_receiver_policy_source import PinnedImage, LIB_SHA, MNLD_SHA

RANGES = (
    (0x509830, 0x1498, "9c6760cd19c9923aef5b102aa886e65acf0361264e1ee633d6c939c7cef0633a"),
    (0x504a08, 0x80, "ab62e145ebe4d61275e9d364d5d4eecc9c7365f4dab2ffac669afa56b1bc4269"),
    (0x5040b0, 0x148, "905eef66335b8305c2ad1af67b4eeef4baf64b8e400a77506eca5e6e9600cfbc"),
    (0x5051d4, 0x280, "467ea454e1df0bc57d2569dec467cb068da085dab5a933e06b6a6b366dddbd5d"),
    (0x505828, 0x260, "dacd7009c1bfa6de4bb374aeab491226eb0db9f777e99dfedf43e5255b17f27a"),
    (0x50e2bc, 0xe1c, "60957d7177b120e085f4471c5464830eea9959c3e221f745765715ec804b14a2"),
    (0x510aa4, 0x170, "22ce9f28a867b788e7b9516a5332ead8ba784bc7664a9808cd04ffeb6f3eb0e6"),
    (0x5132a4, 0x308, "ca86170825f8d81cd83cd1db1d132666be2a979b2ef14ad02862548c1b0804fe"),
    (0x55391c, 0x38, "2be0a9223bcfe8c118d1bd2ee06b6d3c8332437b844c1726015c9e1ddba64a15"),
    (0x68b094, 0x24, "32b49bdb066335ce6969568d8db27e191bf3818b389e03198cb3dd6efe60e4d1"),
    (0x5351c0, 0xb0, "d75eee5c11fd3988ad4ac78b2704b489bf58b088ce70bad1c8716780b6c87093"),
    (0x4c3e36, 0xd2, "3177ed2bdb648a8f8393c6bd7c13801be687a7f7db5cdd158b06f8c924a61c22"),
    (0x4c3f08, 0xfc, "f88482bb12a075255d792a2305ed2a6a4675d41762e5f3324a1c6c104dd4050d"),
    (0x4c4024, 0xfc, "350330886b3153f85d00fb8c91bca139f84a6ffda6237a1d8e0ca8ebbc1c9d1b"),
    (0x4c5244, 0x2a, "f6d1173cf9b367f646e3f17bdf899b06e9c5a7ea541a7c9138e3fbe961e8a5f9"),
    (0x52f334, 0x60, "b4544525b2e439a380935f75629314a262b1d7603b393a4320b0ea73d414adb9"),
    (0x5c6644, 0x78, "4accfa99597d4af5a736ba41e4888c2388a86ea2c1aaf94851413a7e59e4f27b"),
    (0x554f80, 0x29c, "bb4bbfda619e7eaddd8644c30c39fbcd951d7c327483fd4c5c8f1f547e9851d3"),
    (0x554d3c, 0x68, "68fd1a47165bbeef6b2431b743d140de32d028486a247c94d1a997f31d381929"),
)


class NavigationSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = PinnedImage(LIB_PATH.read_bytes(), LIB_SHA)
        cls.mnld = PinnedImage(MNLD_PATH.read_bytes(), MNLD_SHA)

    def test_exact_files_and_new_instruction_ranges(self):
        for address, size, expected in RANGES:
            self.assertEqual(hashlib.sha256(self.lib.read(address, size)).hexdigest(), expected)
        self.assertEqual(hashlib.sha256(self.mnld.read(0x63c30, 0x20)).hexdigest(),
                         "53998c5d66842a3b7a478932d324fcb96fb0c43b3cf2f0897e9de0b7c98d5675")
        with self.assertRaises(ValueError):
            PinnedImage(self.lib.data, MNLD_SHA)

    def test_primary_packet_grammar_is_not_nmea_or_secondary_decoder(self):
        code = self.lib.instructions(0x554d3c, 0x68)
        for address, expected in {
            0x554d44: ("mov", "w8, #0xfe00"), 0x554d58: ("ldrh", "w8, [x2, #2]"),
            0x554d60: ("and", "w10, w8, #0xfff"), 0x554d64: ("sub", "w1, w10, #4"),
            0x554d6c: ("lsr", "w2, w8, #0xc"), 0x554d78: ("bl", "#0x50acc8"),
            0x554d8c: ("bl", "#0x509830"),
        }.items():
            self.assertEqual(code[address], expected)
        escape = self.lib.instructions(0x554fd4, 0x58)
        self.assertEqual(escape[0x554fd8], ("cmp", "w9, #0xde"))
        self.assertEqual(escape[0x554ff4], ("sub", "w10, w9, #0xdf"))
        self.assertEqual(escape[0x555014], ("cmp", "w9, #0xe0"))
        self.assertEqual(escape[0x555028], ("mov", "w11, #0xde"))

    def test_epoch_dispatch_bounds_and_shared_index(self):
        def entry(table, base, command, first):
            return base + 4*struct.unpack("<H", self.lib.read(table + 2*(command-first), 2))[0]
        self.assertEqual(entry(0x4c3e36, 0x509894, 0x2c, 0x29), 0x509bc8)
        self.assertEqual(entry(0x4c3e36, 0x509894, 0x4c, 0x29), 0x509948)
        self.assertEqual(entry(0x4c3f08, 0x509970, 0x4c, 0x14), 0x509970)
        self.assertEqual(entry(0x4c4024, 0x509900, 0x4c, 0x14), 0x50a2f8)
        count = self.lib.instructions(0x509894, 0x18)
        self.assertEqual(count[0x509898], ("ldrb", "w21, [x10, #0xca8]"))
        self.assertEqual(count[0x50989c], ("add", "w8, w21, #1"))
        self.assertEqual(count[0x5098a8], ("strb", "w8, [x10, #0xca8]"))
        for command, target, limit_address, limit, size_address, size in (
            (0x2b,0x50a6cc,0x50a6cc,10,0x50a6dc,46),
            (0x3b,0x50a750,0x50a750,11,0x50a760,14),
            (0x41,0x50a78c,0x50a78c,10,0x50a7ac,32),
            (0x4b,0x50a8fc,0x50a8fc,14,0x50a90c,47),
            (0x4d,0x50a7f4,0x50a7f4,19,0x50a804,47),
            (0x5c,0x50a5f0,0x50a5f0,16,0x50a600,113),
            (0x91,0x50a8dc,0x50a8dc,10,0x50a8ec,115),
        ):
            self.assertEqual(entry(0x4c3e36, 0x509894, command, 0x29), 0x509894)
            self.assertEqual(entry(0x4c3f08, 0x509970, command, 0x14), target)
            self.assertEqual(self.lib.instructions(limit_address,4)[limit_address], ("cmp", f"w21, #{hex(limit)}"))
            self.assertEqual(self.lib.instructions(size_address,4)[size_address], ("mov", f"w24, #{hex(size)}"))
        end = self.lib.instructions(0x509948, 0x3c)
        self.assertEqual(end[0x509978], ("mov", "w9, #0x2fd0"))
        self.assertEqual(end[0x509980], ("mov", "w24, #0xa"))
        self.assertEqual(self.lib.instructions(0x50a304,4)[0x50a304], ("strb", "w0, [x8, #0x528]"))

    def test_41_4d_and_epoch_words_use_different_source_byte_orders(self):
        one = self.lib.instructions(0x5040dc, 0x11c)
        for address, expected in {
            0x5040dc:("ldurb","w13, [x10, #-0xf]"), 0x5040e4:("ldurb","w13, [x10, #-0xd]"),
            0x5040f4:("ldurh","w13, [x10, #-0xb]"), 0x504100:("lsl","w13, w13, #0x10"),
            0x504104:("rev","w13, w13"), 0x504108:("bfi","w13, w14, #0x18, #8"),
            0x50410c:("bfi","w13, w15, #0x10, #8"), 0x5041d0:("str","w13, [x9, #0x20]"),
        }.items(): self.assertEqual(one[address], expected)
        two = self.lib.instructions(0x505250, 0x1b0)
        for address, expected in {
            0x505250:("ldrb","w8, [x9]"), 0x50525c:("bfi","w10, w8, #0x10, #8"),
            0x505264:("bfi","w10, w11, #8, #8"), 0x505294:("ldrb","w11, [x9, #7]"),
            0x5052a0:("lsl","w11, w11, #0x10"), 0x5052a8:("bfi","w11, w12, #0x18, #8"),
            0x5052ac:("orr","w11, w11, w13"), 0x5052b0:("bfi","w11, w14, #8, #8"),
            0x5053e8:("ldrb","w9, [x9, #0x2e]"), 0x5053fc:("str","w11, [x8, #0x37d4]"),
        }.items(): self.assertEqual(two[address], expected)
        end = self.lib.instructions(0x504a24, 0x60)
        self.assertEqual(end[0x504a3c], ("lsl", "w9, w9, #0x10"))
        self.assertEqual(end[0x504a40], ("bfi", "w9, w10, #0x18, #8"))
        self.assertEqual(end[0x504a78], ("ldrb", "w8, [x8, #9]"))

    def test_actual_software_time_message_not_a_dsp_packet(self):
        code = self.lib.instructions(0x510aa4, 0x170)
        for address, expected in {
            0x510b0c:("strh","w0, [sp, #0x88]"), 0x510b14:("str","d0, [sp, #0x90]"),
            0x510b18:("str","s1, [sp, #0x98]"), 0x510b10:("mov","w8, #8"),
            0x510b30:("mov","w8, #0x3f8"), 0x510b34:("movk","w8, #0xe8, lsl #16"),
            0x510b98:("stur","q2, [x0, #4]"), 0x510b9c:("bl","#0x508d90"),
            0x510bf8:("mov","w0, #-1"),
        }.items(): self.assertEqual(code[address], expected)
        subtype8 = 0x530250 + 4*struct.unpack("<H", self.lib.read(0x4c5244+14,2))[0]
        self.assertEqual(subtype8, 0x5324d0)
        dispatch = self.lib.instructions(subtype8, 0x18)
        self.assertEqual(dispatch[0x5324d4], ("ldur", "d0, [x24, #0x94]"))
        self.assertEqual(dispatch[0x5324dc], ("ldrh", "w0, [x24, #0x8c]"))
        self.assertEqual(dispatch[0x5324e0], ("bl", "#0x513080"))
        self.assertEqual(struct.unpack("<f", struct.pack("<I",0x4eee6b28))[0],2000000000.0)
        self.assertEqual(0x4990f83c00,315964800000)

    def test_position_layout_dimension_correction_and_gmtime_not_uart(self):
        code = self.lib.instructions(0x50e2bc, 0xe1c)
        for address, expected in {
            0x50e2f8:("mov","w2, #0xc60"), 0x50e334:("mov","w9, #0xc600000"),
            0x50e350:("str","w9, [x19]"), 0x50e45c:("strh","w0, [x19, #0x10]"),
            0x50e428:("strh","w8, [x19, #0x12]"), 0x50e420:("str","w8, [x19, #0x14]"),
            0x50e4a4:("strh","w8, [x19, #4]"), 0x50e4c0:("stur","s0, [x19, #6]"),
            0x50e4c8:("strb","w8, [x19, #0xa]"), 0x50e50c:("strb","w8, [x19, #0x19]"),
            0x50e4f4:("mov","w8, #2"), 0x50e4e8:("mov","w8, #3"),
            0x50e4f8:("b","#0x50e50c"), 0x50e4a0:("ldr","w8, [sp, #0x1e4]"),
            0x50e758:("ldr","q1, [x19, #0x30]"), 0x50e75c:("fmul","v0.2d, v1.2d, v0.2d"),
            0x50e764:("str","q0, [x19, #0x30]"),
        }.items(): self.assertEqual(code[address], expected)
        self.assertEqual(self.lib.imported_symbol(0x6e8d38), (1026,b"gmtime"))
        self.assertEqual(self.lib.imported_symbol(0x6e8e60), (1026,b"mtk_gps_get_position"))
        calendar = self.lib.instructions(0x68b094,0x24)
        self.assertEqual(calendar[0x68b0a4],("sub","w8, w8, w2, sxth"))
        self.assertEqual(0x12d53d80,315964800)
        admission=self.lib.instructions(0x534ccc,0x38)
        self.assertEqual(admission[0x534cd4],("ldr","s0, [sp, #0x3f20]"))
        self.assertEqual(admission[0x534d00],("b.gt","#0x534c8c"))
        self.assertEqual(struct.unpack("<f",struct.pack("<I",0x4400c000))[0],515.0)
        self.assertEqual(struct.unpack("<d",struct.pack("<Q",0x40d1d78000000000))[0],18270.0)
        coordinates = self.lib.instructions(0x5351c0,0xb0)
        self.assertEqual(coordinates[0x5351f4],("mov","w11, #0x53"))  # South
        self.assertEqual(coordinates[0x5351f8],("mov","w12, #0x4e"))  # North
        self.assertEqual(coordinates[0x535258],("mov","w9, #0x57"))   # West
        self.assertEqual(coordinates[0x53525c],("mov","w10, #0x45"))  # East

    def test_no_second_initialization_or_fd_owner_is_hidden_in_new_code(self):
        self.assertEqual(self.mnld.instructions(0x63c40,4)[0x63c40],("bl","#0x859b0"))
        self.assertEqual(self.lib.instructions(0x52f19c,4)[0x52f19c],("bl","#0x52f264"))
        self.assertEqual(self.lib.instructions(0x52f2bc,4)[0x52f2bc],("bl","#0x6e5520"))
        self.assertEqual(self.lib.imported_symbol(0x6e9188),(1026,b"mtk_gps_dsp_init"))
        code=(HERE/"navigation.c").read_text()
        for forbidden in ("open(","close(","dup(","read(","write(","ioctl(","dlopen(",
                          "dlsym(","CLOCK_REALTIME","time(NULL)","clock_settime(","rtc_valid",
                          "mnl_run(","mtk_gps_init(","fix_ready","private_clock"):
            self.assertNotIn(forbidden,code)
        self.assertIn("gmtime_r(&utc, &civil)",code)
        runner=(HERE/"run-ci.sh").read_text()
        self.assertLess(runner.index('"${GITHUB_ACTIONS:-}"'),runner.index('"${CC:-clang}"'))
        self.assertIn("-fsanitize=address,undefined",runner)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libmnl",type=Path,default=Path(os.environ.get("TETRIS_B41_LIBMNL",
        "/private/tmp/tetris-b41-providers-ci38048111345/vendor/lib64/mt6878/libmnl.so")))
    parser.add_argument("--mnld",type=Path,default=Path(os.environ.get("TETRIS_B41_MNLD",
        "/private/tmp/tetris-b41-providers-ci38048111345/vendor/bin/mnld")))
    args=parser.parse_args()
    LIB_PATH,MNLD_PATH=args.libmnl,args.mnld
    unittest.main(argv=[sys.argv[0]])
