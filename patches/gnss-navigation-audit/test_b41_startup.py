#!/usr/bin/env python3
"""Bounded pinned ARM64 slices; no native ELF loading, devices or solver."""
import hashlib
import gc
from pathlib import Path
import struct
import sys
import weakref
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
        # Do not retain Machine through Uc -> ctypes callback -> bound method.
        owner = weakref.ref(self)
        def dispatch(uc, address, size, user_data):
            machine = owner()
            if machine is None:
                raise RuntimeError("orphaned emulation hook")
            machine.hook(uc, address, size, user_data)
        self.code_hook = self.u.hook_add(UC_HOOK_CODE, dispatch)
        self.set(UC_ARM64_REG_TPIDR_EL0, TLS)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def close(self):
        """Detach callbacks before dropping Uc, using public binding APIs only."""
        if self.u is None:
            return
        self.u.hook_del(self.code_hook)
        self.hooks.clear()  # Mock closures may capture this Machine.
        self.u = None
        self.pages.clear()
        # Bindings also retain internal ctypes/Uc cycles after hook deletion.
        # Collect at this explicit ownership boundary, not after N test cases.
        gc.collect()

    @staticmethod
    def global_at(got):
        return GLOBALS + (got - 0x6e6000) * 16

    def map(self, address, size):
        # A mapping per page exhausts old QEMU physical-section tables even for
        # a single ELF. Map contiguous missing runs, preserving overlap handling.
        end = (address + size + 4095) & ~4095
        run = None
        for page in range(address & ~4095, end + 4096, 4096):
            missing = page < end and page not in self.pages
            if missing and run is None:
                run = page
            elif not missing and run is not None:
                self.u.mem_map(run, page - run)
                self.pages.update(range(run, page, 4096))
                run = None

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
        for slot, got in ((3, 0x6e6d30), (4, 0x6e6d28)):
            assert struct.unpack("<Q", m.u.mem_read(m.global_at(got), 8))[0] == values[slot]
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


def frame_callbacks(lib, mnld):
    m = Machine(mnld, MNLD_SHA, [(0x7ba50, 0x7bbb0), (0x7bbc0, 0x7bd14)])
    def string(p, bound=64):
        raw = bytes(m.u.mem_read(p, bound))
        assert b"\0" in raw
        return raw.split(b"\0", 1)[0]
    def format_call(a):
        fmt = string(a[2])
        v4 = m.u.reg_read(UC_ARM64_REG_X4)
        if fmt == b"PMTK%d,%d":
            out = fmt % (a[3], v4)
        elif fmt == b"PMTK%d,0,0":
            out = fmt % a[3]
        else:
            assert fmt == b"$%s*%02X\r\n"
            out = fmt % (string(a[3]), v4)
        assert len(out) < 64
        m.u.mem_write(a[0], out + b"\0")
        return len(out)
    def copy(a):
        assert a[2] <= a[3] == 64
        m.u.mem_write(a[0], bytes(m.u.mem_read(a[1], a[2])))
        return a[0]
    sent = []
    m.mock(0x7b9a0, format_call)  # Only the three pinned format strings above.
    m.mock(0x853c0, lambda a: len(string(a[0], a[1])))
    m.mock(0x85000, copy)
    m.mock(0x84f30, lambda a: 0)
    m.mock(0x5fa80, lambda a: sent.append((a[0], bytes(m.u.mem_read(a[2], a[1])))) or 0xffffffff)
    vectors = []
    for address, values in ((0x7ba50, list(range(256)) + [256, 257, 0xffffffff]),
                            (0x7bbc0, [0, 1, 0xffffffff])):
        for value in values:
            sent.clear()
            m.run(address, args=(value, DATA, 0x1234, 0x5678))
            body = (f"PMTK738,{value & 255}" if address == 0x7ba50 else "PMTK736,0,0").encode()
            checksum = 0
            for byte in body:
                checksum ^= byte
            expected = b"$" + body + f"*{checksum:02X}\r".encode()
            assert sent == [(0, expected)] and m.args()[0] == 0
            vectors.append(expected.hex())
    print("PASS: slots3/4 full mnld bodies; 262 cases; CR without LF; IPC failure masked by return0")
    # Independently exercise the library veneers, including the overwritten x0
    # on the no-argument slot4 route. No callback executes in this machine.
    l = Machine(lib, LIB_SHA, [(0x50903c, 0x50904c), (0x509054, 0x509064)])
    for start, got in ((0x509054, 0x6e6d30), (0x50903c, 0x6e6d28)):
        observed = []
        l.q(l.global_at(got), STOP + 4)
        l.mock(STOP + 4, lambda a: observed.append(a[0]) or 0xfffffffe)
        l.run(start, args=(257,))
        assert observed == [257 if start == 0x509054 else STOP + 4]
        assert l.args()[0] == 0xfffffffe
    print("PASS: libmnl slot3 w0 preserved, slot4 x0 overwritten by target; return propagated")
    print("FRAME_VECTOR_SHA256=" + hashlib.sha256("\n".join(vectors).encode()).hexdigest())


