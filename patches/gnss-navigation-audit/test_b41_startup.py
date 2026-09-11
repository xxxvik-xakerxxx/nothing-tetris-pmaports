#!/usr/bin/env python3
"""Bounded pinned ARM64 slices; no native ELF loading, devices or solver."""
import hashlib
from pathlib import Path
import struct
import sys
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *

LIB_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
MNLD_SHA = "285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83"
DATA, STACK, TLS, STOP, GLOBALS = 0x2000000, 0x2100000, 0x2200000, 0x2300000, 0x3000000
REGS = [UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3]


class Machine:
    def __init__(self, path, sha, ranges):
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError("wrong binary SHA256")
        self.u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.pages, self.hooks, self.ranges = set(), {}, ranges
        with path.open("rb") as f:
            elf = ELFFile(f)
            for seg in elf.iter_segments():
                if seg["p_type"] == "PT_LOAD" and seg["p_filesz"]:
                    self.map(seg["p_vaddr"], seg["p_filesz"])
                    self.u.mem_write(seg["p_vaddr"], seg.data())
        for start, size in ((DATA, 0x10000), (STACK, 0x10000), (TLS, 4096),
                            (STOP, 4096), (GLOBALS, 0x60000), (0x6e6000, 0x3000)):
            self.map(start, size)
        # Synthetic global storage: unique backing for each GOT slot.
        for got in range(0x6e6000, 0x6e9000, 8):
            self.q(got, self.global_at(got))
        self.u.hook_add(UC_HOOK_CODE, self.hook)
        self.set(UC_ARM64_REG_TPIDR_EL0, TLS)

    @staticmethod
    def global_at(got):
        return GLOBALS + (got - 0x6e6000) * 16

    def map(self, address, size):
        for page in range(address & ~4095, (address + size + 4095) & ~4095, 4096):
            if page not in self.pages:
                self.u.mem_map(page, 4096)
                self.pages.add(page)

    def set(self, reg, value):
        self.u.reg_write(reg, value)

    def q(self, address, value):
        self.u.mem_write(address, struct.pack("<Q", value))

    def args(self):
        return tuple(self.u.reg_read(r) for r in REGS)

    def hook(self, uc, address, size, _):
        if address in self.hooks:
            uc.reg_write(UC_ARM64_REG_X0, self.hooks[address](self.args()))
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
        elif not any(a <= address < b for a, b in self.ranges):
            raise RuntimeError(f"unreviewed execution {address:#x}")

    def mock(self, address, fn):
        self.map(address, 4)
        self.hooks[address] = fn

    def run(self, start, end=STOP, args=()):
        self.map(end, 4)
        self.set(UC_ARM64_REG_SP, STACK + 0xf000)
        self.set(UC_ARM64_REG_LR, STOP)
        for reg, val in zip(REGS, args):
            self.set(reg, val)
        self.u.emu_start(start, end, count=10000)
        assert self.u.reg_read(UC_ARM64_REG_PC) == end, "instruction budget exhausted"


def registration(lib):
    m = Machine(lib, LIB_SHA, [(0x52f9d0, 0x52fbb0)])
    for missing in [None] + list(range(24)):
        values = [STOP + 0x100 + 4 * i if i != missing else 0 for i in range(24)]
        m.u.mem_write(DATA, struct.pack("<24Q", *values))
        m.run(0x52f9d0, args=(DATA,))
        required = missing is not None and missing < 10 and bool(0x3fb & (1 << missing))
        assert m.args()[0] == (0xffffffff if required else 0)
        # Even failure changes globals; a pure preflight must precede this call.
        assert struct.unpack("<Q", m.u.mem_read(m.global_at(0x6e6800), 8))[0] == values[1]
    m.run(0x52f9d0, args=(0,))
    assert m.args()[0] == 0xffffffff
    print("PASS: registration full/null/24 missing-slot cases; required mask0x3fb; nontransactional stores")


