#!/usr/bin/env python3
"""Pinned init argument-copy slice only; never enters engine initialization."""
from pathlib import Path
import sys
from unicorn.arm64_const import UC_ARM64_REG_X22
from test_b41_startup import Machine, LIB_SHA, DATA


def verify(path):
    # Start after init's prologue and stop before any configuration consumers,
    # globals/state transitions, optional callbacks, or device/runtime services.
    with Machine(path, LIB_SHA, [(0x52b670, 0x52b6a4)]) as m:
        first_source, second_source = DATA, DATA + 0x1000
        first_target = m.global_at(0x6e6710)
        second_target = m.global_at(0x6e69d0)
        first = bytes((i * 17 + 3) & 255 for i in range(0x70))
        second = bytes((i * 29 + 7) & 255 for i in range(0x444))
        calls = []

        def copy(args):
            destination, source, size, _ = args
            assert (destination, source, size) == (second_target, second_source, 0x444)
            calls.append((destination, source, size))
            m.u.mem_write(destination, bytes(m.u.mem_read(source, size)))
            return destination

        m.mock(0x6e48e0, copy)
        for source, payload in ((first_source, first), (second_source, second)):
            m.u.mem_write(source, payload + b"\x91" * 16)
        for target, size in ((first_target, 0x70), (second_target, 0x444)):
            m.u.mem_write(target - 16, b"\xa5" * (size + 32))
        m.set(UC_ARM64_REG_X22, first_target)
        m.run(0x52b670, 0x52b6a4, args=(first_source, second_source))
        assert len(calls) == 1
        for target, payload in ((first_target, first), (second_target, second)):
            assert bytes(m.u.mem_read(target, len(payload))) == payload
            assert bytes(m.u.mem_read(target - 16, 16)) == b"\xa5" * 16
            assert bytes(m.u.mem_read(target + len(payload), 16)) == b"\xa5" * 16
        # The observed copy is owned storage, not borrowed source retention.
        # This proves ONLY this slice; no inference about later consumers.
        m.u.mem_write(first_source, bytes(0x70))
        m.u.mem_write(second_source, bytes(0x444))
        assert bytes(m.u.mem_read(first_target, 0x70)) == first
        assert bytes(m.u.mem_read(second_target, 0x444)) == second
    print("PASS: pinned init copy 0x70/0x444; exact bounds, distinct destinations, source independence")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