def config_producer(mnld, lib):
    base = 0xde590
    m = Machine(mnld, MNLD_SHA, [(0x62b70, 0x62bac), (0x6352c, 0x6365c),
                                (0x63694, 0x638a0), (0x6397c, 0x63a08),
                                (0x63af4, 0x63b18)])
    m.map(0xdd000, 0x4000)
    m.mock(0x84f40, lambda a: m.u.mem_write(a[0], bytes([a[1]]) * a[2]) or a[0])
    m.mock(0x84f30, lambda a: 0)
    copies = []
    def copy(a):
        src_bound = m.u.reg_read(UC_ARM64_REG_X4)
        raw = bytes(m.u.mem_read(a[1], src_bound))
        assert b"\0" in raw and a[2] < a[3]
        raw = raw.split(b"\0", 1)[0][:a[2]].ljust(a[2], b"\0")
        m.u.mem_write(a[0], raw)
        copies.append((a[0] - base, a[1], a[2]))
        return a[0]
    m.mock(0x85000, copy)
    m.u.mem_write(base - 1, b"\xa5" * (0x444 + 2))
    m.set(UC_ARM64_REG_X20, 0xde520)
    m.set(UC_ARM64_REG_X29, STACK + 0xe000)
    m.run(0x62b70, 0x62bac)
    assert bytes(m.u.mem_read(base, 0x444)) == bytes(0x444)
    # 62ba4 clears first-block +0x68..0x6f, ending immediately before base.
    assert m.u.mem_read(base - 1, 1)[0] == 0
    assert m.u.mem_read(base + 0x444, 1)[0] == 0xa5
    m.run(0x6352c, 0x6365c)
    assert (0x1cc, 0x88ac0, 29) in copies
    assert bytes(m.u.mem_read(base + 0x1cc, 30)) == b"UseCallback" + bytes(19)
    assert [c[0] for c in copies] == [0xd4, 0xf2, 0x1ea, 0x1cc, 0x190, 0x406, 0x424, 0x208]
    # A non-default source proves producer copying, not a hard-coded marker.
    m.u.mem_write(0x88ac0, b"CustomOutput\0")
    m.run(0x6352c, 0x6365c)
    assert bytes(m.u.mem_read(base + 0x1cc, 13)) == b"CustomOutput\0"
    m.set(UC_ARM64_REG_X25, 0xde000)
    m.run(0x63694, 0x638a0, args=(0x12345678,))
    assert struct.unpack("<I", m.u.mem_read(base + 0xc8, 4))[0] == 0x12345678
    assert [c[0] for c in copies[-12:]] == [0x110, 0x226, 0x256, 0x286, 0x2b6, 0x2e6, 0x316, 0x346, 0x376, 0x3a6, 0x3d6, 0x46]
    m.mock(0x56c70, lambda a: 1)
    m.run(0x6397c, 0x63a08)
    assert bytes(m.u.mem_read(base + 0xcc, 8)) == struct.pack("<4H", 0xce, 6, 0xaa55, 0x102)
    m.u.mem_write(0x88798, struct.pack("<2I", 37, 41))
    for secondary in (1, 0):
        m.mock(0x56ce0, lambda a, secondary=secondary: secondary)
        m.u.mem_write(base + 0x14, struct.pack("<I", 0xffffffff))
        m.set(UC_ARM64_REG_X25, base + 0x10)
        m.run(0x63af4, 0x63b18)
        assert bytes(m.u.mem_read(base + 0x10, 8)) == struct.pack("<2I", 37, 41 if secondary else 0xffffffff)
    print("PASS: config zero extent/guards, paths, marker producer override, magic, conditional fd fields")
    l = Machine(lib, LIB_SHA, [(0x52b638, 0x52b6a4)])
    copied = []
    def memcpy(a):
        copied.append(a[:3])
        l.u.mem_write(a[0], bytes(l.u.mem_read(a[1], a[2])))
        return a[0]
    l.mock(0x6e48e0, memcpy)
    first = bytes(range(0x70))
    second = bytes(m.u.mem_read(base, 0x444))
    l.u.mem_write(DATA, first)
    l.u.mem_write(DATA + 0x100, second)
    destination = l.global_at(0x6e69d0)
    l.u.mem_write(destination - 1, b"\xa5" * (0x444 + 2))
    l.run(0x52b638, 0x52b6a4, args=(DATA, DATA + 0x100))
    assert copied == [(destination, DATA + 0x100, 0x444)]
    assert bytes(l.u.mem_read(destination, 0x444)) == second
    assert bytes(l.u.mem_read(l.global_at(0x6e6710), 0x70)) == first
    assert l.u.mem_read(destination - 1, 1)[0] == l.u.mem_read(destination + 0x444, 1)[0] == 0xa5
    print("PASS: actual libmnl entry copies distinct 0x70/0x444 inputs without crossing guards; stops before init")


