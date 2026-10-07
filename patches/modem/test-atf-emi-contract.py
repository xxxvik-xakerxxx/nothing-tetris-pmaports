#!/usr/bin/env python3
"""Exercise the pinned ATF EMI handler in emulated RAM/MMIO, never on hardware."""
import argparse
import hashlib
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
    UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_LR, UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
)

SHA = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"
BASE, STACK, STOP = 0x48800000, 0x70000000, 0x70002000
MMIO, OUTPUT = 0x10351000, STACK + 0x1000
ALLOWED = ((0x2f750, 0x2f7e4), (0x2f618, 0x2f69c), (0x10300, 0x103d0),
           (0x2d61c, 0x2d670), (0x2f510, 0x2f618), (0x2f428, 0x2f464),
           (0x5aa8, 0x5adc), (0x2d9c4, 0x2da20), (0x4f28, 0x4fcc))
REGS = (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
        UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5)


def extract(path):
    with path.open("rb") as stream:
        data = stream.read(512 + 900240 + 1)
    if len(data) != 512 + 900240:
        raise ValueError("expected only the ATF header and declared payload")
    if struct.unpack_from("<II", data) != (0x58881688, 900240):
        raise ValueError("unexpected ATF container header")
    if hashlib.sha256(data[512:]).hexdigest() != SHA:
        raise ValueError("unrecognized ATF payload; re-audit before use")
    return data[512:]


class Handler:
    def __init__(self, data):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(BASE, 0x100000)
        self.uc.mem_write(BASE, data)
        self.uc.mem_map(STACK, 0x3000)
        self.uc.mem_map(MMIO, 0x1000)
        self.writes = []
        self.uc.hook_add(UC_HOOK_CODE, self.guard)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.record)

    def guard(self, uc, address, size, context):
        if not any(start <= address - BASE < end for start, end in ALLOWED):
            raise RuntimeError(f"unmodeled code {address - BASE:#x}")

    def record(self, uc, access, address, size, value, context):
        if MMIO <= address < MMIO + 0x1000:
            self.writes.append((address, size, value))
        elif not (STACK <= address and address + size <= STACK + 0x2000 or
                  BASE + 0xf7a25 <= address < BASE + 0xf7a65 and size == 1):
            raise RuntimeError(f"unmodeled write {address:#x}")

    def call(self, op, a=0, b=0, slot=0):
        self.writes.clear()
        for reg, value in zip(REGS, (op, a, b, slot, 0, OUTPUT)):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM64_REG_SP, STACK + 0x1000)
        self.uc.reg_write(UC_ARM64_REG_LR, STOP)
        self.uc.emu_start(BASE + 0x2f750, STOP, count=1024)
        assert self.uc.reg_read(UC_ARM64_REG_PC) == STOP, "instruction budget exhausted"
        assert self.uc.reg_read(UC_ARM64_REG_SP) == STACK + 0x1000
        return self.uc.reg_read(UC_ARM64_REG_X0)


def check(data):
    h = Handler(data)
    count = 0
    for slot in range(32, 44):
        start, end = 0x80000000 + (slot - 32) * 0x200000, 0x80200000 + (slot - 32) * 0x200000
        enable = MMIO + 0x2a4 + ((slot - 1) // 32) * 4
        enabled = struct.unpack("<I", h.uc.mem_read(enable, 4))[0]
        assert h.call(0, start >> 12, end >> 12, slot) == 0
        assert h.writes == [
            (MMIO + (slot - 1) * 8, 4, (start - 0x40000000) >> 12),
            (MMIO + (slot - 1) * 8 + 4, 4, ((end - 0x40000000) >> 12) | 0x80000000),
            (enable, 4, enabled | (1 << ((slot - 1) % 32))),
        ]
        assert h.call(2, 0, slot) == start and not h.writes
        # The getter shifts the raw end register, including its bit-31 marker.
        assert h.call(2, 1, slot) == end + (1 << 43) and not h.writes
        assert h.call(2, 3, slot) == 1 and not h.writes
        before = bytes(h.uc.mem_read(MMIO, 0x1000))
        assert h.call(0, start >> 12, end >> 12, slot) == 2**64 - 4
        assert not h.writes and bytes(h.uc.mem_read(MMIO, 0x1000)) == before
        count += 1
    for slot in range(32, 44):
        for start in (0x40000000, 0x120000000, 0x83fffe000):
            h = Handler(data)
            assert h.call(0, start >> 12, (start + 4096) >> 12, slot) == 0
            assert h.call(2, 0, slot) == start
            assert h.call(2, 1, slot) == (start + 4096) | (1 << 43)
            count += 1
    for start, end, slot in ((0x3ffff, 0x80000, 32), (0x80000, 0x7ffff, 32),
                              (0x80000, 0x81000, 0), (0x80000, 0x81000, 64)):
        h = Handler(data)
        assert h.call(0, start, end, slot) == 2**64 - 3 and not h.writes
        assert h.call(0, 0x80000, 0x81000, 32) == 0
        count += 1
    # Demonstrate why callers must reject truncation rather than rely on ATF.
    h = Handler(data)
    assert h.call(0, 0x1080000, 0x1081000, 32) == 0
    assert h.call(2, 0, 32) == 0x80000000
    count += 1
    for slot, preset in ((32, 0), (40, 4), (41, 3)):
        h = Handler(data)
        assert h.call(6, slot, preset) == 2**64 - 4 and not h.writes
        count += 1
    presets = (((35, 2), (47, 2)), ((35, 3), (47, 3), (93, 3)),
               ((35, 3), (47, 2), (93, 2)), ((35, 2), (47, 3), (93, 3)))
    for preset, expected in enumerate(presets):
        for existing in (0, 0xffffffff):
            h = Handler(data)
            # Synthetic selector read window, not a model of real domain state.
            h.uc.mem_write(MMIO + 0x9ec, struct.pack("<I", existing))
            assert h.call(6, 40, preset) == 0
            selectors = [value for addr, _, value in h.writes if addr == MMIO + 0x9bc]
            assert selectors == [domain for domain, _ in expected]
            updates = [value for addr, _, value in h.writes if addr == MMIO + 0x9cc]
            assert updates == [value for _, permission in expected
                               for value in (existing, existing | (permission << 14))]
            commits = [value for addr, _, value in h.writes if addr == MMIO + 0x800]
            assert commits == [1] * len(expected)
            count += 1
    print(f"PASS: {count} pinned ATF EMI scenarios; bounds, readback, one-shot state")
    print("Raw end readback includes bit 43; oversized page input is truncated")
    print("Preset writes preserve existing permission bits (OR), not replacement")
    print("No hardware access; physical permissions and endpoint semantics remain untested")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    check(extract(args.image))


if __name__ == "__main__":
    main()
