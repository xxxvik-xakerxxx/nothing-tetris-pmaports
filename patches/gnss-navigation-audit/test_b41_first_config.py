#!/usr/bin/env python3
"""New first-config producer audit; frozen adapter/harness remain unchanged."""
from pathlib import Path
import json
import struct
import sys
from test_b41_startup import Machine, MNLD_SHA, LIB_SHA, DATA, STACK
from test_b41_startup import UC_ARM64_REG_X29, UC_ARM64_REG_X20
from b41_first_config_contract import report


def defaults(mnld):
    base = 0xde520
    for rate, profile in ((0, 0), (1, 0), (0, 1)):
        m = Machine(mnld, MNLD_SHA, [(0x62b54, 0x62d0c)])
        m.map(0xdd000, 0x4000)
        m.map(0x9b000, 4096)
        m.u.mem_write(base - 1, b"\xa5" * 0x72)
        m.u.mem_write(0xde22c, struct.pack("<I", profile))
        m.u.mem_write(0x88794, struct.pack("<I", rate))
        m.u.mem_write(0xde3c4, b"unknown\0")
        m.u.mem_write(0xde490, bytes(range(16)))
        m.u.mem_write(0x9bc3c, bytes.fromhex("112233445566778899aa"))
        m.mock(0x84f40, lambda a: m.u.mem_write(a[0], bytes([a[1]]) * a[2]) or a[0])
        m.set(UC_ARM64_REG_X29, STACK + 0xe000)
        m.run(0x62b54, 0x62d0c)
        actual = bytes(m.u.mem_read(base, 0x70))
        expected = bytearray(0x70)
        struct.pack_into("<I", expected, 0, 1)
        struct.pack_into("<H", expected, 0x10, 100)
        struct.pack_into("<I", expected, 0x1c, 115200)
        struct.pack_into("<I", expected, 0x20, 1000 if rate else 200)
        expected[0x3c:0x4c] = bytes(range(16))
        if profile:
            expected[0x13] = 0x99
            expected[0x14:0x16] = bytes.fromhex("5566")
            expected[0x18:0x1c] = bytes.fromhex("11223344")
            expected[0x24] = 0xaa
        else:
            expected[0x13] = 255
            struct.pack_into("<H", expected, 0x14, 2000)
            struct.pack_into("<I", expected, 0x18, 26000000)
        assert actual == expected
        assert m.u.mem_read(base - 1, 1) == b"\xa5"
        # The next block is independently zeroed by this same producer.
        assert m.u.mem_read(base + 0x70, 1) == b"\0"
    print("PASS: three first0x70 early-producer vectors; exact untouched/zero/profile extents")


def xml_path(lib):
    m = Machine(lib, LIB_SHA, [(0x51ac8c, 0x51ad6c)])
    def string(pointer):
        return bytes(m.u.mem_read(pointer, 128)).split(b"\0", 1)[0]
    m.mock(0x6e4960, lambda a: len(string(a[0])))
    m.mock(0x6e4a80, lambda a: len(string(a[0])[:a[1]]))
    def copy(a):
        assert a[2] < a[3] == 50
        m.u.mem_write(a[0], string(a[1])[:a[2]])
        return a[0]
    m.mock(0x6e4ec0, copy)
    def append(a):
        existing = string(a[0])
        appended = string(a[1])[:a[2]]
        assert len(existing + appended) < a[3] == 50
        m.u.mem_write(a[0], existing + appended + b"\0")
        return a[0]
    m.mock(0x6e4ba0, append)
    calls = []
    m.mock(0x4ff868, lambda a: calls.append((string(a[1] + 8), a[3])) or 0)
    for directory in (b"/data/vendor/gps/", b"/vendor/etc/"):
        calls.clear()
        m.u.mem_write(DATA, directory + b"\0")
        m.run(0x51ac8c, args=(DATA, DATA + 0x1000))
        assert calls == [(directory + b"MNL_Config.xml", DATA + 0x1000)]
    print("PASS: full libMNL XML path producer; exact data/vendor fallback candidates; parser intercepted")


def clock_and_fd_owner(mnld):
    m = Machine(mnld, MNLD_SHA, [(0x62280, 0x62544)])
    def string(pointer):
        return bytes(m.u.mem_read(pointer, 128)).split(b"\0", 1)[0]
    flags = [0]
    ioctl_calls, property_calls = [], []
    m.mock(0x85880, lambda a: ioctl_calls.append(a[:3]) or flags[0])
    m.mock(0x85820, lambda a: property_calls.append((string(a[0]), string(a[1]))) or 0)
    m.mock(0x84f30, lambda a: 0)
    for flag in (0, 1, 8, 16, 32, 48, 64, 80, 81, 255, 0xffffffff):
        flags[0] = flag
        ioctl_calls.clear()
        property_calls.clear()
        m.u.mem_write(DATA, b"\xa5" * 0x70)
        m.run(0x62280, args=(37, DATA))
        assert ioctl_calls == [(37, 11, 0)]
        assert len(property_calls) == 1
        assert property_calls[0][0] == b"vendor.gps.clock.type"
        assert m.u.mem_read(DATA + 0x13, 1)[0] in (254, 255)
        actual = bytes(m.u.mem_read(DATA, 0x70))
        assert actual[:0x13] == b"\xa5" * 0x13
        assert actual[0x14:0x18] == b"\xa5" * 4
        assert actual[0x1c:] == b"\xa5" * (0x70 - 0x1c)
    # Stock masks failed ioctl to0xff, sets fallback clock policy and returns.
    # This is an observed unsafe continuation, not our constructor contract.
    print("PASS: eleven full clock-policy producer cases; ioctl11/property side effect; negative ioctl is masked by stock")

    m = Machine(mnld, MNLD_SHA, [(0x630c8, 0x630f0)])
    m.map(0x88000, 4096)
    m.set(UC_ARM64_REG_X20, 0x88a80)
    from test_b41_startup import UC_ARM64_REG_X27, UC_ARM64_REG_X28
    m.set(UC_ARM64_REG_X27, 0xffffffff)
    m.set(UC_ARM64_REG_X28, 0x88000)
    m.u.mem_write(0x88a80, b"/dev/explicit-test-receiver\0")
    closes, opens = [], []
    m.mock(0x85380, lambda a: closes.append(a[0]) or 0)
    m.mock(0x85550, lambda a: opens.append((string_in(m, a[0]), a[1])) or 41)
    for old in (0xffffffff, 0, 37):
        closes.clear()
        opens.clear()
        m.u.mem_write(0x88798, struct.pack("<I", old))
        m.run(0x630c8, 0x630f0)
        assert closes == ([37] if old == 37 else [])
        assert opens == [(b"/dev/explicit-test-receiver", 2)]
        assert m.u.mem_read(0x88798, 4) == struct.pack("<I", 41)
    print("PASS: three host-fd owner acquisition slices; O_RDWR, actual returned fd; stock does not close fd0")


def string_in(machine, pointer):
    return bytes(machine.u.mem_read(pointer, 128)).split(b"\0", 1)[0]


if __name__ == "__main__":
    lib, mnld = map(Path, sys.argv[1:])
    defaults(mnld)
    xml_path(lib)
    clock_and_fd_owner(mnld)
    contract = report()
    assert not contract["constructor_ready"]
    assert len(contract["fields"]) == 31
    print(json.dumps({"size": contract["size"], "constructor_ready": False,
                      "missing_inputs": contract["missing_inputs"],
                      "config_xml_paths": contract["config_xml_paths"]}, indent=2))