def build_policy(mnld):
    m = Machine(mnld, MNLD_SHA, [(0x628e0, 0x62a10)])
    properties = {}
    reads = []
    def property_get(a):
        name = bytes(m.u.mem_read(a[0], 32)).split(b"\0", 1)[0].decode()
        assert name in ("ro.build.type", "ro.debuggable") and a[2] == 0
        reads.append(name)
        value = properties[name].encode()
        m.u.mem_write(a[1], value + b"\0")
        return len(value)
    m.mock(0x85530, property_get)
    m.mock(0x84f30, lambda a: 0)  # Diagnostic formatting, not policy.
    for kind, debug, expected in (("user", "0", 0), ("user", "1", 0),
                                  ("eng", "1", 1), ("userdebug", "1", 2),
                                  ("eng", "0", -1), ("userdebug", "0", -1),
                                  ("eng", "10", -1), ("unknown", "1", -1),
                                  ("", "", -1)):
        reads.clear()
        properties.update({"ro.build.type": kind, "ro.debuggable": debug})
        m.run(0x628e0)
        assert m.args()[0] == expected & 0xffffffff
        assert reads == ["ro.build.type", "ro.debuggable"]
    print("PASS: full628e0 build policy producer; nine property vectors; offsetc8 is not GNSS mode")


