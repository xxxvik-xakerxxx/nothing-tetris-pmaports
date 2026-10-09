#!/usr/bin/env python3
"""Pinned event7 and exact abstract-socket transport; intercepted syscalls only."""
from pathlib import Path
import struct
import sys
from unicorn.arm64_const import UC_ARM64_REG_X20, UC_ARM64_REG_X4, UC_ARM64_REG_X5
from test_b41_startup import Machine, MNLD_SHA, DATA, STACK


def transport(path):
    for outcome in (4, 3, -1):
        m = Machine(path, MNLD_SHA, [(0x36b40, 0x36d68)])
        name = b"mnld_gps_control_socket"
        m.u.mem_write(DATA, name + b"\0")
        m.u.mem_write(DATA + 128, b"\3\0\0\0")
        m.u.mem_write(DATA + 256, struct.pack("<I", 5))  # EIO, no OEM retry
        calls = []
        m.mock(0x85350, lambda a: calls.append(("socket", a[:3])) or 41)
        m.mock(0x853a0, lambda a: calls.append(("fcntl", a[:3])) or 0)
        m.mock(0x85210, lambda a: m.u.mem_write(a[0], name + bytes(a[2] - len(name))) or a[0])
        def send(a):
            calls.append(("sendto", a[0], bytes(m.u.mem_read(a[1], a[2])), a[3],
                          bytes(m.u.mem_read(m.u.reg_read(UC_ARM64_REG_X4),
                                            m.u.reg_read(UC_ARM64_REG_X5)))))
            return outcome & 0xffffffffffffffff
        m.mock(0x853b0, send)
        m.mock(0x85380, lambda a: calls.append(("close", a[0])) or 0)
        m.mock(0x85280, lambda a: DATA + 256)
        m.mock(0x85290, lambda a: DATA + 512)
        m.mock(0x84f30, lambda a: 0)
        m.run(0x36b40, args=(DATA, DATA + 128, 4))
        assert calls[0] == ("socket", (1, 2, 0))
        sends = [c for c in calls if c[0] == "sendto"]
        assert sends == [("sendto", 41, b"\3\0\0\0", 0,
                          b"\1\0\0" + name + bytes(110 - 3 - len(name)))]
        assert calls[-1] == ("close", 41)
        assert m.args()[0] & 0xffffffff == outcome & 0xffffffff


def event7(path):
    for policy in (0, 1, 16, 17, 255):
        m = Machine(path, MNLD_SHA, [(0x5df28, 0x5dfb4), (0x35410, 0x35464)])
        m.map(STACK + 0x10000, 0x30000)
        # Callback prologue retains the serialization counter address in X20.
        m.set(UC_ARM64_REG_X20, STACK + 0xf000 + 0x28bf0)
        m.u.mem_write(0x88a55, bytes([policy]))
        m.u.mem_write(DATA + 128, bytes(8))
        captured = []
        m.mock(0x84f40, lambda a: m.u.mem_write(a[0], bytes(a[2])) or a[0])
        def send(a):
            captured.append((bytes(m.u.mem_read(a[0], len(b"mnld_gps_control_socket") + 1)), bytes(m.u.mem_read(a[1], a[2]))))
            return 4
        m.mock(0x36b40, send)
        m.mock(0x85280, lambda a: DATA + 128)
        m.mock(0x85290, lambda a: DATA + 256)
        m.mock(0x84f30, lambda a: 0)
        m.run(0x5df28, 0x5dfb4)
        assert captured == ([] if policy & 16 else [(b"mnld_gps_control_socket\0", b"\3\0\0\0")]), (policy, captured)


if __name__ == "__main__":
    path = Path(sys.argv[1])
    transport(path)
    event7(path)
    print("PASS: pinned control transport 110-byte abstract name and event7 bit4 suppression")
