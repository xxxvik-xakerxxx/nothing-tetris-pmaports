#!/usr/bin/env python3
"""Pinned LK shared-memory builder with synthetic allocation; no phone access."""
import argparse
import hashlib
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
                                UC_ARM64_REG_X2, UC_ARM64_REG_X3,
                                UC_ARM64_REG_X4, UC_ARM64_REG_SP,
                                UC_ARM64_REG_LR, UC_ARM64_REG_PC)

SHA = "29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f"
STACK, INPUT, OUTPUT, DONE = 0x70000000, 0x71000000, 0x72000000, 0x73000000


def expected(entries, base, md_offset):
    result, cursor = bytearray(), 0
    for ident, offset, size, flags in entries:
        if offset > cursor:
            result += struct.pack("<QQIIIIII", base + cursor, 0, ident, cursor,
                                  offset - cursor, 0, 4, md_offset + cursor)
        result += struct.pack("<QQIIIIII", base + offset, 0, ident, offset,
                              size, 0, flags, md_offset + offset)
        cursor = offset + size
    return bytes(result)


def run(image, entries, base, bank, capacity):
    want = expected(entries, base, bank)
    count = len(want) // 40
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x200000)
    uc.mem_write(0, image[512:][:0x200000])
    for address in (STACK, INPUT, OUTPUT, DONE):
        uc.mem_map(address, 0x10000)
    uc.mem_write(INPUT, b"synthetic_smem\0")
    for index, (ident, offset, size, flags) in enumerate(entries):
        uc.mem_write(INPUT + 0x100 + 32 * index,
                     struct.pack("<IIIIIIII", ident, offset, size, 0, flags, 0, 0, 0))
    calls, stopped = [], []

    def finish(machine, value):
        machine.reg_write(UC_ARM64_REG_X0, value)
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    def code(machine, address, size, context):
        if address == DONE:
            stopped.append(True)
            machine.emu_stop()
        elif address == 0x69248:
            assert machine.reg_read(UC_ARM64_REG_X0) == 1
            assert machine.reg_read(UC_ARM64_REG_X1) == len(want)
            calls.append("table-allocation")
            finish(machine, OUTPUT)
        elif address == 0x238FC:
            assert machine.reg_read(UC_ARM64_REG_X0) == INPUT
            assert machine.reg_read(UC_ARM64_REG_X1) == capacity
            assert machine.reg_read(UC_ARM64_REG_X2) == 0
            calls.append("physical-allocation")
            finish(machine, base)
        elif address == 0x69C28:
            finish(machine, 0)
        else:
            assert 0x235C4 <= address < 0x237F8, hex(address)

    def write(machine, access, address, size, value, context):
        assert (STACK <= address and address + size <= STACK + 0x8000 or
                OUTPUT <= address and address + size <= OUTPUT + len(want)), hex(address)

    uc.hook_add(UC_HOOK_CODE, code)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)
    for reg, value in ((UC_ARM64_REG_SP, STACK + 0x8000), (UC_ARM64_REG_LR, DONE),
                       (UC_ARM64_REG_X0, INPUT), (UC_ARM64_REG_X1, INPUT + 0x100),
                       (UC_ARM64_REG_X2, count), (UC_ARM64_REG_X3, bank),
                       (UC_ARM64_REG_X4, capacity)):
        uc.reg_write(reg, value)
    uc.emu_start(0x235C4, DONE + 4, count=100000)
    assert stopped and calls == ["table-allocation", "physical-allocation"]
    assert uc.reg_read(UC_ARM64_REG_X0) == OUTPUT
    assert bytes(uc.mem_read(OUTPUT, len(want))) == want


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    if hashlib.sha256(image).hexdigest() != SHA:
        raise ValueError("unknown LK image")
    cases = [[(1, 0, 0x1000, 0)],
             [(1, 0, 0x1000, 0), (2, 0x1000, 0x2000, 0x100)],
             [(1, 0x1000, 0x1000, 0), (2, 0x4000, 0x2000, 8)],
             [(1, 0, 0, 0), (2, 0x1000, 0x1000, 0)]]
    for entries in cases:
        for base in (0x88000000, 0x128000000):
            for bank in (0, 0x8000000):
                run(image, entries, base, bank, 0x10000)
    print("PASS: 16 real LK builder scenarios; synthetic allocations; no MMIO")


if __name__ == "__main__":
    main()