def mandatory_callbacks(mnld, lib):
    with mnld.open("rb") as stream:
        elf = ELFFile(stream)
        relocations = {r["r_offset"]: r["r_addend"]
                       for r in elf.get_section_by_name(".rela.dyn").iter_relocations()}
    expected = (0x5de00, 0x7b240, 0x7b3f0, 0x7ba50, 0x7bbc0,
                0x7b850, 0x5fa80, 0x5d910, 0x5d920, 0x5d930)
    assert tuple(relocations[0x88cb8 + i * 8] for i in range(10)) == expected
    print("PASS: pinned mnld registration table RELATIVE producers0..9")

    m = Machine(mnld, MNLD_SHA, [(0x5d910, 0x5d934), (0x84c6c, 0x84e8c)])
    for count in (0, 1, 7, 8, 15, 16, 31, 32, 33, 63, 256):
        for operation in (0, 1):
            for overlap in (False, True):
                src, dst = DATA, DATA + (1 if overlap else 0x1000)
                initial = bytes(range(256)) * 32
                m.u.mem_write(DATA, initial)
                result = bytearray(initial)
                for i in range(count):
                    value = result[i]
                    result[dst - DATA + i] = (((value ^ 0x63) << 2) |
                                              ((value ^ 0x63) >> 6)) & 255 if operation else \
                                             (((value >> 2) | (value << 6)) ^ 0x63) & 255
                # Producer wrappers8/9 tail-call helpers with asymmetric operands.
                m.run(0x5d930 if operation else 0x5d920,
                      args=(dst, src, count) if operation else (src, dst, count))
                assert m.args()[0] == count
                assert bytes(m.u.mem_read(DATA, len(initial))) == bytes(result)
    print("PASS: slots8/9 full scalar/SIMD bodies;44 length/direction/overlap vectors")
    for value in (0, 1, 0x80000000, 0xffffffff):
        m.run(0x5d910, args=(value,))
        assert m.args()[0] == value
    l = Machine(lib, LIB_SHA, [(0x509064, 0x509074)])
    l.q(l.global_at(0x6e6d38), STOP + 4)
    l.mock(STOP + 4, lambda a: a[0])
    l.run(0x509064, args=(0x80000000,))
    assert l.args()[0] == 0x80000000
    print("PASS: slot7 RET preserves input; libmnl veneer preserves w0; consumer542008 passes fcvtzs w0")

    m = Machine(mnld, MNLD_SHA, [(0x7b850, 0x7b990)])
    def string(p, bound=64):
        raw = bytes(m.u.mem_read(p, bound))
        assert b"\0" in raw
        return raw.split(b"\0", 1)[0]
    def formatter(a):
        fmt = string(a[2])
        value = m.u.reg_read(UC_ARM64_REG_X4) & 0xffffffff
        if fmt == b"PMTK%d,1,%d":
            assert a[3] == 736
            out = fmt % (a[3], value if value < 0x80000000 else value - 0x100000000)
        else:
            assert fmt == b"$%s*%02X\r\n"
            out = fmt % (string(a[3]), value)
        assert len(out) < 64
        m.u.mem_write(a[0], out + b"\0")
        return len(out)
    m.mock(0x7b9a0, formatter)
    def copy(a):
        raw = string(a[1])[:a[2]].ljust(a[2], b"\0")
        assert a[2] < a[3] == 64
        m.u.mem_write(a[0], raw)
        return a[0]
    m.mock(0x85000, copy)
    m.mock(0x853c0, lambda a: len(string(a[0], a[1])))
    sent = []
    m.mock(0x5fa80, lambda a: sent.append((a[0], bytes(m.u.mem_read(a[2], a[1])))) or 0xffffffff)
    for value in (0, 1, 255, 256, 0x7fffffff, 0x80000000, 0xffffffff):
        sent.clear()
        m.run(0x7b850, args=(value,))
        body = f"PMTK736,1,{value if value < 0x80000000 else value - 0x100000000}".encode()
        checksum = 0
        for byte in body:
            checksum ^= byte
        assert sent == [(0, b"$" + body + f"*{checksum:02X}\r\n".encode())]
        assert m.args()[0] == 0
    print("PASS: slot5 full callback; seven signed32 vectors; CRLF retained; vendor masks dispatch failure")

    m = Machine(mnld, MNLD_SHA, [(0x5de00, 0x5de60), (0x5f9e8, 0x5fa24)])
    m.map(STACK - 0x50000, 0x60000)
    for event in (1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 14, 0xffffffff):
        m.run(0x5de00, args=(event,))
        assert m.args()[0] == 0
    for event, target in ((0, 0x5de60), (3, 0x5dfd8), (7, 0x5df28), (13, 0x5e0c0)):
        m.run(0x5de00, target, args=(event,))
    print("PASS: slot0 twelve genuine no-action selectors; four active targets identified, NOT executed")

    m = Machine(mnld, MNLD_SHA, [(0x7b240, 0x7b3c4)])
    m.map(0x89000, 4096)
    m.u.mem_write(0x89264, bytes(4))  # Explicit diagnostic-disabled state.
    m.run(0x7b240, args=(DATA, 5))
    assert m.args()[0] == 0
    print("PASS: slot1 diagnostic-disabled producer returns0; pointer/length consumer already tested")

    m = Machine(mnld, MNLD_SHA, [(0x5fa80, 0x5feb0)])
    m.u.mem_write(0x88bf4, bytes(4))  # Explicit receiver-off state, not ELF default.
    m.mock(0x84f30, lambda a: 0)
    for selector in (0, 1, 7):
        m.run(0x5fa80, args=(selector, 5, DATA))
        assert m.args()[0] == 0xffffffff
    print("PASS: slot6 mandatory receiver-off gate returns-1; no fabricated AGPS delivery")


if __name__ == "__main__":
    lib, mnld = map(Path, sys.argv[1:])
    registration(lib)
    agps(lib)
    postinit(lib, mnld)
    nmea(lib)
    frame_callbacks(lib, mnld)
    config_producer(mnld, lib)
    build_policy(mnld)
    mandatory_callbacks(mnld, lib)
    print("OFFLINE ONLY: mocked globals/endpoints, no complete init, firmware, receiver or solver")
