#!/usr/bin/env python3
"""Immutable complete bootstrap producers; no DSO/native/session execution."""
import hashlib
from pathlib import Path
import re
import struct
import sys
import unittest

import capstone
from capstone.arm64 import ARM64_OP_MEM, ARM64_REG_SP

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA
from test_source import source


class BootstrapEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check(self, expected):
        for address, instruction in expected.items():
            self.assertEqual(self.lib.instructions(address, 4)[address], instruction, hex(address))

    def test_complete_producer_and_immutable_table_pins(self):
        self.assertEqual(capstone.__version__, "5.0.6")
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(self.mnld.data, LIB_SHA)
        for start, end, digest in (
            (0x4f0bdc, 0x4f3634, "559fc7a71f7be281bf79877e50dd3907f84bf7d4d185671c17471315989169af"),
            (0x52e3dc, 0x52e480, "7cc700f48da362fb998027bb0a72cf31b9564c654d9806cd490ad99fc70bdabb"),
            (0x27934, 0x27c04, "ec85c275d49568c182872ba5d4f51f04f47bc815b126ed0eaa1b77b5b9c08290"),
        ):
            self.assertEqual(hashlib.sha256(self.lib.read(start, end - start)).hexdigest(), digest)

    def test_exact_secure_mvcd_cw_selection_and_fragment_pair(self):
        for got, target in ((0x6e6660, 0x7178b8), (0x6e6618, 0x717cb0)):
            self.assertEqual(struct.unpack("<Q", self.lib.read(got, 8))[0], target)
        self.check({
            0x4f2244: ("ldrb", "w8, [x8, #0x33e]"),
            0x4f2250: ("cbz", "w8, #0x4f2350"),
            0x4f225c: ("ldrb", "w8, [x8]"),
            0x4f2268: ("sub", "w8, w8, #1"),
            0x4f226c: ("and", "w8, w8, #0xff"),
            0x4f2270: ("cmp", "w8, #0x3f"),
            0x4f2274: ("mov", "w8, #0x17"),
            0x4f227c: ("cinc", "w2, w8, lo"),
            0x4f32a8: ("sub", "w9, w9, #1"),
            0x4f32b0: ("and", "w9, w9, #0xff"),
            0x4f32b8: ("cmp", "w9, #0x3f"),
            0x4f32bc: ("sub", "w3, w8, #1"),
            0x4f32c0: ("mov", "w8, #0x19"),
            0x4f32c4: ("cinc", "w2, w8, lo"),
        })
        cw = {selector for selector in range(256) if ((selector - 1) & 255) < 63}
        self.assertEqual(cw, set(range(1, 64)))

    def test_query_uses_actual_retained_descriptor_not_wire_pointer(self):
        self.check({
            0x4f2280: ("add", "x4, sp, #0x118"),
            0x4f2284: ("mov", "w0, wzr"),
            0x4f2288: ("mov", "w1, w19"),
            0x52e3f8: ("cmp", "w8, #1"),
            0x52e3fc: ("b.eq", "#0x52e440"),
            0x52e444: ("ldr", "w0, [x8, #0x124]"),
            0x52e448: ("and", "w1, w2, #0xff"),
            0x52e44c: ("mov", "x2, x4"),
            0x52e450: ("bl", "#0x6e5200"),
            0x52e470: ("cset", "w8, ne"),
            0x52e474: ("lsl", "w0, w8, #1"),
            0x4f2cd4: ("add", "x2, sp, #0x6b0"),
            0x4f2cd8: ("mov", "w0, #8"),
            0x4f2cdc: ("mov", "w1, #0x35"),
        })
        # Stock collapses real ioctl failures to OEM2 and consumes output anyway.
        post = self.lib.instructions(0x4f2290, 0x4f2318 - 0x4f2290)
        self.assertFalse(any(mn.startswith("b") or mn in ("cbz", "cbnz", "tbz", "tbnz")
                             for mn, _ in post.values()))

    def test_pinned_kernel_metadata_shape_and_failures(self):
        fields = source("hw/inc/gps_dl_hw_api.h").split(
            "struct gps_dl_hw_mvcd_gps_bootup_info {", 1)[1].split("};", 1)[0]
        self.assertEqual([line.strip() for line in fields.splitlines() if line.strip()], [
            "unsigned int code_size;", "unsigned int start_addr;", "unsigned int exec_addr;",
            "unsigned int cipher_key;", "unsigned int frag_num;"
        ])
        backend = source("hw/gps_dl_hw_atf_mvcd.c")
        for field, shift in (("frag_num", 0), ("code_size", 16),
                             ("start_addr", 32), ("exec_addr", 48)):
            mask = 0xffff << shift
            suffix = ");" if shift == 0 else f") >> {shift});"
            self.assertIn(f"bootup_info->{field} = (unsigned int)(" +
                          ("" if shift == 0 else "(") +
                          f"res.a1 & 0x{mask:016X}" + suffix, backend)
        self.assertIn("bootup_info->cipher_key = (unsigned int)(res.a2 & 0x000000000000FFFF);", backend)
        self.assertIn("if (res.a1 == 0)", backend)
        self.assertIn("#define GNSS_IMAGE_MAX_FRAGEMENT_NUM 256", backend)
        self.assertIn("if (fragement_num > GNSS_IMAGE_MAX_FRAGEMENT_NUM)", backend)
        driver = source("linux/gps_each_device.c")
        for command, cw in (("GPS_GET_DSP_BOOTUP_INFO", 0), ("GPS_GET_CWDSP_BOOTUP_INFO", 1)):
            block = driver.split(f"case GPSDL_IOC_{command}:", 1)[1].split("break;\n\t}", 1)[0]
            self.assertIn("if (!dev->is_open)", block)
            self.assertIn(f"dev->index, {cw}, &bootup_info)", block)
            self.assertIn("&bootup_info, sizeof(bootup_info)", block)
            self.assertIn("retval = -EFAULT;", block)
            self.assertIn("retval = 0;", block)

    def test_zero_scalars_have_no_unclosed_direct_stack_writer(self):
        expected = {
            0xc4: {0x4f0cf8}, 0xc0: {0x4f0cfc},
            0xdc: {0x4f0c94}, 0xd8: {0x4f0c98},
            0xf4: {0x4f0c74, 0x4f2600}, 0xf0: {0x4f0c78, 0x4f2604},
        }
        actual = {offset: set() for offset in expected}
        decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
        decoder.detail = True
        for i in decoder.disasm(self.lib.read(0x4f0bdc, 0x4f2ad8 - 0x4f0bdc), 0x4f0bdc):
            if i.mnemonic not in ("str", "strb", "strh", "stur", "sturb", "sturh", "stp"):
                continue
            mem = i.operands[-1]
            if mem.type != ARM64_OP_MEM or mem.mem.base != ARM64_REG_SP:
                continue
            reg = i.reg_name(i.operands[0].reg)
            if i.mnemonic.endswith("b"):
                width = 1
            elif i.mnemonic.endswith("h"):
                width = 2
            elif reg in ("fp", "lr"):
                width = 8
            else:
                width = {"w": 4, "x": 8, "s": 4, "d": 8, "q": 16}[reg[0]]
            width *= 2 if i.mnemonic == "stp" else 1
            for offset in actual:
                if mem.mem.disp <= offset < mem.mem.disp + width:
                    actual[offset].add(i.address)
                    self.assertEqual(i.op_str, f"wzr, [sp, #0x{offset:x}]")
        self.assertEqual(actual, expected)

    def test_remaining_56_payload_bytes_have_exact_source_stores(self):
        covered = {0, 1, 2, 3, 26, 27, 28, 29}
        self.check({
            0x4f263c: ("strb", "wzr, [sp, #0xe4]"),
            0x4f2640: ("strb", "wzr, [sp, #0xe0]"),
            0x4f2664: ("mov", "w8, #0x1a"),
            0x4f2674: ("strh", "w8, [sp, #0x6b0]"),
            0x4f2734: ("mov", "w9, #0x50000"),
            0x4f273c: ("stur", "w9, [x27, #0x1a]"),
        })
        for dest, stack, load, store in (
            (10, 0xc4, 0x4f26b8, 0x4f26bc), (11, 0xc0, 0x4f26c0, 0x4f26c4),
            (12, 0xdc, 0x4f26c8, 0x4f26cc), (13, 0xd8, 0x4f26d0, 0x4f26d4),
            (24, 0xf4, 0x4f2728, 0x4f272c), (25, 0xf0, 0x4f2730, 0x4f2738),
        ):
            self.check({load: ("ldrb", f"w8, [sp, #0x{stack:x}]"),
                        store: ("strb", f"w8, [sp, #0x{0x6b0 + dest:x}]")})
            covered.add(dest)
        for index, stack in enumerate((0x114, 0x110, 0x10c, 0x108, 0x104,
                                        0x100, 0xfc, 0xf8, 0xec, 0xe8)):
            load = 0x4f26d8 + 8 * index
            self.check({load: ("ldrb", f"w8, [sp, #0x{stack:x}]"),
                        load + 4: ("strb", f"w8, [sp, #0x{0x6be + index:x}]")})
            covered.add(14 + index)
        covered.update(range(62, 94))
        fields = set(range(4, 10)) | set(range(30, 62)) | set(range(94, 106))
        self.assertEqual(len(covered), 56)
        self.assertFalse(covered & fields)
        self.assertEqual(covered | fields, set(range(106)))

    def test_metadata_low_halfwords_are_copied_from_real_query_fields(self):
        self.check({
            0x4f2290: ("ldr", "w7, [sp, #0x118]"),
            0x4f2294: ("ldr", "w8, [sp, #0x11c]"),
            0x4f2298: ("ldr", "w9, [sp, #0x120]"),
            0x4f229c: ("ldr", "w10, [sp, #0x124]"),
            0x4f22a0: ("strb", "w7, [sp, #0x114]"),
            0x4f22b8: ("strb", "w11, [sp, #0x110]"),
            0x4f22a8: ("strb", "w8, [sp, #0x10c]"),
            0x4f22c0: ("strb", "w12, [sp, #0x108]"),
            0x4f22b0: ("strb", "w9, [sp, #0x104]"),
            0x4f22c8: ("strb", "w13, [sp, #0x100]"),
            0x4f22e4: ("strb", "w10, [sp, #0xfc]"),
            0x4f22cc: ("strb", "w11, [sp, #0xf8]"),
            0x4f22d8: ("strb", "w12, [sp, #0xec]"),
            0x4f22e8: ("strb", "w11, [sp, #0xe8]"),
        })

    def test_nonzero_profile_block_uses_original_context_frequency(self):
        self.check({
            0x4f213c: ("ldr", "w21, [x26, #0x18]"),
            0x4f2140: ("adrp", "x1, #0x27000"),
            0x4f2144: ("add", "x1, x1, #0x934"),
            0x4f214c: ("mov", "w2, #0x2d0"),
            0x4f2168: ("b.lo", "#0x4f2348"),
            0x4f217c: ("b.ls", "#0x4f257c"),
            0x4f2348: ("mov", "x9, xzr"),
            0x4f257c: ("mov", "w9, #1"),
            0x4f3530: ("mov", "w9, #2"),
            0x4f3590: ("mov", "w9, #3"),
            0x4f3598: ("mov", "w9, #4"),
            0x4f35a0: ("mov", "w9, #5"),
            0x4f35a8: ("mov", "w9, #6"),
            0x4f35b0: ("mov", "w9, #7"),
            0x4f35dc: ("mov", "w9, #8"),
            0x4f35e4: ("mov", "w9, #9"),
            0x4f35ec: ("mov", "w10, #0x48"),
            0x4f35f0: ("madd", "x9, x9, x10, x20"),
            0x4f35f4: ("orr", "x9, x9, #1"),
            0x4f35f8: ("mov", "w10, #-5"),
            0x4f35fc: ("add", "x11, sp, #0x720"),
            0x4f3604: ("ldur", "w12, [x9, #-1]"),
            0x4f3608: ("strh", "w12, [x11, x8]"),
            0x4f3618: ("cmp", "x8, #0x24"),
            0x4f361c: ("b.eq", "#0x4f2220"),
            0x4f3620: ("cmp", "w10, #3"),
            0x4f3624: ("b.hi", "#0x4f3604"),
            0x4f3628: ("ldrb", "w12, [x9]"),
        })
        code = (HERE / "bootstrap.c").read_text()
        body = code.split("common[16] = {", 1)[1].split("};", 1)[0]
        actual = [int(word) for word in re.findall(r"\b\d+\b", body)]
        for row in range(10):
            words = struct.unpack("<18I", self.lib.read(0x27934 + row * 72, 72))
            expected = [(word >> 8) & 255 if 5 <= index <= 8 else word & 65535
                        for index, word in enumerate(words[:16])]
            self.assertEqual(actual, expected, f"row{row}")

    def test_frequency_windows_match_exact_unsigned_instruction_bounds(self):
        constants = []
        for address, low, high, count, condition in (
            (0x4f2158, 0xe518, 0xff48, 0x31, "b.lo"),
            (0x4f216c, 0xdc20, 0xff0b, 0x40, "b.ls"),
            (0x4f2180, 0x0826, 0xfedb, 0x4d, "b.lo"),
            (0x4f2194, 0xd328, 0xfece, 0x51, "b.lo"),
            (0x4f21a8, 0xca30, 0xfe91, 0x61, "b.lo"),
            (0x4f21bc, 0x45b4, 0xfe73, 0x69, "b.lo"),
            (0x4f21d0, 0xb840, 0xfe17, 0x81, "b.lo"),
            (0x4f21e4, 0x104c, 0xfdb6, 0x99, "b.lo"),
            (0x4f21f8, 0xa650, 0xfd9d, 0xa1, "b.lo"),
            (0x4f220c, 0x8b68, 0xfce6, 0xd1, "b.lo"),
        ):
            self.check({address: ("mov", f"w8, #0x{low:x}"),
                        address + 4: ("movk", f"w8, #0x{high:x}, lsl #16"),
                        address + 8: ("add", "w8, w21, w8"),
                        address + 12: ("cmp", f"w8, #0x{count:x}")})
            self.assertEqual(self.lib.instructions(address + 16, 4)[address + 16][0], condition)
            constants.append(((-(low | high << 16)) & 0xffffffff,
                              count + (condition == "b.ls")))
        code = (HERE / "bootstrap.c").read_text().split("windows[] = {", 1)[1].split("};", 1)[0]
        self.assertEqual([(int(a), int(b)) for a, b in re.findall(r"\{(\d+)u, (\d+)u\}", code)],
                         constants)

    def test_synthetic_golden_covers_full_payload_and_frame_checksum(self):
        fixture = (HERE / "test_bootstrap.c").read_text().split("expected[106] = {", 1)[1].split("};", 1)[0]
        payload = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-f]+)", fixture))
        self.assertEqual(len(payload), 106)
        self.assertEqual(payload[:4], b"\x1a\0\0\0")
        self.assertEqual(payload[10:14], bytes(4))
        self.assertEqual(payload[24:30], b"\0\0\0\0\x05\0")
        self.assertEqual(sum(b"\x6e\0\x08\xfe" + payload), 0x1788)
        row = struct.unpack("<18I", self.lib.read(0x27934 + 5 * 72, 72))
        expected = b"".join(struct.pack("<H", (word >> 8) & 255 if 5 <= i <= 8 else word & 65535)
                            for i, word in enumerate(row[:16]))
        self.assertEqual(payload[62:94], expected)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_bootstrap_source.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
