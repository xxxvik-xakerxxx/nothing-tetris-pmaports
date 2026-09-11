#!/usr/bin/env python3
"""Check pinned ATF tag traversal using synthetic buffers and stub consumers."""
from pathlib import Path
import runpy
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X22, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_SP,
)

START, END = 0xb234, 0xb4c8
PARAM, TAGS, STACK, STOP = 0x2000000, 0x2001000, 0x2002000, 0x2003000
COUNT = 0xf65d0
CONSUMERS = {0x19240, 0x4f14, 0x1921c, 0x195a8, 0x19354,
             0x19394, 0x193a8, 0x19328, 0xb1f0, 0xb4c8}


def run(data, headers, expected_offsets, expected_consumers, initial_count=0):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, (len(data) + 4095) & ~4095)
    uc.mem_write(0, data)
    for address in (0xf6000, PARAM, TAGS, STACK, STOP):
        uc.mem_map(address, 4096)
    buffer = bytearray(b"\xa5" * 4096)
    for offset, size, tag in headers:
        struct.pack_into("<II", buffer, offset, size, tag)
    uc.mem_write(TAGS, bytes(buffer))
    uc.mem_write(PARAM, struct.pack("<QQ", TAGS, 4096))
    uc.mem_write(COUNT, struct.pack("<I", initial_count))
    visits, calls = [], []

    def guard(machine, address, size, context):
        if START <= address < END:
            if address == 0xb2a0:
                visits.append(machine.reg_read(UC_ARM64_REG_X22) - TAGS)
            return
        if address == 0x11abc:
            value = PARAM
        elif address in CONSUMERS:
            calls.append((address, machine.reg_read(UC_ARM64_REG_X0) - TAGS))
            value = 0
        else:
            raise AssertionError(f"unexpected execution {address:#x}")
        machine.reg_write(UC_ARM64_REG_X0, value)
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    uc.hook_add(UC_HOOK_CODE, guard)
    uc.reg_write(UC_ARM64_REG_SP, STACK + 4096)
    uc.reg_write(UC_ARM64_REG_LR, STOP)
    uc.emu_start(START, STOP, count=3000)
    assert uc.reg_read(UC_ARM64_REG_PC) == STOP
    assert uc.reg_read(UC_ARM64_REG_SP) == STACK + 4096
    assert uc.reg_read(UC_ARM64_REG_X0) == 0
    assert visits == expected_offsets, (visits, expected_offsets)
    assert calls == expected_consumers, (calls, expected_consumers)
    assert uc.mem_read(TAGS, 4096) == buffer
    assert uc.mem_read(PARAM, 16) == struct.pack("<QQ", TAGS, 4096)
    assert struct.unpack("<I", uc.mem_read(COUNT, 4))[0] == initial_count + len(calls)


def main():
    helper = runpy.run_path(str(Path(__file__).with_name("inspect-bl2-handoff.py")))
    data = helper["extract"](Path(sys.argv[1]).read_bytes(), "atf")
    cases = [
        ([(0, 0, 0)], [0], [], 0),
        ([(0, 0, 0x88610001)], [0], [], 0),
        ([(0, 8, 0x8861ffff), (8, 0, 0)], [0, 8], [], 0),
        ([(0, 12, 0x8861ffff), (12, 0, 0)], [0, 12], [], 0),
        ([(0, 9, 0x8861ffff), (9, 0, 0)], [0, 9], [], 0),
        ([(0, 8, 0x11223344), (8, 0, 0)], [0, 8], [], 0),
        ([(0, 16, 0x88610001), (16, 0, 0)], [0, 16], [(0x19240, 8)], 0),
        ([(0, 12, 0x8861ffff), (12, 16, 0x8861002e), (28, 0, 0)],
         [0, 12, 28], [(0x1921c, 20)], 0),
        ([(0, 8, 0x88610001), (8, 8, 0x88610001), (16, 0, 0)],
         [0, 8], [(0x19240, 8)], 9),
        ([(0, 8, 0x88610001)], [0], [], 10),
    ]
    for headers, visits, consumers, count in cases:
        run(data, headers, visits, consumers, count)
    print(f"PASS: {len(cases)} pinned ATF tag traversal cases")
    print("Byte strides, zero-size stop, payload +8 and consumer cap verified.")
    print("Unknown namespace and unaligned stride are accepted by ATF, not endorsed.")
    print("Consumers are stubbed; no firmware entry, SMC, MMIO or handset access.")


if __name__ == "__main__":
    main()
