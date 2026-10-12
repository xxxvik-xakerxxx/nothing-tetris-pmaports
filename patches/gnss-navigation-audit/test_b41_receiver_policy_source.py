#!/usr/bin/env python3
"""Pinned static producer/INIT consumer evidence. No instruction execution."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

MNLD_SHA = "285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83"
LIB_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
HERE = Path(__file__).resolve().parent


class PinnedImage:
    def __init__(self, data, digest):
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("wrong B4.1 SHA256")
        if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
            raise ValueError("expected little-endian AArch64 ELF64")
        self.data = data
        offset = struct.unpack_from("<Q", data, 32)[0]
        size, count = struct.unpack_from("<HH", data, 54)
        if size != 56 or offset + size * count > len(data):
            raise ValueError("invalid program headers")
        self.loads = []
        for index in range(count):
            kind, flags, file_offset, address, _, file_size, _, _ = struct.unpack_from(
                "<II6Q", data, offset + index * size)
            if kind == 1:
                if file_offset + file_size > len(data):
                    raise ValueError("invalid file-backed segment")
                self.loads.append((address, file_size, file_offset, flags))

    def read(self, address, size):
        for start, length, offset, _ in self.loads:
            if start <= address and address + size <= start + length:
                return self.data[offset + address - start:offset + address - start + size]
        raise ValueError("unbacked virtual address")

    def instructions(self, address, size):
        decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
        result = {i.address: (i.mnemonic, i.op_str) for i in decoder.disasm(self.read(address, size), address)}
        if len(result) != size // 4:
            raise ValueError("incomplete static instruction decode")
        return result

    def imported_symbol(self, slot):
        offset = struct.unpack_from("<Q", self.data, 40)[0]
        size, count = struct.unpack_from("<HH", self.data, 58)
        sections = [struct.unpack_from("<II4QII2Q", self.data, offset + index * size)
                    for index in range(count)]
        for section in sections:
            if section[1] != 4:  # SHT_RELA
                continue
            symbols = sections[section[6]]
            strings = sections[symbols[6]]
            for entry in range(section[4], section[4] + section[5], section[9]):
                address, info, _ = struct.unpack_from("<QQq", self.data, entry)
                if address == slot:
                    self_info = struct.unpack_from("<I", self.data, symbols[4] + (info >> 32) * symbols[9])[0]
                    text = self.data[strings[4] + self_info:strings[4] + strings[5]]
                    return info & 0xffffffff, text.split(b"\0", 1)[0]
        raise ValueError("missing relocation")


class ReceiverPolicySource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld = PinnedImage(MNLD_PATH.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB_PATH.read_bytes(), LIB_SHA)

    def test_pin_rejects_other_assets_before_decode(self):
        for image, digest in ((self.mnld, LIB_SHA), (self.lib, MNLD_SHA)):
            with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
                PinnedImage(image.data, digest)
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(b"not a vendor ELF", MNLD_SHA)

    def test_property_keys_and_order(self):
        self.assertEqual(self.mnld.read(0x138bd, 14), b"ro.build.type\0")
        self.assertEqual(self.mnld.read(0x138cb, 14), b"ro.debuggable\0")
        code = self.mnld.instructions(0x628f4, 0x54)
        expected = {
            0x628f4: ("adrp", "x0, #0x13000"),
            0x628f8: ("add", "x0, x0, #0x8bd"),
            0x62904: ("add", "x1, sp, #0x60"),
            0x62908: ("mov", "x2, xzr"),
            0x62930: ("bl", "#0x85530"),
            0x62934: ("adrp", "x0, #0x13000"),
            0x62938: ("add", "x0, x0, #0x8cb"),
            0x6293c: ("mov", "x1, sp"),
            0x62940: ("mov", "x2, xzr"),
            0x62944: ("bl", "#0x85530"),
        }
        for address, instruction in expected.items():
            self.assertEqual(code[address], instruction)
        veneer = self.mnld.instructions(0x85530, 16)
        self.assertEqual(veneer[0x85530], ("adrp", "x16, #0x86000"))
        self.assertEqual(veneer[0x85534], ("ldr", "x17, [x16, #0xbc8]"))
        self.assertEqual(self.mnld.imported_symbol(0x86bc8), (1026, b"property_get"))

    def test_stock_string_comparisons_and_return_mapping(self):
        code = self.mnld.instructions(0x62948, 0x80)
        # eng is an exact four-byte match, including NUL, not a prefix.
        self.assertEqual(0x676000 + 0xe65, int.from_bytes(b"eng\0", "little"))
        self.assertEqual(code[0x62948], ("ldr", "w8, [sp, #0x60]"))
        self.assertEqual(code[0x6294c], ("sub", "w8, w8, #0x676, lsl #12"))
        self.assertEqual(code[0x62950], ("cmp", "w8, #0xe65"))
        self.assertEqual(code[0x62954], ("b.eq", "#0x629a4"))
        self.assertEqual(code[0x629a4], ("ldrh", "w8, [sp]"))
        self.assertEqual(code[0x629a8], ("cmp", "w8, #0x31"))
        self.assertEqual(code[0x629b0], ("cneg", "w19, w8, eq"))
        # userdebug builds a literal from four MOV/MOVK chunks, then 'g'+NUL.
        chunks = (0x7375, 0x7265, 0x6564, 0x7562)
        self.assertEqual(struct.pack("<4H", *chunks) + b"g\0", b"userdebug\0")
        for address, instruction in {
            0x62958: ("mov", "x10, #0x7375"),
            0x62960: ("movk", "x10, #0x7265, lsl #16"),
            0x62968: ("movk", "x10, #0x6564, lsl #32"),
            0x6296c: ("movk", "x10, #0x7562, lsl #48"),
            0x62964: ("ldrh", "w9, [sp, #0x68]"),
            0x62974: ("mov", "w8, #0x67"),
            0x62978: ("ccmp", "w9, w8, #0, eq"),
            0x6297c: ("b.eq", "#0x629b8"),
            0x629bc: ("cmp", "w8, #0x31"),
            0x629c0: ("mov", "w8, #2"),
            0x629c4: ("csinv", "w19, w8, wzr, eq"),
            0x62984: ("mov", "w10, #0x7375"),
            0x6298c: ("movk", "w10, #0x7265, lsl #16"),
            0x62988: ("ldrb", "w9, [sp, #0x64]"),
            0x62994: ("orr", "w8, w8, w9"),
            0x6299c: ("csetm", "w19, ne"),
        }.items():
            self.assertEqual(code[address], instruction)
        self.assertEqual(struct.pack("<HH", 0x7375, 0x7265) + b"\0", b"user\0")
        self.assertEqual(self.mnld.instructions(0x629fc, 4)[0x629fc], ("mov", "w0, w19"))

    def test_second_block_offsets_and_conditional_log_bit(self):
        code = self.mnld.instructions(0x63690, 0x4c)
        expected = {
            0x63690: ("bl", "#0x628e0"),
            0x63694: ("adrp", "x23, #0xde000"),
            0x63698: ("ldrb", "w8, [x23, #0x3c0]"),
            0x636a0: ("adr", "x9, #0x88e40"),
            0x636a4: ("ldr", "w10, [x25, #0x4c4]"),
            0x636a8: ("adrp", "x26, #0xde000"),
            0x636ac: ("add", "x26, x26, #0x594"),
            0x636b0: ("cmp", "w8, #0"),
            0x636b4: ("ldrb", "w8, [x9]"),
            0x636bc: ("ccmp", "w10, #1, #0, eq"),
            0x636c4: ("str", "w0, [x26, #0xc4]"),
            0x636cc: ("and", "w9, w8, #0xfe"),
            0x636d4: ("csel", "w8, w9, w8, eq"),
            0x636d8: ("strb", "w8, [x26]"),
        }
        for address, instruction in expected.items():
            self.assertEqual(code[address], instruction)
        self.assertEqual(0xde594 - 0xde590, 4)
        self.assertEqual(0xde594 + 0xc4 - 0xde590, 0xc8)
        # x25 initially pointed at de000;63028 replaces it before636a4.
        # Requiring the LAST destination assignment prevents the earlier base
        # from incorrectly authorizing a de4c4 snapshot.
        preceding = self.mnld.instructions(0x62e54, 0x636a4 - 0x62e54)
        setters = [(a, op) for a, op in preceding.items() if op[1].startswith("x25,")]
        self.assertEqual(setters, [(0x62e54, ("adrp", "x25, #0xde000")),
                                   (0x63028, ("adrp", "x25, #0x88000"))])
        self.assertEqual(0x88000 + 0x4c4, 0x884c4)
        later = self.mnld.instructions(0x63bd4, 0x20)
        self.assertEqual(self.mnld.instructions(0x63a20, 4)[0x63a20], ("mov", "x24, x25"))
        self.assertEqual(later[0x63bd4], ("ldr", "w8, [x24, #0x4c4]"))
        self.assertEqual(later[0x63bd8], ("cmp", "w8, #1"))
        self.assertEqual(later[0x63bf0], ("bl", "#0x859a0"))
        veneer = self.mnld.instructions(0x859a0, 8)
        self.assertEqual(veneer[0x859a0], ("adrp", "x16, #0x86000"))
        self.assertEqual(veneer[0x859a4], ("ldr", "x17, [x16, #0xe00]"))
        self.assertEqual(self.mnld.imported_symbol(0x86e00), (1026, b"mtk_gps_ofl_ap_config_init"))

    def test_actual_init_consumes_both_fields(self):
        copy = self.lib.instructions(0x52b690, 0x54)
        for address, instruction in {
            0x52b69c: ("mov", "w2, #0x444"),
            0x52b6a0: ("bl", "#0x6e48e0"),
            0x52b6c0: ("ldr", "w8, [x19, #0xc8]"),
            0x52b6cc: ("adrp", "x23, #0x6e7000"),
            0x52b6d0: ("ldr", "x23, [x23, #0x768]"),
            0x52b6d8: ("str", "w8, [x9]"),
            0x52b6e0: ("str", "w8, [x23]"),
        }.items():
            self.assertEqual(copy[address], instruction)
        log = self.lib.instructions(0x52bac8, 0x2c)
        self.assertEqual(log[0x52bac8], ("ldrb", "w8, [x19, #4]"))
        self.assertEqual(log[0x52bacc], ("tbz", "w8, #3, #0x52baf4"))
        self.assertEqual(log[0x52bad0], ("add", "x0, x19, #0x1ea"))
        self.assertEqual(log[0x52bae0], ("bl", "#0x508d10"))

    def test_owner_and_config_source_boundaries(self):
        source = (HERE / "b41_receiver_policy.c").read_text()
        native = (HERE / "b41_receiver_properties.c").read_text()
        self.assertIn('keys[] = {"ro.build.type", "ro.debuggable"}', source)
        self.assertIn("if (owner->entered)", source)
        self.assertIn("++owner->collected", source)
        self.assertIn("owner->first_error = status;", source)
        self.assertIn("b41_startup_set_build_policy(&fragment", source)
        self.assertIn("!s->secondary_policy_de3c0 && s->ap_config_init_884c4 == 1", source)
        self.assertIn("base->provenance[i] && base->bytes[i] != fragment.second[i]", source)
        self.assertIn("result.missing_inputs &= ~B41_SECOND_BUILD_POLICY", source)
        self.assertIn("result.unresolved_bytes += result.provenance[i] == B41_SECOND_UNKNOWN", source)
        self.assertIn("__system_property_get(key, value)", native)
        self.assertIn("return -EOPNOTSUPP;", native)
        for forbidden in ("missing_contracts", "receiver_owner_missing =", "mpe_schema_missing =",
                          "stop_contract_missing =", "dlopen(", "getenv(", "socket(", "ioctl("):
            self.assertNotIn(forbidden, source + native)
        gates = (HERE / "b41_native_arguments.c").read_text()
        self.assertIn("missing |= B41_MISSING_SECOND_POLICY | B41_MISSING_AGPS_RECEIVER;", gates)

    def test_ci_only_runner_and_fixture_coverage(self):
        runner = (HERE / "run_receiver_policy_ci.sh").read_text()
        self.assertIn('"${CI:-}" != true', runner)
        self.assertIn("-fsanitize=address,undefined", runner)
        self.assertIn("--wrap=b41_receiver_property_read", runner)
        self.assertIn("--wrap=__system_property_get", runner)
        self.assertIn('20 "$temporary/test-receiver-policy"', runner)
        bionic = runner[runner.index('elif [ "$#" -eq 2 ]'):]
        self.assertNotIn('"$2"\n', bionic.replace('-o "$2"\n', ''))
        fixture = (HERE / "test_b41_receiver_policy.c").read_text()
        for evidence in ("flags < 256", "UINT32_MAX", "invalid.lengths[0] = SIZE_MAX",
                         "-ESTALE", "-EALREADY", "-EAGAIN", "-EOVERFLOW", "-EBADMSG",
                         "memcmp(&out, &before", "calls == 2", "&again, &p, &s, &again"):
            self.assertIn(evidence, fixture)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_b41_receiver_policy_source.py PINNED_MNLD PINNED_LIBMNL")
    MNLD_PATH, LIB_PATH = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
