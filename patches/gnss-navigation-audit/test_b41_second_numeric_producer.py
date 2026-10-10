#!/usr/bin/env python3
"""Pinned buffer producer and float-format ABI; external format intercepted."""
from pathlib import Path
import struct
import sys
from unicorn.arm64_const import UC_ARM64_REG_X26, UC_ARM64_REG_D0
from test_b41_startup import Machine, MNLD_SHA, DATA


def check(path):
    with Machine(path, MNLD_SHA, [(0x63828, 0x638c4)]) as m:
        m.map(0xde000, 0x2000)
        m.mock(0x85000, lambda a: 0)  # Separate identity-path producer.
        def format_value(a):
            assert a[:2] == (DATA + 0x28, 30)
            assert bytes(m.u.mem_read(a[2], 5)) == b"%.1f\0"
            assert struct.unpack("<d", struct.pack("<Q", m.u.reg_read(UC_ARM64_REG_D0)))[0] == 1.5
            m.u.mem_write(a[0], b"1.5\0")
            return 3
        m.mock(0x37ff0, format_value)
        for primary in (0, 0xfffff, 0x100000, 0x3000000, 0xffffffff):
            for secondary in (0, 1, 0xffffffff):
                m.u.mem_write(DATA, bytes(0x444))
                m.u.mem_write(0xdfff4, struct.pack("<II", primary, secondary))
                m.u.mem_write(0xde4bc, struct.pack("<f", 1.5))
                m.set(UC_ARM64_REG_X26, DATA + 4)  #636a8/ac: de594=second+4.
                m.run(0x63828, 0x638c4)
                expected_primary = 0x1900000 if primary < 0x100000 else min(primary, 0x3000000)
                floor = 0x12c00000 if primary < 0x100000 else 12 * min(primary, 0x3000000)
                assert struct.unpack("<II", m.u.mem_read(DATA + 0x1c, 8)) == (
                    expected_primary, min(max(secondary, floor), 0x20000000))
    print("PASS:15 pinned buffer boundary vectors; binary32->double %.1f/30-byte ABI")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_b41_second_numeric_producer.py PINNED_MNLD")
    check(Path(sys.argv[1]))
