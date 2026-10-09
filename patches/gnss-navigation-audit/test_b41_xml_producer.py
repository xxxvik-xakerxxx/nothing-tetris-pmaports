#!/usr/bin/env python3
"""Pinned XML decoder oracle. In-memory stdio only; never applies engine params."""
import hashlib
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET
from elftools.elf.elffile import ELFFile
from unicorn.arm64_const import UC_ARM64_REG_D0, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC
from test_b41_startup import Machine, LIB_SHA, DATA, STACK, STOP, REGS

XML_SHA = "7018751a6e20a12fb255f9dfd5f6b55a0c6c7966a87f047d427b885b62f9ee31"

def decode(lib, asset, feature):
    raw = asset.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == XML_SHA
    with Machine(lib, LIB_SHA, [(0x4ff868, 0x500524)]) as m:
        return decode_machine(m, lib, raw, feature)

def decode_machine(m, lib, raw, feature):
    # Machine's synthetic global GOT is inappropriate for immutable version strings.
    with lib.open("rb") as f:
        e = ELFFile(f)
        for s in e.iter_segments():
            if s["p_type"] == "PT_LOAD" and s["p_vaddr"] <= 0x6e69b8 < s["p_vaddr"] + s["p_filesz"]:
                m.u.mem_write(0x6e69b8, s.data()[0x6e69b8-s["p_vaddr"]:0x6e69b8-s["p_vaddr"]+8])
    def cstr(address):
        result = bytearray()
        for offset in range(4096):
            ch = bytes(m.u.mem_read(address + offset, 1))
            if ch == b"\0": return bytes(result)
            result.extend(ch)
        raise AssertionError("unbounded string")
    def copy(a):
        assert a[2] <= a[3]
        m.u.mem_write(a[0], bytes(m.u.mem_read(a[1], a[2])))
        return a[0]
    m.mock(0x6e48d0, lambda a: m.u.mem_write(a[0], bytes(a[2])) or a[0])
    m.mock(0x6e48e0, lambda a: m.u.mem_write(a[0], bytes(m.u.mem_read(a[1], a[2]))) or a[0])
    m.mock(0x6e4ad0, copy)
    m.mock(0x6e4960, lambda a: len(cstr(a[0])))
    m.mock(0x6e4a70, lambda a: 0 if cstr(a[0])[:a[2]] == cstr(a[1])[:a[2]] else 1)
    def strstr(a):
        offset = cstr(a[0]).find(cstr(a[1]))
        return 0 if offset < 0 else a[0] + offset
    m.mock(0x6e4bf0, strstr)
    m.mock(0x6e4c20, lambda a: (a[0] + cstr(a[0]).index(bytes([a[1]]))) if bytes([a[1]]) in cstr(a[0]) else 0)
    cursor = [0]
    def strtok(a):
        if a[0]: cursor[0] = a[0]
        delimiters = cstr(a[1])
        p = cursor[0]
        if not p: return 0
        while bytes(m.u.mem_read(p, 1))[0] in delimiters: p += 1
        if bytes(m.u.mem_read(p, 1)) == b"\0": cursor[0] = 0; return 0
        start = p
        while bytes(m.u.mem_read(p, 1)) != b"\0" and bytes(m.u.mem_read(p, 1))[0] not in delimiters: p += 1
        if bytes(m.u.mem_read(p, 1)) == b"\0": cursor[0] = 0
        else: m.u.mem_write(p, b"\0"); cursor[0] = p + 1
        return start
    m.mock(0x6e4c00, strtok)
    def atof(a):
        value = float(cstr(a[0]))
        m.set(UC_ARM64_REG_D0, struct.unpack("<Q", struct.pack("<d", value))[0])
        return 0
    m.mock(0x6e4c10, atof)
    m.mock(0x6e4c30, lambda a: int(cstr(a[0]), a[2]))
    lines = iter(raw.splitlines(keepends=True))
    def fopen(a):
        assert cstr(a[0]) == b"/vendor/etc/MNL_Config.xml"
        assert cstr(a[1]) == b"r"
        return 1
    def fgets(a):
        line = next(lines, None)
        if line is None: return 0
        assert a[2] == 1 and len(line) < a[1]
        m.u.mem_write(a[0], line + b"\0")
        return a[0]
    m.mock(0x6e4af0, fopen)
    m.mock(0x6e4be0, fgets)
    m.mock(0x6e4b20, lambda a: 0)
    m.u.mem_write(DATA, b"\2")  # GET mode: never setter4fd870/file mutation
    m.u.mem_write(DATA + 128 + 8, b"/vendor/etc/MNL_Config.xml\0")
    output = DATA + 4096
    m.u.mem_write(output, feature.encode() + b"\0")
    m.set(UC_ARM64_REG_SP, STACK + 0xf000)
    m.set(UC_ARM64_REG_LR, STOP)
    for r,v in zip(REGS, (DATA, DATA + 128, 0, output)): m.set(r,v)
    m.u.emu_start(0x4ff868, STOP, count=300000)
    assert m.u.reg_read(UC_ARM64_REG_PC) == STOP, "bounded XML instruction budget"
    assert m.args()[0] == 1, (feature, m.args()[0])  # root type="gps"
    return bytes(m.u.mem_read(output, 0xfc4))

def verify(lib, asset):
    root = ET.fromstring(asset.read_bytes())
    for node in root.findall("feature"):
        name = node.text.strip()
        got = decode(lib, asset, name)
        expected = bytearray(0xfc4)
        expected[:len(name)] = name.encode()
        struct.pack_into("<d", expected, 0x14, float(node.findtext("version")))
        expected[0x1c] = int(node.findtext("config"))
        rows = node.findall("setting")
        count = 0
        for row, setting in enumerate(rows):
            values = [float(v) for v in setting.text.split(",")]
            count += len(values)
            struct.pack_into("<" + "d" * len(values), expected, 0x24 + row * 200, *values)
        struct.pack_into("<I", expected, 0x20, count)
        assert got == expected, (name, [(hex(i),a,b) for i,(a,b) in enumerate(zip(got,expected)) if a!=b][:20])
    print("PASS: all stock XML features match pinned GET parser 0xfc4 producer")

if __name__ == "__main__": verify(Path(sys.argv[1]), Path(sys.argv[2]))
