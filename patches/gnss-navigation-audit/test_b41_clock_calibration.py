#!/usr/bin/env python3
"""Pinned16-byte clock calibration source selection; no real files/devices."""
from pathlib import Path
import sys
from test_b41_startup import Machine, MNLD_SHA

EL6N = b"/mnt/vendor/nvdata/md/NVRAM/CALIBRAT/EL6N_000"
ML4A = b"/mnt/vendor/nvdata/md/NVRAM/CALIBRAT/ML4A_000"


def audit(path):
    for chip, expected_path, expected_offset in (
            ("0x6735", EL6N, 160), ("0x0321", EL6N, 160),
            ("0x0335", EL6N, 160), ("0x0337", EL6N, 160),
            ("0x6893", ML4A, 64), ("0x6855", ML4A, 64),
            ("0x6789", ML4A, 64), ("0x6878", ML4A, 160),
            ("unknown", ML4A, 160)):
        for count in (16, 7):
            m = Machine(path, MNLD_SHA, [(0x56d00, 0x57184)])
            m.map(0xdd000, 0x4000)
            m.u.mem_write(0xde3bc, b"\0")  # Explicit legacy NV-reader branch.
            m.u.mem_write(0xde3c4, chip.encode() + b"\0")
            m.u.mem_write(0xde490, b"\xa5" * 16)
            calls = []
            def string(pointer):
                return bytes(m.u.mem_read(pointer, 128)).split(b"\0", 1)[0]
            m.mock(0x84f30, lambda a: 0)
            m.mock(0x85550, lambda a: calls.append(("open", string(a[0]), a[1])) or 37)
            m.mock(0x857f0, lambda a: calls.append(("seek", *a[:3])) or a[1])
            def read(a):
                assert a[:3] == (37, 0xde490, 16)
                calls.append(("read", *a[:3]))
                m.u.mem_write(a[1], bytes(range(count)))
                return count
            m.mock(0x85690, read)
            m.mock(0x85380, lambda a: calls.append(("close", a[0])) or 0)
            m.run(0x56d00)
            assert calls == [("open", expected_path, 0), ("seek", 37, expected_offset, 0),
                             ("read", 37, 0xde490, 16), ("close", 37)]
            assert m.u.mem_read(0xde490, 16) == bytes(range(count)) + b"\xa5" * (16 - count)
    print("PASS: eighteen calibration producer cases; exact NV path/offset/16-byte request/close")
    print("SHORT READ: stock retains stale bytes; a native constructor must reject incomplete16-byte input")
    print("OFFLINE ONLY: synthetic chip IDs/NV bytes; no per-device calibration read or committed")


if __name__ == "__main__":
    audit(Path(sys.argv[1]))
