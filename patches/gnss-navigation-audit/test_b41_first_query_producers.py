#!/usr/bin/env python3
"""Execute pinned mnld query slices offline; no real ioctl/device/engine calls."""
from pathlib import Path
import struct
import sys
from test_b41_startup import Machine, MNLD_SHA, DATA, STACK
from test_b41_startup import UC_ARM64_REG_X20


def platform_clock(mnld):
    for result in (0, 1, 0xffffffff):
        m = Machine(mnld, MNLD_SHA, [(0x632e0, 0x6332c)])
        m.map(0x88000, 4096)
        m.u.mem_write(0x88798, struct.pack("<I", 37))
        m.set(UC_ARM64_REG_X20, 0x88000)
        calls = []
        m.mock(0x85880, lambda a: calls.append(a[:3]) or result)
        m.mock(0x84f30, lambda a: 0)
        m.run(0x632e0, 0x6332c)
        assert calls == [(37, 30, 0)]
        # Stock stores even an error for the subsequent AGPS131 producer.
        assert bytes(m.u.mem_read(STACK + 0xf090, 4)) == struct.pack("<I", result)
    print("PASS: ioctl30 return selector stored at sp+90; no output pointer; stock error retained")


def modem_status(mnld):
    for status, override, expected in ((0, 0xffffffff, 0x12345678),
                                        (0, 9, 9), (0xffffffff, 9, 0xffffffff)):
        m = Machine(mnld, MNLD_SHA, [(0x5dcc0, 0x5ddc0)])
        m.map(0x88000, 4096)
        m.u.mem_write(0x88798, struct.pack("<I", 37))
        m.u.mem_write(0x88c74, struct.pack("<I", override))
        calls = []
        def ioctl(args):
            assert args[0:2] == (37, 21) and args[2] != 0
            calls.append(args[:3])
            m.u.mem_write(args[2], struct.pack("<I", 0x12345678))
            return status
        m.mock(0x85880, ioctl)
        m.mock(0x84f30, lambda a: 0)
        m.run(0x5dcc0, args=(DATA,))
        assert len(calls) == 1
        assert bytes(m.u.mem_read(DATA, 4)) == struct.pack("<I", expected)
    print("PASS: ioctl21 actual output versus explicit override; failed query produces -1, not override")


def lna_output(mnld):
    for status in (0, 0xffffffff):
        m = Machine(mnld, MNLD_SHA, [(0x6344c, 0x6349c)])
        m.map(0x88000, 4096)
        m.map(0xde000, 4096)
        m.u.mem_write(0x88798, struct.pack("<I", 37))
        m.u.mem_write(STACK + 0xf094, struct.pack("<I", 0xa5a5a5a5))
        calls = []
        def ioctl(args):
            assert args[:2] == (37, 16) and args[2] == STACK + 0xf094
            calls.append(args[:3])
            if status == 0:
                m.u.mem_write(args[2], struct.pack("<I", 23))
            return status
        m.mock(0x85880, ioctl)
        m.mock(0x84f30, lambda a: 0)
        m.run(0x6344c, 0x6349c)
        assert len(calls) == 1
        expected = 23 if status == 0 else 0xa5a5a5a5
        assert bytes(m.u.mem_read(0xde574, 4)) == struct.pack("<I", expected)
    print("PASS: ioctl16 pointer output; failed stock query copies stale stack bytes to first+54")


if __name__ == "__main__":
    path = Path(sys.argv[1])
    platform_clock(path)
    modem_status(path)
    lna_output(path)
