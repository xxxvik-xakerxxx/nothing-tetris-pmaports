#!/usr/bin/env python3
"""Exact pinned AGPS sender producers with intercepted send; no native engine."""
from pathlib import Path
import struct
import sys
from test_b41_startup import Machine, MNLD_SHA, DATA, STACK


def packets(path):
    vectors = (None, b"", b"$PMTK738,1*00\r", b"$PMTK736,1,-1*00\r\n", b"A" * 1024)
    for payload in vectors:
        m = Machine(path, MNLD_SHA, [(0x39490, 0x39538), (0x35410, 0x35464), (0x35630, 0x35728)])
        m.map(STACK - 0x20000, 0x20000)
        if payload is not None:
            m.u.mem_write(DATA, payload + b"\0")
        m.mock(0x84f40, lambda a: m.u.mem_write(a[0], bytes(a[2])) or a[0])
        m.mock(0x85250, lambda a: len(payload))
        m.mock(0x85240, lambda a: m.u.mem_write(a[0], bytes(m.u.mem_read(a[1], a[2]))) or a[0])
        captured = []
        m.mock(0x380a0, lambda a: captured.append(bytes(m.u.mem_read(a[0], a[1]))) or 0)
        m.run(0x39490, args=(0 if payload is None else DATA,))
        expected = struct.pack("<II", 1, 150)
        expected += b"\0" if payload is None else b"\1" + struct.pack("<I", len(payload) + 1) + payload + b"\0"
        assert captured == [expected]
    m = Machine(path, MNLD_SHA, [(0x39540, 0x395c8), (0x35410, 0x35464)])
    m.map(STACK - 0x20000, 0x20000)
    m.mock(0x84f40, lambda a: m.u.mem_write(a[0], bytes(a[2])) or a[0])
    captured = []
    m.mock(0x380a0, lambda a: captured.append(bytes(m.u.mem_read(a[0], a[1]))) or 0xffffffff)
    m.run(0x39540)
    assert captured == [struct.pack("<II", 1, 152)]
    assert m.args()[0] == 0xffffffff
    print("PASS: 5 exact optional-string150 envelopes and selector1/type152; send failure retained")


if __name__ == "__main__":
    packets(Path(sys.argv[1]))
