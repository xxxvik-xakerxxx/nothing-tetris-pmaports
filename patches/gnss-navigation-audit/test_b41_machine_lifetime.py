#!/usr/bin/env python3
"""Mapping fragmentation and deterministic hook lifetime regression; no engine."""
import gc
from pathlib import Path
import sys
import weakref
from test_b41_startup import Machine, LIB_SHA, STOP


def mapping_runs():
    class Memory:
        def __init__(self):
            self.calls = []
        def mem_map(self, address, size):
            self.calls.append((address, size))
    m = Machine.__new__(Machine)
    m.u, m.pages = Memory(), set()
    m.map(1, 0x6000)
    assert m.u.calls == [(0, 0x7000)]
    m.map(0x2000, 0x2000)
    assert len(m.u.calls) == 1
    m.map(0x9000, 0x1000)
    m.map(0x5000, 0x7000)
    assert m.u.calls[2:] == [(0x7000, 0x2000), (0xa000, 0x2000)]
    assert len(m.pages) == 12


def lifetimes(path):
    enabled = gc.isenabled()
    gc.disable()  # Cleanup must not wait for the cyclic collector's thresholds.
    try:
        for case in range(32):
            try:
                with Machine(path, LIB_SHA, []) as m:
                    ref = weakref.ref(m.u)
                    # Exercise the same capturing mock cycle as XML/producer code.
                    m.mock(STOP + 4, lambda a, owner=m: owner.args()[0])
                    if case & 1:
                        raise ValueError("intentional fixture failure")
            except ValueError as error:
                assert str(error) == "intentional fixture failure"
            assert m.u is None and not m.hooks and not m.pages
            assert ref() is None, "Uc retained after public hook_del/drop with GC disabled"
            m.close()  # Idempotent, including the exception path.
    finally:
        if enabled:
            gc.enable()


if __name__ == "__main__":
    mapping_runs()
    lifetimes(Path(sys.argv[1]))
    print("PASS: coalesced overlap mappings; 32 Uc lifetimes with GC disabled, normal/error cleanup")
