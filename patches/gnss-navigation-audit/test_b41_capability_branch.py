#!/usr/bin/env python3
"""Pinned matcher/profile source: no native library or hardware calls."""
from pathlib import Path
import sys
from test_b41_startup import Machine, LIB_SHA, DATA


def check(path):
    with Machine(path, LIB_SHA, [(0x51b31c, 0x51b488)]) as m:
        m.q(0x6e6ff8, 0x6edd50)
        def string(pointer):
            return bytes(m.u.mem_read(pointer, 92)).split(b"\0", 1)[0]
        m.mock(0x6e4960, lambda a: len(string(a[0])))
        m.mock(0x6e4ee0, lambda a: int(string(a[0]) == string(a[1])))
        m.mock(0x6e4ef0, lambda a: int(string(a[0]) == string(a[1])))
        m.mock(0x525df8, lambda a: 0)
        for adie, index, address in ((b"0x6631", 21, 0x6ed7d0),
                                     (b"0x6637", 22, 0x6ed960),
                                     (b"0x6686", 23, 0x6edaf0)):
            identity = bytearray(0xc0)
            identity[:7] = b"0x6878\0"
            identity[0x5c:0x63] = adie + b"\0"
            m.u.mem_write(DATA, bytes(identity))
            m.run(0x51b31c, args=(DATA,))
            assert m.args()[0] == index
            capability = bytes(m.u.mem_read(address, 0xd0))
            assert capability[0xcc] == 1
            print(adie.decode(), "index", index, "property branch", capability[0xcc])
        identity[0x5c:0x63] = b"0x0000\0"
        m.u.mem_write(DATA, bytes(identity))
        m.run(0x51b31c, args=(DATA,))
        assert m.args()[0] == 0xffffffff
    print("PASS: 3 exact MT6878 matches, all property branch1; unknown Adie refused")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_b41_capability_branch.py PINNED_LIBMNL")
    check(Path(sys.argv[1]))
