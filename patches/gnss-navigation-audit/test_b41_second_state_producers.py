#!/usr/bin/env python3
"""Pinned second-config fd/MPE state producers, not native initialization."""
from pathlib import Path
import struct
import sys
from test_b41_startup import Machine, MNLD_SHA, DATA
from unicorn.arm64_const import UC_ARM64_REG_X20, UC_ARM64_REG_X25


def descriptors(path):
    for secondary in (0, 1, 2, 3):
        m = Machine(path, MNLD_SHA, [(0x63af4, 0x63b18)])
        m.map(0x88000, 4096)
        m.map(0xde000, 4096)
        m.u.mem_write(0x88798, struct.pack("<II", 37, 38))
        # Real initial zero from mnld62ba8, not a fabricated inactive -1.
        m.u.mem_write(0xde590, bytes(0x444))
        m.set(UC_ARM64_REG_X25, 0xde5a0)
        m.mock(0x56ce0, lambda a: secondary)
        m.run(0x63af4, 0x63b18)
        assert bytes(m.u.mem_read(0xde5a0, 8)) == struct.pack("<II", 37, 38 if secondary & 1 else 0)
    print("PASS: second+10 primary fd and bit0-conditional +14 secondary; inactive value0")


def state_copy(path):
    state = bytes(range(68))
    for requested in (0, 1, 9):
        for backend in (0, 1, 2, 3, 0xffffffff):
            m = Machine(path, MNLD_SHA, [(0x639c0, 0x63a08)])
            m.map(0xde000, 4096)
            m.set(UC_ARM64_REG_X20, 0xde5fc)
            m.u.mem_write(0xde4d4, state)
            m.u.mem_write(0xde228, struct.pack("<I", requested))
            m.u.mem_write(0xde5fc, b"\xa5" * 72)
            m.mock(0x56c70, lambda a: backend)
            m.run(0x639c0, 0x63a08)
            assert bytes(m.u.mem_read(0xde600, 68)) == state
            assert bytes(m.u.mem_read(0xde5fc, 1)) == bytes([(bool(requested) & backend)])
            assert bytes(m.u.mem_read(0xde5fd, 3)) == b"\xa5" * 3
    print("PASS: exact copied68-byte MPE state; boolean request AND backend bit0; padding untouched")


if __name__ == "__main__":
    descriptors(Path(sys.argv[1]))
    state_copy(Path(sys.argv[1]))