def agps(lib):
    m = Machine(lib, LIB_SHA, [(0x6b17b0, 0x6b1a34)])
    allocations, queues, frees = [], [], []
    m.mock(0x651668, lambda a: allocations.append(a[0]) or DATA)
    m.mock(0x5214b0, lambda a: 0)
    m.mock(0x651500, lambda a: queues.append(a[0]) or 0)
    m.mock(0x6512b4, lambda a: frees.append(a[0]) or 0)
    m.mock(0x6e48e0, lambda a: m.u.mem_write(a[0], bytes(m.u.mem_read(a[1], a[2]))) or a[0])
    m.mock(0x6b1710, lambda a: 0)  # Diagnostic formatter only.
    m.mock(0x6e4a80, lambda a: 0)
    m.q(m.global_at(0x6e6800), STOP + 4)
    m.mock(STOP + 4, lambda a: 0)
    for command, src, subtype, length in ((38, 1, 18, 0), (37, 6, 4, 16)):
        m.u.mem_write(DATA, b"\xa5" * 64)
        payload = bytes(range(length))
        m.u.mem_write(DATA + 128, payload or b"\0")
        m.run(0x6b17b0, args=(command, DATA + 128 if length else 0, src, 4))
        assert m.args()[0] == 0 and allocations[-1] == length + 10
        assert bytes(m.u.mem_read(DATA, 8 + length)) == struct.pack("<4H", src, 4, subtype, length) + payload
        assert bytes(m.u.mem_read(DATA + 8 + length, 2)) == b"\xa5\xa5"
        assert queues[-1] == DATA
    m.mock(0x651500, lambda a: 0xffffffff)
    m.run(0x6b17b0, args=(38, 0, 1, 4))
    assert m.args()[0] == 0xffffffff and frees == [DATA]
    count = len(queues)
    m.mock(0x651668, lambda a: 0)
    m.run(0x6b17b0, args=(38, 0, 1, 4))
    assert m.args()[0] == 0xffffffff and len(queues) == count
    print("PASS: AGPS37/38 headers/copy, uninitialized allocation tail, queue/allocation failure")

    # Subtype18 reaches the active assistance FSM, not the DSP sender.
    m = Machine(lib, LIB_SHA, [(0x6b1fdc, 0x6b20c4)])
    m.mock(0x50c1d8, lambda a: 0)
    for subtype in (17, 18):
        m.u.mem_write(DATA, struct.pack("<4H", 1, 4, subtype, 0))
        for got, value in ((0x6e8890, 2), (0x6e8888, 1), (0x6e8880, 7)):
            m.u.mem_write(m.global_at(got), bytes([value]))
        m.run(0x6b1fdc, args=(DATA,))
        assert m.args()[0] == (0xffffffff if subtype == 18 else 0)
        assert m.u.mem_read(m.global_at(0x6e8888), 1)[0] == (0 if subtype == 18 else 1)
    print("PASS: active assistance mode2/subtype18 clears assistance state; subtype17 does not")


def postinit(lib, mnld):
    m = Machine(mnld, MNLD_SHA, [(0x643e4, 0x64644)])
    m.map(0x9a000, 0x3000)
    m.map(0xdd000, 0x4000)
    calls = []
    m.mock(0x85700, lambda a: calls.append(a[:2]) or 0)
    m.mock(0x84f30, lambda a: 0)
    m.mock(0x62550, lambda a: 0)
    for enabled in (0, 1):
        calls.clear()
        m.set(UC_ARM64_REG_X19, 2 if enabled else 0)
        m.set(UC_ARM64_REG_X21, 0xddd98)
        m.u.mem_write(0x9a933, bytes([enabled]))
        m.u.mem_write(0xde484, struct.pack("<I", enabled))
        m.run(0x643e4, 0x64644)
        expected = [59, 73] + ([60] if enabled else []) + [74, 104] + ([126] if enabled else []) + [121, 133] + ([135] if enabled else []) + [131]
        assert [a[0] for a in calls] == expected
    params = [59, 73, 60, 74, 104, 126, 121, 133, 135, 131]
    contracts = {59: (1026, 1), 73: (1030, 1), 60: (1029, 1),
                 74: (1031, 1), 104: (314, 1), 126: (1077, 4),
                 121: (1072, 4), 133: (1082, 8), 131: (1080, 4)}
    l = Machine(lib, LIB_SHA, [(0x50fda0, 0x51036c), (0x510408, 0x51040c)])
    l.mock(0x6e4910, lambda a: 0)
    l.mock(0x50c1d8, lambda a: 0)
    for p in params:
        l.set(UC_ARM64_REG_X19, p)
        l.run(0x50fda0, 0x510408 if p == 135 else 0x51036c)
        if p == 135:
            assert l.args()[0] == 0xffffffff
            print("PASS: mnld param135 rejected by ordinary libmnl table bounds (before return -1)")
        else:
            assert (l.u.reg_read(UC_ARM64_REG_X24),
                    l.u.reg_read(UC_ARM64_REG_X25)) == contracts[p]
            print(f"PASS: param{p} -> message{l.u.reg_read(UC_ARM64_REG_X24)}, length{l.u.reg_read(UC_ARM64_REG_X25)}")


def nmea(lib):
    m = Machine(lib, LIB_SHA, [(0x5249b8, 0x5249f4), (0x524a30, 0x524ac8)])
    calls = []
    m.mock(0x52188c, lambda a: 0)
    m.mock(0x521770, lambda a: calls.append(("fd", a[1], a[2])) or 0)
    for got, address, name in ((0x6e77c8, STOP + 4, "mnld"), (0x6e6800, STOP + 8, "app")):
        m.q(m.global_at(got), address)
        m.mock(address, lambda a, name=name: calls.append((name, a[0], a[1])) or 0xffffffff)
    config = m.global_at(0x6e69d0)
    m.set(UC_ARM64_REG_X26, config)
    m.set(UC_ARM64_REG_X19, DATA)
    m.set(UC_ARM64_REG_X20, 5)
    m.u.mem_write(DATA, b"$GN\0x")
    for marker, first in ((b"UseCallback", "mnld"), (b"NotCallback", "fd")):
        calls.clear()
        m.u.mem_write(config + 0x1cc, marker)
        m.run(0x5249b8, 0x5249f4)
        assert calls == [(first, DATA, 5), ("app", DATA, 5)]
    print("PASS: UseCallback route vs fd; borrowed pointer + w1 length; return values ignored in slice")


if __name__ == "__main__":
    lib, mnld = map(Path, sys.argv[1:])
    registration(lib)
    agps(lib)
    postinit(lib, mnld)
    nmea(lib)
    print("OFFLINE ONLY: mocked globals/endpoints, no complete init, firmware, receiver or solver")
