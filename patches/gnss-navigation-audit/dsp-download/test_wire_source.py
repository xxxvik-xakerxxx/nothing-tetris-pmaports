#!/usr/bin/env python3
"""Pinned static MVCD wire proof; no native execution or session data."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA

ROUTINES = (
    (0x554828, 0x554aec, "d10beb55cf93ba411ab3deace29bf7649e15f699449ad4167c7be15b481dc06b"),
    (0x554c64, 0x554da4, "dedfabbd96818b594aabc7db7a21e3fcd4a7af3c3d98771dfa8f0875957ac25b"),
    (0x4f2624, 0x4f2ad8, "1b8512239ea4298a0f603c8c227e528cbec45e88fb9864e4a2623caaa3892341"),
    (0x4f05f4, 0x4f0a18, "19d5202a6ce2748d186f64279c20aaa7bf6cbe689e0d44139e94e2fec6ee812e"),
    (0x682ef8, 0x68358c, "40dbc40558e5efd2be0c9be54053615693b5458f6af5661ab90601f3966cae90"),
    (0x509830, 0x50acc8, "9c6760cd19c9923aef5b102aa886e65acf0361264e1ee633d6c939c7cef0633a"),
)


class WireEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check(self, expectations):
        for address, instruction in expectations.items():
            self.assertEqual(self.lib.instructions(address, 4)[address], instruction, hex(address))

    def table_target(self, table, origin, command, minimum):
        offset = struct.unpack("<H", self.lib.read(table + 2 * (command - minimum), 2))[0]
        return origin + 4 * offset

    def test_hash_pins_before_any_decode(self):
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(self.mnld.data, LIB_SHA)
        for start, end, digest in ROUTINES:
            self.assertEqual(hashlib.sha256(self.lib.read(start, end - start)).hexdigest(), digest)

    def test_halfword_count_and_pointer_is_not_wire_data(self):
        self.check({
            0x4f2cd4: ("add", "x2, sp, #0x6b0"),
            0x4f2cd8: ("mov", "w0, #8"),
            0x4f2cdc: ("mov", "w1, #0x35"),
            0x5548c8: ("lsl", "w8, w19, #1"),
            0x5548d4: ("add", "w8, w8, #4"),
            0x55490c: ("stur", "x22, [sp, #6]"),
            0x5549fc: ("ldur", "x1, [sp, #6]"),
            0x554a04: ("ldrh", "w8, [sp, #2]"),
            0x554a08: ("sub", "w2, w8, #4"),
            0x554a10: ("bl", "#0x683b9c"),
        })
        self.assertEqual(0x35 << 1, 106)
        self.assertEqual(2 + 4 + 106 + 2 + 2, 116)
        self.assertNotEqual(0x35 << 1, 212)

    def test_additive_checksum_and_frame_constants(self):
        self.check({
            0x5548cc: ("mov", "w9, #0xf0aa"),
            0x5548d0: ("mov", "w11, #0xfe00"),
            0x5548dc: ("bfxil", "w11, w23, #0, #8"),
            0x5548ec: ("strh", "w8, [sp, #2]"),
            0x5548f0: ("add", "w10, w10, w9, lsr #8"),
            0x5548fc: ("add", "w8, w10, w12"),
            0x554900: ("add", "w10, w8, #0xfe"),
            0x55497c: ("uaddw", "v0.8h, v0.8h, v2.8b"),
            0x554980: ("uaddw", "v1.8h, v1.8h, v3.8b"),
            0x554994: ("addv", "h0, v0.8h"),
            0x5549a4: ("ldrb", "w12, [x11], #1"),
            0x5549ac: ("add", "w10, w10, w12"),
            0x5549bc: ("mov", "w8, #0xfaa"),
            0x5549c0: ("strh", "w10, [sp, #0xe]"),
            0x554d20: ("ldrh", "w8, [x0, #0xe]"),
            0x554d24: ("cmp", "w8, w10, uxth"),
        })

    def test_every_payload_byte_has_a_traced_destination(self):
        covered = set()

        def mark(start, size):
            self.assertFalse(covered.intersection(range(start, start + size)))
            covered.update(range(start, start + size))

        self.check({0x4f2674: ("strh", "w8, [sp, #0x6b0]")})
        mark(0, 2)
        sources = [0xe4, 0xe0, 0xcc, 0xc8, 0x130, 0x131, 0x12c, 0x12d,
                   0xc4, 0xc0, 0xdc, 0xd8, 0x114, 0x110, 0x10c, 0x108,
                   0x104, 0x100, 0xfc, 0xf8, 0xec, 0xe8, 0xf4, 0xf0]
        for index, source in enumerate(sources):
            address = 0x4f2678 + 8 * index
            destination = 0x6b2 + index
            store = address + (8 if index == 23 else 4)
            self.check({address: ("ldrb", f"w8, [sp, #0x{source:x}]"),
                        store: ("strb", f"w8, [sp, #0x{destination:x}]")})
            mark(2 + index, 1)
        self.check({0x4f2734: ("mov", "w9, #0x50000"),
                    0x4f273c: ("stur", "w9, [x27, #0x1a]")})
        mark(26, 4)
        for index in range(28):
            store = 0x4f2744 + 8 * index if index < 27 else 0x4f282c
            self.check({0x4f2740 + 8 * index: ("ldrb", f"w8, [sp, #0x{0x750 + index:x}]"),
                        store: ("strb", f"w8, [sp, #0x{0x6ce + index:x}]")})
            mark(30 + index, 1)
        self.check({0x4f2848: ("strh", "w10, [sp, #0x6ea]"),
                    0x4f285c: ("strb", "w8, [sp, #0x6ea]"),
                    0x4f2860: ("strb", "wzr, [sp, #0x6eb]"),
                    0x4f28b0: ("strh", "w9, [sp, #0x6ea]"),
                    0x4f28b8: ("strb", "w9, [sp, #0x6ec]"),
                    0x4f28c0: ("strb", "w9, [sp, #0x6ed]")})
        mark(58, 4)
        for index in range(32):
            load = 0x4f28c4 + 8 * index
            store = load + 4
            if index == 30:
                store = 0x4f29c0
            elif index == 31:
                load, store = 0x4f29c4, 0x4f29d0
            self.check({load: ("ldrb", f"w9, [sp, #0x{0x720 + index:x}]"),
                        store: ("strb", f"w9, [sp, #0x{0x6ee + index:x}]")})
            mark(62 + index, 1)
        self.check({
            0x4f29d4: ("strb", "w10, [sp, #0x70e]"),
            0x4f29dc: ("strb", "w11, [sp, #0x70f]"),
            0x4f29ec: ("strb", "w8, [sp, #0x710]"),
            0x4f29f0: ("strb", "w10, [sp, #0x711]"),
            0x4f2a40: ("strb", "w10, [sp, #0x712]"),
            0x4f2a48: ("strb", "w11, [sp, #0x713]"),
            0x4f2a74: ("strb", "w8, [sp, #0x714]"),
            0x4f2a78: ("strb", "wzr, [sp, #0x715]"),
            0x4f2acc: ("strb", "w24, [sp, #0x716]"),
            0x4f2abc: ("mov", "w9, #0x4e00"),
            0x4f2ac4: ("mov", "w8, #0x4f"),
            0x4f2ad0: ("sturh", "w9, [x27, #0x67]"),
            0x4f2ad4: ("strb", "w8, [sp, #0x719]"),
        })
        mark(94, 12)
        self.assertEqual(covered, set(range(106)))

    def test_clock_block_is_synthesized_not_dummy_zero(self):
        self.check({
            0x4f2120: ("ldr", "w2, [x26, #0x18]"),
            0x4f2124: ("add", "x4, sp, #0x750"),
            0x4f2128: ("add", "x5, sp, #0x130"),
            0x4f212c: ("add", "x6, sp, #0x12c"),
            0x4f2130: ("mov", "w0, w28"),
            0x4f2134: ("mov", "w1, wzr"),
            0x4f2138: ("bl", "#0x4f05f4"),
            0x4f0648: ("ldrb", "w8, [x9, #0x13]"),
            0x4f0658: ("bl", "#0x5523c0"),
            0x4f0684: ("csel", "w22, w22, w25, eq"),
            0x4f087c: ("bl", "#0x574f04"),
            0x4f0980: ("strh", "w27, [x19]"),
            0x4f09c8: ("strh", "w0, [x19, #0x1a]"),
            0x4f20c0: ("str", "q0, [sp, #0x720]"),
            0x4f20c4: ("str", "q0, [sp, #0x730]"),
        })

    def test_ack_tables_distinguish_bootstrap_fragment_and_unrelated_ack(self):
        for command in (0x31, 0x32, 0x33):
            self.assertEqual(self.table_target(0x4c3e36, 0x509894, command, 0x29), 0x509eec)
        for command, copy, completion in ((0x31, 0x509984, 0x509f98),
                                           (0x32, 0x509f20, 0x50a228),
                                           (0x33, 0x509984, 0x50a254)):
            self.assertEqual(self.table_target(0x4c3f08, 0x509970, command, 0x14), copy)
            self.assertEqual(self.table_target(0x4c4024, 0x509900, command, 0x14), completion)
        self.check({
            0x509fb4: ("and", "x10, x10, #0xffffffffffff7fff"),
            0x509fc8: ("ldrh", "w10, [x11]"),
            0x509fd0: ("str", "x10, [x9]"),
            0x509fd4: ("ldrh", "w8, [x8]"),
            0x509fe0: ("str", "x8, [x9]"),
            0x50a244: ("and", "x10, x10, #0xffffffffffffffdf"),
            0x50a24c: ("ldrh", "w8, [x8, #0xd00]"),
            0x50a250: ("b", "#0x50a280"),
            0x50a270: ("and", "x10, x10, #0xffffffffffffbfff"),
            0x50a288: ("str", "x8, [x9]"),
            0x4f2dd4: ("tbnz", "w8, #0xf, #0x4f2d70"),
            0x4f2e08: ("cmp", "w6, w9"),
            0x4f33a4: ("tbnz", "w8, #5, #0x4f3340"),
            0x4f33e4: ("cmp", "w27, w9"),
            0x4f33e8: ("b.ne", "#0x4f3438"),
        })

    def test_wire_receive_checks_before_dispatch(self):
        self.check({
            0x554788: ("sub", "w8, w8, #5"),
            0x55478c: ("and", "w8, w8, #0xffff"),
            0x554790: ("cmp", "w8, #0x3f6"),
            0x554794: ("cset", "w9, lo"),
            0x5547c0: ("and", "w8, w8, #0xfff"),
            0x5547c4: ("sub", "w8, w8, #4"),
            0x6832a8: ("cmp", "w8, #0xaa"),
            0x6832b4: ("cmp", "w8, #0xf0"),
            0x6832c0: ("cmp", "w8, #0xaa"),
            0x6832cc: ("cmp", "w8, #0xf"),
            0x6832dc: ("bl", "#0x554c64"),
            0x683350: ("cbz", "w8, #0x683404"),
            0x554d44: ("mov", "w8, #0xfe00"),
            0x554d50: ("cmp", "w9, w8"),
            0x554d64: ("sub", "w1, w10, #4"),
            0x554d6c: ("lsr", "w2, w8, #0xc"),
            0x554d8c: ("bl", "#0x509830"),
        })

    def test_short_ack_stale_bytes_are_not_a_safe_acceptance_policy(self):
        # Stock caps the copy but does not require complete ACK fields.
        self.check({0x509f00: ("mov", "w24, #0xa"),
                    0x509f2c: ("mov", "w24, #2"),
                    0x509984: ("cmp", "w24, w23, uxth"),
                    0x5099c8: ("tst", "w23, #0xffff"),
                    0x5099cc: ("b.eq", "#0x509a3c"),
                    0x509a30: ("cmp", "w10, w24, uxth"),
                    0x509a5c: ("ldrh", "w12, [x10, x9, lsl #1]")})
        copy = self.lib.instructions(0x509984, 0x509a68 - 0x509984)
        self.assertNotIn(("cmp", "w23, #4"), copy.values())
        self.assertNotIn(("cmp", "w23, #2"), copy.values())

    def test_unclosed_dynamic_inputs_are_explicit(self):
        self.check({
            0x4f0e8c: ("ldr", "w8, [x26, #0x1c]"),
            0x4f2094: ("ldrb", "w8, [x26, #0x13]"),
            0x4f20f8: ("ldrb", "w9, [x26, #0x24]"),
            0x4f287c: ("ldr", "w8, [x26, #0x30]"),
            0x4f29c8: ("ldr", "w10, [x10]"),
            0x4f29f8: ("ldr", "w10, [x26, #0x54]"),
            0x4f2a7c: ("bl", "#0x508d0c"),
            0x4f2a98: ("tbz", "w9, #6, #0x4f2ab0"),
            0x4f2aa0: ("bl", "#0x5cc564"),
        })
        codec = (HERE / "wire.c").read_text()
        self.assertNotIn("ioctl(", codec)
        self.assertNotIn("dlopen(", codec)
        self.assertIn("#define B41_MVCD_ACK_PAYLOAD_MAX 1014u", (HERE / "wire.h").read_text())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_wire_source.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
