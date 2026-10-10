#!/usr/bin/env python3
"""Exact selector0/1 pointer/parameter routing, no service or engine executed."""
from pathlib import Path
import sys
from test_b41_startup import Machine, MNLD_SHA, DATA


def check(path):
    with Machine(path, MNLD_SHA, [(0x5fa80, 0x5feb0)]) as m:
        m.u.mem_write(0x88bf4, (1).to_bytes(4, "little"))
        calls = []
        m.mock(0x39490, lambda a: calls.append((150, a[0])) or 0)
        m.mock(0x39540, lambda a: calls.append((152, None)) or 0)
        m.mock(0x84f30, lambda a: 0)
        for selector in (0, 0x10000):
            for parameter in (0, 0x10000, 1, 0xffff0001, 0xffffffff):
                for pointer in (0, DATA):
                    calls.clear()
                    m.run(0x5fa80, args=(selector, parameter, pointer))
                    assert calls == ([(150, pointer)] if parameter & 0xffff else [])
                    assert m.args()[0] == 0
        for selector in (1, 0x10001):
            for parameter in (0, 1, 0xffffffff):
                calls.clear()
                m.run(0x5fa80, args=(selector, parameter, 1))
                assert calls == [(152, None)] and m.args()[0] == 0
        m.u.mem_write(0x88bf4, bytes(4))
        for selector in (0, 1):
            calls.clear()
            m.run(0x5fa80, args=(selector, 1, DATA))
            assert not calls and m.args()[0] == 0xffffffff
    print("PASS: 26 active low16 selector/parameter routes + 2 receiver-off refusals")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_b41_slot6_string_producer.py PINNED_MNLD")
    check(Path(sys.argv[1]))
