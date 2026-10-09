#!/usr/bin/env python3
"""Pinned producer initialization and conditional consumer, no engine/device IO."""
from pathlib import Path
import struct
import sys
from test_b41_startup import Machine, MNLD_SHA, LIB_SHA, DATA, STACK
from unicorn.arm64_const import UC_ARM64_REG_X20, UC_ARM64_REG_X22, UC_ARM64_REG_X26, UC_ARM64_REG_W8
from unicorn import UC_HOOK_MEM_READ


def producer(mnld):
    for status, expected in ((0, 23), (0xffffffff, 0)):
        m = Machine(mnld, MNLD_SHA, [(0x62bac, 0x62bd0), (0x6344c, 0x6349c)])
        m.map(0x88000, 4096)
        m.map(0xde000, 4096)
        m.set(UC_ARM64_REG_X20, DATA)
        # Poison first: prove that the real producer initializes the output.
        m.u.mem_write(STACK + 0xf094, b"\xa5" * 4)
        m.run(0x62bac, 0x62bd0)
        assert bytes(m.u.mem_read(STACK + 0xf094, 4)) == bytes(4)
        m.u.mem_write(0x88798, struct.pack("<I", 37))
        calls = []
        def ioctl(args):
            assert args[:3] == (37, 16, STACK + 0xf094)
            calls.append(args[:3])
            if status == 0:
                m.u.mem_write(args[2], struct.pack("<I", 23))
            return status
        m.mock(0x85880, ioctl)
        m.mock(0x84f30, lambda a: 0)
        m.run(0x6344c, 0x6349c)
        assert len(calls) == 1
        assert bytes(m.u.mem_read(0xde574, 4)) == struct.pack("<I", expected)
    print("PASS: mnld62bcc initializes ioctl16 output0; unsupported untouched output retains0")


def consumer(lib):
    # w8=config+30 chip identity; w9=family table entry. MT6878 maps to5.
    for chip, family, reads_pin, mode in ((0xffff6878, 5, True, 10),
                                         (0xffff6739, 2, False, 73),
                                         (0xffff6632, 5, False, 73),
                                         (0xffff6771, 3, True, 8)):
        for word in (0, 143, 0x12345678):
            m = Machine(lib, LIB_SHA, [(0x4f29e0, 0x4f2a48)])
            m.set(UC_ARM64_REG_X26, DATA)
            m.set(UC_ARM64_REG_X22, DATA + 128)
            m.set(UC_ARM64_REG_W8, chip)
            m.u.mem_write(DATA + 128, bytes([family]))
            m.u.mem_write(DATA + 0x54, struct.pack("<I", word))
            reads = []
            m.u.hook_add(UC_HOOK_MEM_READ,
                lambda uc, access, address, size, value, _: reads.append((address, size)))
            m.run(0x4f29e0, 0x4f2a48)
            assert ((DATA + 0x54, 4) in reads) == reads_pin
            expected = (word & 255) if reads_pin else 72
            assert bytes(m.u.mem_read(STACK + 0xf712, 1)) == bytes([expected])
            # strb of mode at4f2a48 is outside the bounded run; inspect W11.
            from unicorn.arm64_const import UC_ARM64_REG_W11
            assert m.u.reg_read(UC_ARM64_REG_W11) == mode
    # Real table, not a caller-supplied synthetic MT6878 family guess.
    # Obtain actual file-backed GOT/table bytes, not Machine's synthetic globals.
    from elftools.elf.elffile import ELFFile
    with lib.open("rb") as stream:
        elf = ELFFile(stream)
        def read(address, size):
            for segment in elf.iter_segments():
                if segment["p_type"] == "PT_LOAD" and segment["p_vaddr"] <= address and address + size <= segment["p_vaddr"] + segment["p_filesz"]:
                    offset = address - segment["p_vaddr"]
                    return segment.data()[offset:offset + size]
            raise ValueError("table address outside file-backed ELF")
        table = struct.unpack("<Q", read(0x6e7b00, 8))[0]
        assert table == 0x6ee1a8
        rows = struct.iter_unpack("<II", read(table, 400))
        assert [(family, chip) for family, chip in rows if chip == 0xffff6878] == [(5, 0xffff6878)]
    print("PASS: MT6878 family5 consumes lowbyte first+54; zero is retained OEM value, NOT unused field")


if __name__ == "__main__":
    producer(Path(sys.argv[1]))
    consumer(Path(sys.argv[2]))
