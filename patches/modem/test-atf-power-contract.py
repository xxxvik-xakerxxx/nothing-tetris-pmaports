#!/usr/bin/env python3
"""Execute pinned CCCI power handlers against synthetic MMIO, never a phone."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from unicorn import (Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE,
                     UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
                                UC_ARM64_REG_X2, UC_ARM64_REG_X3,
                                UC_ARM64_REG_X4, UC_ARM64_REG_X5,
                                UC_ARM64_REG_SP, UC_ARM64_REG_LR,
                                UC_ARM64_REG_PC)

SHA = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"
BASE, STACK, STOP = 0x48800000, 0x70000000, 0x7000f000
OUTPUT = STACK + 0x9000
FLAGS = 0x1040d834
BOOT = 0x21b20300
SELECTOR, STATUS = 0x1020e700, 0x1020e300
PAGES = (0x10001000, 0x1040d000, 0x21b20000, 0x1020e000, 0x20400000)
ALLOWED = ((0xbe28, 0xbf2c), (0xbf2c, 0xbfd8),
           (0x1bf84, 0x1c090), (0x1bf50, 0x1bf60),
           (0xb598, 0xb718), (0x1a1b4, 0x1a25c), (0x100f8, 0x10128))


def extract(path):
    data = path.read_bytes()
    if len(data) != 900752 or struct.unpack_from("<II", data) != (0x58881688, 900240):
        raise ValueError("expected only pinned ATF container and declared payload")
    data = data[512:]
    if hashlib.sha256(data).hexdigest() != SHA:
        raise ValueError("unknown ATF: re-audit all offsets before execution")
    entries = [struct.unpack_from("<QIIQQ", data, off)
               for off in range(0x58a20, 0x59540, 32)]
    for fid, handler in ((0xc200040b, 0xbe28), (0xc2000505, 0xbf2c)):
        found = [entry for entry in entries if entry[2] == fid]
        if len(found) != 1 or found[0][0] != BASE + handler:
            raise ValueError("CCCI SIP registration mismatch")
    return data


class Handler:
    def __init__(self, data, flags=(0, 0, 0, 0)):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(BASE, 0x100000)
        self.uc.mem_write(BASE, data)
        self.uc.mem_map(STACK, 0x10000)
        for page in PAGES:
            self.uc.mem_map(page, 0x1000)
        self.uc.mem_write(FLAGS, struct.pack("<4I", *flags))
        self.uc.mem_write(BOOT, struct.pack("<I", 0x55))
        self.uc.mem_write(0x100018a8, struct.pack("<2I", 0x80, 0x40))
        self.uc.mem_write(0x20400504, struct.pack("<2I", 0x12345678, 0xabcdef01))
        self.uc.mem_write(STATUS, struct.pack("<I", 0x87654321))
        self.reads, self.writes = [], []
        self.uc.hook_add(UC_HOOK_CODE, self.code)
        self.uc.hook_add(UC_HOOK_MEM_READ, self.read)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.write)

    def code(self, uc, address, size, context):
        if address == BASE + 0x3a608:
            # Logging only, not power/reset helpers or MMIO.
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
            return
        if not any(start <= address - BASE < end for start, end in ALLOWED):
            raise AssertionError(f"unexpected instruction {address - BASE:#x}")

    def read(self, uc, access, address, size, value, context):
        if any(page <= address and address + size <= page + 0x1000 for page in PAGES):
            self.reads.append((address, size))

    def write(self, uc, access, address, size, value, context):
        if any(page <= address and address + size <= page + 0x1000 for page in PAGES):
            self.writes.append((address, size, value))
        elif not (STACK <= address and address + size <= STACK + 0xa000):
            raise AssertionError(f"unexpected write {address:#x}/{size}")

    def call(self, kernel, command, argument=0):
        self.reads.clear()
        self.writes.clear()
        self.uc.mem_write(OUTPUT, b"\xa5" * 24)
        for reg, value in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1,
                               UC_ARM64_REG_X2, UC_ARM64_REG_X3,
                               UC_ARM64_REG_X4, UC_ARM64_REG_X5),
                              (6, command, argument, 0, 0, OUTPUT)):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM64_REG_SP, STACK + 0x8000)
        self.uc.reg_write(UC_ARM64_REG_LR, STOP)
        self.uc.emu_start(BASE + (0xbf2c if kernel else 0xbe28), STOP, count=1024)
        assert self.uc.reg_read(UC_ARM64_REG_PC) == STOP, "instruction budget exceeded"
        assert self.uc.reg_read(UC_ARM64_REG_SP) == STACK + 0x8000
        return (self.uc.reg_read(UC_ARM64_REG_X0),
                struct.unpack("<3Q", self.uc.mem_read(OUTPUT, 24)))


def check(data):
    cases = 0
    sentinel = 0xa5a5a5a5a5a5a5a5
    for flags in itertools.product((0, 1, 2, 0xffffffff), repeat=4):
        h = Handler(data, flags)
        ret, out = h.call(True, 2)
        assert (ret, out) == (flags[0], flags[1:])
        assert not h.writes and h.reads == [(FLAGS + 4*i, 4) for i in range(4)]
        ret, out = h.call(True, 3)
        assert (ret, out) == (int(flags != (1, 1, 1, 1)), flags[1:])
        assert not h.writes and h.reads == [(FLAGS + 4*i, 4) for i in range(4)]
        cases += 2
    for argument in (0, 1, 2, 0xffffffff, 0x100000000, 0xffffffffffffffff):
        h = Handler(data)
        ret, out = h.call(False, 5, argument)
        assert ret == 0
        if argument <= 1:
            assert out == (sentinel, sentinel, argument)
            assert h.writes == [(BOOT, 4, argument)] and h.reads == [(BOOT, 4)]
        else:
            assert out == (sentinel,) * 3 and not h.writes and not h.reads
        cases += 1
    h = Handler(data)
    ret, out = h.call(False, 1)
    assert ret == 0 and out == (sentinel, sentinel, 1)
    assert h.writes == [(0x100018ac, 4, 0x41), (0x100018a8, 4, 0x81), (BOOT, 4, 1)]
    h = Handler(data)
    ret, out = h.call(True, 0)
    assert (ret, out) == (0, (0x12345678, 0xabcdef01, 1))
    assert h.writes == [(BOOT, 4, 1)]
    for kernel, command in ((False, 7), (True, 4)):
        h = Handler(data, (1, 2, 3, 4))
        ret, out = h.call(kernel, command)
        assert ret == 0
        assert h.writes == [(SELECTOR, 4, 2), (SELECTOR, 4, 3)]
        if kernel:
            assert out == (0x87654321, 0x87654321, sentinel)
        else:
            assert out == (0x8765432187654321, 0x100000002, 0x300000004)
        cases += 1
    for kernel in (False, True):
        h = Handler(data)
        assert h.call(kernel, 8) == (0, (sentinel,) * 3)
        assert not h.writes and not h.reads
        cases += 1
    for argument in (0, 1, 2, 0xffffffffffffffff):
        h = Handler(data)
        ret, out = h.call(False, 6, argument)
        assert out == (sentinel,) * 3
        if argument == 1:
            assert ret == 1 and h.writes == [(0x2040040c, 4, 0x5500),
                                             (0x20400404, 4, 0),
                                             (0x20400408, 4, 1)]
        else:
            assert ret == (0 if argument == 0 else 0xffff)
            assert not h.writes
        assert not h.reads
        cases += 1
    for kernel, commands in ((False, (0, 2, 3, 4, 9)),
                             (True, (1, 5, 6, 7, 9))):
        for command in commands:
            h = Handler(data)
            assert h.call(kernel, command) == (
                0xfffffff2 if kernel else 0xfffffff3, (sentinel,) * 3)
            assert not h.writes and not h.reads
            cases += 1
    print(json.dumps({"result": "PASS", "cases": cases + 2, "sha256": SHA,
                      "scope": "real inner handlers; synthetic MMIO; no outer-stage admission",
                      "pure_queries": ["kernel POWER/2 flags", "kernel POWER/3 done"],
                      "not_reset_proof": "LK POWER/5 writes boot enable, invalid argument silently succeeds",
                      "mutating_queries": ["LK POWER/7", "kernel POWER/4"],
                      "noop": "POWER/8 in both interfaces"}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    check(extract(args.image))


if __name__ == "__main__":
    main()
