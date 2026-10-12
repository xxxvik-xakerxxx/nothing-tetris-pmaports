#!/usr/bin/env python3
"""Hash-pinned static disassembly and source checks. Never executes either ELF."""
from pathlib import Path
import re
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA


class NativeSatelliteEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check_code(self, image, expected):
        for address, text in expected.items():
            self.assertEqual(image.instructions(address, 4)[address], text,
                             hex(address))

    def test_wrong_binary_rejected(self):
        with self.assertRaises(ValueError):
            PinnedImage(self.mnld.data, LIB_SHA)
        with self.assertRaises(ValueError):
            PinnedImage(self.lib.data, MNLD_SHA)

    def test_both_request_producers(self):
        # The second request handler repeats the same packing, displaced914.
        common = {
            0x51760: ("ldr", "x9, [x19]"),
            0x51768: ("adr", "x8, #0x9a925"),
            0x5176c: ("ldur", "x10, [x19, #6]"),
            0x51770: ("movi", "v2.4h, #1"),
            0x51774: ("adrp", "x11, #0x22000"),
            0x51778: ("ldr", "d0, [x11, #0xab8]"),
            0x51780: ("stur", "x10, [x8, #6]"),
            0x51784: ("str", "x9, [x8]"),
            0x51788: ("ldur", "s1, [x8, #0xa]"),
            0x5178c: ("ldr", "s3, [x8, #4]"),
            0x51790: ("adrp", "x9, #0x22000"),
            0x51794: ("ldr", "d4, [x9, #0xb50]"),
            0x51798: ("adrp", "x9, #0x22000"),
            0x5179c: ("ldr", "d5, [x9, #0xb88]"),
            0x517a0: ("ushll", "v1.8h, v1.8b, #0"),
            0x517a4: ("ldrb", "w9, [x8, #8]"),
            0x517a8: ("ushll", "v3.8h, v3.8b, #0"),
            0x517ac: ("ldrb", "w16, [x8, #2]"),
            0x517b0: ("and", "v1.8b, v1.8b, v2.8b"),
            0x517b4: ("ldrb", "w1, [x8, #3]"),
            0x517b8: ("ushl", "v2.4h, v3.4h, v4.4h"),
            0x517bc: ("ushl", "v0.4h, v1.4h, v0.4h"),
            0x517c0: ("ubfiz", "w9, w9, #7, #1"),
            0x517c4: ("ldrb", "w2, [x8, #1]"),
            0x517c8: ("and", "v1.8b, v2.8b, v5.8b"),
            0x517cc: ("umov", "w10, v0.h[3]"),
            0x517d0: ("umov", "w11, v0.h[2]"),
            0x517d4: ("umov", "w12, v1.h[3]"),
            0x517d8: ("umov", "w13, v1.h[2]"),
            0x517dc: ("umov", "w17, v0.h[1]"),
            0x517e0: ("umov", "w0, v0.h[0]"),
            0x517e4: ("umov", "w14, v1.h[1]"),
            0x517e8: ("umov", "w15, v1.h[0]"),
            0x517ec: ("ubfiz", "w16, w16, #1, #1"),
            0x517f0: ("orr", "w10, w11, w10"),
            0x517f4: ("bfi", "w16, w1, #2, #1"),
            0x517f8: ("orr", "w12, w13, w12"),
            0x517fc: ("orr", "w13, w0, w17"),
            0x51804: ("orr", "w10, w13, w10"),
            0x51808: ("orr", "w14, w15, w14"),
            0x5180c: ("orr", "w9, w10, w9"),
            0x51814: ("orr", "w11, w14, w12"),
            0x5181c: ("and", "w13, w2, #1"),
            0x51820: ("orr", "w9, w11, w9"),
            0x51828: ("orr", "w10, w16, w13"),
            0x51830: ("orr", "w9, w9, w10"),
            0x51838: ("adrp", "x19, #0xdd000"),
            0x5183c: ("strh", "w9, [x19, #0xd90]"),
        }
        self.check_code(self.mnld, common)
        self.check_code(self.mnld, {a + 0x914: i for a, i in common.items()})
        names = self.mnld.read(0x135ac, 400).split(b"\0", 1)[0]
        self.assertIn(b"gps_sat_en = %d, glonass_sat_en = %d", names)
        self.assertIn(b"a_glonass_sat_en = %d", names)
        self.assertIn(b"a_gps_satellite_enable = %d", names)

    def test_lane_tables_and_all_native_boolean_vectors(self):
        high = struct.unpack("<4H", self.mnld.read(0x22ab8, 8))
        low = struct.unpack("<4H", self.mnld.read(0x22b50, 8))
        masks = struct.unpack("<4H", self.mnld.read(0x22b88, 8))
        self.assertEqual(high, (9, 8, 11, 10))
        self.assertEqual(low, (3, 4, 5, 6))
        self.assertEqual(masks, (8, 16, 32, 64))
        source = (HERE / "b41_native_satellite_config.c").read_text()
        literal = re.search(r"bits\[B41_SAT_COUNT\] = \{([^}]+)\}", source)[1]
        bits = tuple(int(v) for v in literal.split(",") if v.strip())
        self.assertEqual(bits, (0, 1, 2, *low, 7, *high))
        results = set()
        for vector in range(4096):
            values = [(vector >> i) & 1 for i in range(12)]
            # Algebraic reduction of the pinned vector lanes, no CPU emulator.
            packed = values[0] | values[1] << 1 | values[2] << 2 | values[7] << 7
            for value, shift, mask in zip(values[3:7], low, masks):
                packed |= (value << shift) & mask
            for value, shift in zip(values[8:], high):
                packed |= value << shift
            candidate = sum(value << bit for value, bit in zip(values, bits))
            self.assertEqual(candidate, packed)
            results.add(packed)
        self.assertEqual(results, set(range(4096)))

    def test_startup_overwrites_constant_receipts(self):
        self.check_code(self.mnld, {
            0x62b64: ("adr", "x20, #0xde520"),
            0x63530: ("ldr", "w8, [x8, #0x4a4]"),
            0x6353c: ("adrp", "x21, #0xde000"),
            0x63540: ("add", "x21, x21, #0x578"),
            0x63544: ("cmp", "w8, #1"),
            0x6354c: ("cset", "w8, ne"),
            0x63564: ("strb", "w8, [x21, #2]"),
            0x63640: ("adr", "x8, #0xddd90"),
            0x63650: ("ldrh", "w8, [x8]"),
            0x63658: ("strh", "w8, [x21]"),
            0x63c34: ("adr", "x0, #0xde520"),
            0x63c3c: ("adr", "x1, #0xde590"),
        })
        self.assertEqual(0xde578 - 0xde520, 0x58)

    def test_library_copies_and_consumes_mask_pairs(self):
        self.check_code(self.lib, {
            0x52e2bc: ("b", "#0x52b638"),
            0x52b680: ("ldp", "q1, q0, [x0, #0x50]"),
            0x52b688: ("stp", "q1, q0, [x22, #0x50]"),
            0x52e728: ("ldp", "q0, q1, [x2, #0x50]"),
            0x52e734: ("stp", "q0, q1, [x24, #0x50]"),
            0x52e86c: ("ldrh", "w9, [x24, #0x58]"),
            0x52e91c: ("mov", "w10, #0x21"),
            0x52e924: ("bics", "wzr, w10, w9"),
            0x52e92c: ("cset", "w10, eq"),
            0x52e944: ("mov", "w13, #0x12"),
            0x52e94c: ("bics", "wzr, w13, w9"),
            0x52e95c: ("mov", "w13, #0x44"),
            0x52e964: ("bics", "wzr, w13, w9"),
            0x52e984: ("mov", "w14, #0x88"),
            0x52e98c: ("bics", "wzr, w14, w9"),
            0x52e9ac: ("mov", "w13, #0x500"),
            0x52e9b4: ("bics", "wzr, w13, w9"),
            0x52e9c4: ("mov", "w13, #0xa00"),
            0x52e9cc: ("bics", "wzr, w13, w9"),
        })

    def test_factory_selector_is_separate_from_satellite_mask(self):
        self.assertEqual(self.mnld.read(0xb44b, 23), b"factory_mnld_gps_start\0")
        self.check_code(self.mnld, {
            0x5c598: ("adr", "x8, #0xde4a4"),
            0x5c59c: ("mov", "w9, #1"),
            0x5c5b8: ("str", "w9, [x8]"),
            0x5c660: ("adr", "x8, #0xde4a4"),
            0x5c664: ("str", "wzr, [x8]"),
        })

    def test_native_ownership_and_ci_boundary(self):
        source = (HERE / "b41_native_satellite_config.c").read_text()
        for forbidden in ("__system_property", "dlopen(", "ioctl(", "socket(",
                          "missing_inputs =", "xml_policy_missing =", "malloc("):
            self.assertNotIn(forbidden, source)
        for required in ("result = *base;", "settings->enabled[i] > 1",
                         "return -ESTALE;", "B41_FIRST_UNKNOWN", "*out = result;"):
            self.assertIn(required, source)
        runner = (HERE / "run_ci.sh").read_text()
        self.assertIn('"${CI:-}" != true', runner)
        self.assertIn("-fsanitize=address,undefined", runner)
        self.assertNotIn("b41_receiver_policy.c", runner)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_static.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
