#!/usr/bin/env python3
"""Pinned stop-record acknowledgement; no real thread/signal/engine calls."""
from pathlib import Path
import struct
import sys
from test_b41_startup import Machine, LIB_SHA, DATA


def verify(path):
    for index, offload, result in ((0, 0, 0), (0, 0, 22), (14, 1, 0), (16, 1, 0)):
        with Machine(path, LIB_SHA, [(0x529f18, 0x52a2f4)]) as m:
            m.map(0x6fa000, 4096)
            m.u.mem_write(m.global_at(0x6e6d00), struct.pack("<I", offload))
            m.u.mem_write(m.global_at(0x6e7768), bytes(4))
            m.u.mem_write(DATA, struct.pack("<IIQQQ", 7, index, 1234, 0x529f18, 0x529418))
            calls = []
            m.mock(0x6e52b0, lambda a: calls.append(("signal", a[:2])) or 0)
            m.mock(0x529e04, lambda a: calls.append(("join", a)) or result)
            m.mock(0x6e4910, lambda a: 0)
            m.mock(0x6e4990, lambda a: DATA + 128)
            m.mock(0x6e4b60, lambda a: DATA + 256)
            m.run(0x529f18, args=(DATA,))
            marker = struct.unpack("<i", bytes(m.u.mem_read(DATA, 4)))[0]
            if offload:
                assert not calls and marker == -1  # Counterexample to bare-marker readiness.
            else:
                assert calls[0] == ("signal", (1234, 10))
                assert calls[1][0] == "join" and calls[1][1][0] == 1234 and calls[1][1][2] == 1
                assert marker == (-1 if result == 0 else 7)
                assert m.args()[0] & 0xffffffff == (0 if result == 0 else 0xffffffff)
    print("PASS: primary join success/failure markers; offload14/16 skipped-join counterexamples")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
