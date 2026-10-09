#!/usr/bin/env python3
"""27-byte producer branches, exact B4.1 instructions; no engine initialization."""
from pathlib import Path
from contextlib import contextmanager
import struct
import sys
from unicorn.arm64_const import UC_ARM64_REG_X21, UC_ARM64_REG_X25
from test_b41_startup import Machine, MNLD_SHA
from test_b41_xml_producer import decode

@contextmanager
def machine(path, ranges):
    with Machine(path, MNLD_SHA, ranges) as m:
        m.map(0xdd000, 0x3000)
        yield m

def word(m, address, value): m.u.mem_write(address, struct.pack("<I", value))
def read(m, offset, size=4): return int.from_bytes(m.u.mem_read(0xde520 + offset, size), "little")

def producers(path):
    for host in (0, 1, 0xffffffff):
        with machine(path, [(0x62ce4, 0x62d0c)]) as m:
            word(m, 0x88794, host)
            m.run(0x62ce4, 0x62d0c)
            assert read(m, 0x20) == (1000 if host else 200)
    for secondary in (0, 1, 255):
        with machine(path, [(0x63358, 0x63394)]) as m:
            word(m, 0xde304, 0x12345678); word(m, 0xde308, 0x10203040)
            m.mock(0x56ce0, lambda a: int(bool(secondary)))
            m.run(0x63358, 0x63394)
            assert read(m, 0x30) == 0x12345678 and read(m, 0x28) == 0x10203040
            assert read(m, 0x34) == (0x12345678 if secondary else 0)
            assert read(m, 0x2c) == (0x10203040 if secondary else 0)
    for mode in (0, 1, 2, 3, 4, 0xffffffff):
        with machine(path, [(0x63484, 0x634c0)]) as m:
            word(m, 0x88c1c, mode); word(m, 0xde548, 0x10203040)
            m.run(0x63484, 0x634c0)
            assert read(m, 0x28) == (0x10203040 | ({1:0x80000000,2:0x40000000,3:0xc0000000}.get(mode,0)))
    for override1,override2 in ((0xffffffff,0xffffffff),(3,0xffffffff),(0xffffffff,8),(3,8)):
        with machine(path, [(0x634c0, 0x6352c)]) as m:
            word(m, 0x88c20, 6); word(m, 0x88e10, override1); word(m, 0x88e14, override2)
            m.mock(0x62a20, lambda a: 0) # Separate exact XML miss oracle below.
            m.run(0x634c0, 0x6352c)
            assert read(m, 0x38) == (override2 if override2 != 0xffffffff else override1 if override1 != 0xffffffff else 6)
    for tracking in (0,1,2,0xffffffff):
        with machine(path, [(0x63b3c, 0x63b84)]) as m:
            word(m, 0xde9d8, tracking); m.mock(0x84f30, lambda a: 0)
            m.run(0x63b3c, 0x63b84)
            assert read(m,0x50,1) == (tracking if tracking <= 1 else 0)
    for requested in range(16):
        for host in (0,1):
            for probe in (0,1,2,3):
                with machine(path, [(0x63a0c,0x63a34),(0x63d68,0x63d94)]) as m:
                    m.set(UC_ARM64_REG_X21,0xde000);m.set(UC_ARM64_REG_X25,0xde000)
                    word(m,0xde228,requested);word(m,0x88794,host)
                    m.u.mem_write(0x88c4c,b"\x9a");m.mock(0x4eee0,lambda a:probe)
                    m.run(0x63a0c,0x63a34)
                    expected = 0x9a if not(requested & 13) and host and probe & 1 else 0
                    assert read(m,0x5b,1)==expected,(requested,host,probe)
    for present in (0,1,255):
        with machine(path,[(0x63a38,0x63a8c)]) as m:
            m.set(UC_ARM64_REG_X21,0xde558)
            m.u.mem_write(0xddd84,bytes([present]));m.u.mem_write(0x88c80,b"\x9a")
            m.run(0x63a38,0x63a8c)
            assert read(m,0x6c,1)==(0x9a if present else 0)
    print("PASS: all27 remaining first-config bytes, 128 MPE branch vectors, exact mode flags")

if __name__ == "__main__":
    producers(Path(sys.argv[1]))
    missing=decode(Path(sys.argv[2]),Path(sys.argv[3]),"BD_PRIORITY")
    assert missing==b"BD_PRIORITY"+bytes(0xfc4-len("BD_PRIORITY"))
    print("PASS: actual stock XML GET miss preserves zero policy for BD_PRIORITY")
