#!/usr/bin/env python3
"""Static B4.1 writer census and native-policy evidence; no ELF execution."""
from pathlib import Path
import struct
import sys
import unittest

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from capstone.arm64 import ARM64_OP_REG, ARM64_OP_IMM, ARM64_OP_MEM
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA

HERE = Path(__file__).resolve().parent
TARGETS = {0x88e40: 1, 0xde3c0: 1, 0x884c4: 4}


def relative_slots(image):
    data = image.data
    offset = struct.unpack_from("<Q", data, 40)[0]
    size, count = struct.unpack_from("<HH", data, 58)
    result = {}
    for index in range(count):
        section = struct.unpack_from("<II4QII2Q", data, offset + index * size)
        if section[1] != 4:
            continue
        for entry in range(section[4], section[4] + section[5], section[9]):
            address, info, addend = struct.unpack_from("<QQq", data, entry)
            if info & 0xffffffff == 1027:
                result[address] = addend
    return result


def writer_census(image):
    """Candidate address slicing, NOT execution or a dynamic alias proof.

    Resolve ADR/P, MOV/K, ADD, register copies and relocated GOT loads across
    executable file-backed segments. Account for wide/paired overlapping stores.
    Keep callee-saved constants across calls and alternate return blocks; every
    reported writer is separately pinned below. Indexed/unknown pointer aliases
    are not silently assigned a value. Relative target aliases are also checked.
    """
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    decoder.detail = True
    decoder.skipdata = True
    slots = relative_slots(image)
    result = {target: [] for target in TARGETS}

    def key(register):
        name = decoder.reg_name(register)
        return "x" + name[1:] if name.startswith("w") else name

    for start, size, _, flags in image.loads:
        if not flags & 1:
            continue
        registers = {}
        for instruction in decoder.disasm(image.read(start, size), start):
            if not instruction.id:
                registers.clear()
                continue
            operands = instruction.operands
            value = None
            for operand in operands:
                if operand.type != ARM64_OP_MEM:
                    continue
                base = registers.get(key(operand.mem.base))
                if base is None or operand.mem.index:
                    continue
                address = base + operand.mem.disp
                if instruction.mnemonic.startswith(("str", "stur", "stp", "stnp", "stlr")):
                    name = decoder.reg_name(operands[0].reg)
                    width = 16 if name.startswith("q") else 8 if name.startswith(("x", "d")) else 4
                    if instruction.mnemonic.endswith("b"):
                        width = 1
                    elif instruction.mnemonic.endswith("h"):
                        width = 2
                    if instruction.mnemonic in ("stp", "stnp"):
                        width *= 2
                    for target, length in TARGETS.items():
                        if address < target + length and target < address + width:
                            result[target].append(instruction.address)
                if instruction.mnemonic == "ldr" and decoder.reg_name(operands[0].reg).startswith("x"):
                    value = slots.get(address)
            mnemonic = instruction.mnemonic
            if mnemonic in ("adr", "adrp"):
                value = operands[1].imm
            elif mnemonic == "add" and len(operands) == 3 and operands[2].type == ARM64_OP_IMM:
                base = registers.get(key(operands[1].reg))
                if base is not None:
                    value = base + (operands[2].imm << operands[2].shift.value)
            elif mnemonic == "mov" and len(operands) == 2:
                if operands[1].type == ARM64_OP_REG:
                    value = registers.get(key(operands[1].reg))
                elif operands[1].type == ARM64_OP_IMM:
                    value = operands[1].imm
            elif mnemonic == "movk":
                old = registers.get(key(operands[0].reg))
                shift = operands[1].shift.value
                if old is not None:
                    value = (old & ~(0xffff << shift)) | (operands[1].imm << shift)
            _, writes = instruction.regs_access()
            for register in writes:
                registers.pop(key(register), None)
            if value is not None and operands[0].type == ARM64_OP_REG:
                registers[key(operands[0].reg)] = value
            if mnemonic in ("bl", "blr"):
                for index in range(19):
                    registers.pop("x" + str(index), None)
    return result


class ReceiverInputSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def test_initial_values_and_bss(self):
        self.assertEqual(self.mnld.read(0x88e40, 1), b"\x10")
        self.assertEqual(self.mnld.read(0x884c4, 4), bytes(4))
        # de3c0 is zero-filled by ELF loading, then explicitly rewritten by XML.
        data = self.mnld.data
        offset = struct.unpack_from("<Q", data, 32)[0]
        size, count = struct.unpack_from("<HH", data, 54)
        bss = []
        for index in range(count):
            kind, _, _, address, _, file_size, memory_size, _ = struct.unpack_from(
                "<II6Q", data, offset + index * size)
            if kind == 1 and address + file_size <= 0xde3c0 < address + memory_size:
                bss.append(address)
        self.assertEqual(len(bss), 1)

    def test_all_resolved_store_candidates_and_relocated_aliases(self):
        self.assertEqual(writer_census(self.mnld), {
            0x88e40: [0x78964, 0x78a1c, 0x78acc, 0x78cdc],
            0xde3c0: [0x60afc, 0x60b90],
            0x884c4: [0x63bf8],
        })
        aliases = relative_slots(self.mnld)
        self.assertEqual({slot: value for slot, value in aliases.items() if value in TARGETS},
                         {0x86628: 0xde3c0, 0x86630: 0x88e40})

    def test_log_writer_semantics_and_startup_choices(self):
        expected = {
            0x7890c: ("mov", "w19, w0"),
            0x78960: ("orr", "w9, w9, w19"),
            0x78964: ("strb", "w9, [x8, #0xe40]"),
            0x78a18: ("orr", "w9, w9, #0x11111111"),
            0x78a1c: ("strb", "w9, [x8, #0xe40]"),
            0x78ac8: ("and", "w9, w9, #0xfe"),
            0x78acc: ("strb", "w9, [x8, #0xe40]"),
            0x78cd8: ("orr", "w9, w9, #0x20"),
            0x78cdc: ("strb", "w9, [x8, #0xe40]"),
            0x6365c: ("cbnz", "w10, #0x63678"),
            0x6366c: ("bl", "#0x857b0"),
            0x6367c: ("ldr", "w0, [x8, #0xbc0]"),
            0x63684: ("bl", "#0x78900"),
            0x6368c: ("bl", "#0x78a70"),
            0x63224: ("bl", "#0x78c80"),
            0x7861c: ("bl", "#0x789c0"),
            0x78624: ("bl", "#0x78a70"),
        }
        for address, instruction in expected.items():
            self.assertEqual(self.mnld.instructions(address, 4)[address], instruction)
        path = b"/data/vendor/gps/silentGnssLogging\0"
        self.assertEqual(self.mnld.read(0xdb97, len(path)), path)
        self.assertEqual(self.mnld.read(0x206af, 64).split(b"\0", 1)[0], b"vendor.gpsdbglog.enable")

    def test_mpvt_is_xml_logging_not_secondary_receiver(self):
        self.assertEqual(self.mnld.read(0x2309d, 16), b"MPVT_LOG_ENABLE\0")
        code = self.mnld.instructions(0x60af8, 0x9c)
        for address, instruction in {
            0x60afc: ("strb", "wzr, [x20, #0x3c0]"),
            0x60b3c: ("b.ne", "#0x60b58"),
            0x60b54: ("b.eq", "#0x60b94"),
            0x60b58: ("ldrb", "w8, [sp, #0x3c]"),
            0x60b5c: ("ldur", "d0, [sp, #0x44]"),
            0x60b60: ("cmp", "w8, #1"),
            0x60b6c: ("fcmp", "d0, d1"),
            0x60b74: ("mov", "w8, #1"),
            0x60b84: ("fcmp", "d0, #0.0"),
            0x60b8c: ("mov", "w8, wzr"),
            0x60b90: ("strb", "w8, [x20, #0x3c0]"),
        }.items():
            self.assertEqual(code[address], instruction)
        self.assertEqual(self.mnld.instructions(0x57c88, 4)[0x57c88], ("bl", "#0x60ac0"))

    def test_path_sensitive_ap_config_base(self):
        code = self.mnld.instructions(0x62fe4, 0x48)
        self.assertEqual(code[0x62fec], ("cbz", "w8, #0x63020"))
        self.assertEqual(code[0x62ff0], ("ldr", "w8, [x25, #0x4c4]"))
        self.assertEqual(code[0x6301c], ("b", "#0x63164"))
        self.assertEqual(code[0x63028], ("adrp", "x25, #0x88000"))
        self.assertEqual(self.mnld.instructions(0x62e54, 4)[0x62e54], ("adrp", "x25, #0xde000"))
        self.assertEqual(0xde000 + 0x4c4, 0xde4c4)
        self.assertEqual(0x88000 + 0x4c4, 0x884c4)
        self.assertEqual(self.mnld.instructions(0x63bf8, 4)[0x63bf8], ("str", "wzr, [x24, #0x4c4]"))

    def test_quiet_retains_bit4_and_callback_output(self):
        for address, instruction in {
            0x52bfd4: ("ldrb", "w8, [x19, #4]"),
            0x52bfd8: ("tbnz", "w8, #4, #0x52c004"),
            0x52bfdc: ("mov", "w0, #3"),
            0x52bfe0: ("bl", "#0x5085ec"),
            0x52c05c: ("tbnz", "w1, #4, #0x52c090"),
            0x52c064: ("bl", "#0x52a424"),
            0x52c7c0: ("tbnz", "w8, #4, #0x52c7f8"),
            0x52bacc: ("tbz", "w8, #3, #0x52baf4"),
            0x524d74: ("tbz", "w8, #1, #0x524d8c"),
            0x5249d8: ("tbz", "w8, #2, #0x5249f4"),
            0x52d908: ("and", "w0, w8, #1"),
            0x52ba40: ("add", "x0, x19, #0x1cc"),
        }.items():
            self.assertEqual(self.lib.instructions(address, 4)[address], instruction)
        self.assertEqual(0x10 & 0x0f, 0)

    def test_native_source_does_not_invent_property_or_admission_receipts(self):
        source = (HERE / "b41_receiver_inputs.c").read_text()
        runner = (HERE / "run_receiver_inputs_ci.sh").read_text()
        for required in ("mode != B41_RECEIVER_NATIVE_NMEA_QUIET", "B41_FIRST_TRANSPORT_MODE",
                         "B41_SECOND_RECEIVER_FD", '"UseCallback", 11', "primary > INT32_MAX",
                         "result.log.log_flags_88e40 = 0x10", "result.log.secondary_policy_de3c0 = 0",
                         "result.log.ap_config_init_884c4 = 0", "result.second = *base",
                         "result.second.missing_inputs &= ~B41_SECOND_BUILD_POLICY"):
            self.assertIn(required, source)
        for forbidden in ("b41_receiver_property_owner", "b41_receiver_property_read(",
                          "b41_receiver_properties_collect(", "__system_property_get(",
                          "receiver_owner_missing =", "missing_contracts", "socket(", "ioctl(", "dlopen("):
            self.assertNotIn(forbidden, source)
        self.assertIn('"${CI:-}" != true', runner)
        self.assertIn("-fsanitize=address,undefined", runner)
        self.assertNotIn('"$here/b41_receiver_policy.c"', runner)
        self.assertNotIn('"$here/b41_receiver_properties.c"', runner)
        fixture = (HERE / "test_b41_receiver_inputs.c").read_text()
        for required in ("flags < 256", "UINT32_MAX", "B41_FIRST_TRANSPORT", "-EBADF",
                         "&again.second, &again", "out.second.bytes[0x14] == 42", "memcmp(&out, &before"):
            self.assertIn(required, fixture)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_b41_receiver_inputs_source.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
