#!/usr/bin/env python3
"""Linux-CI-only bounded SET slice; mock libc and capture, never dispatch/INIT."""
import hashlib
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from b41_xml_read_profile import LIB_SHA, XML_SHA, pinned_segments

AUDIT = Path(__file__).resolve().parent.parent
PROFILES = {
    "IFB": (0, 0, 1), "GGTO": (0, 0, 1), "DCB": (0, 1, 0),
    "L1Only": (1, 0, 1), "DisableSignal": (1, 0, 1), "GLP": (1, 0, 1),
    "GnssMode": (1, 0, 1), "Bluesky": (1, 0, 1), "CoTMS": (1, 0, 1),
    "SwitchTIA": (1, 0, 1), "MDTime": (1, 0, 1), "Time_Source": (1, 0, 1),
    "GNSSPower": (0, 0, 1), "OSNMA": (1, 0, 1), "SignalConfig": (1, 0, 1)
}


def load_stock(lib, xml):
    """Pin assets before iteration, so zero/disabled rows cannot bypass admission."""
    pinned_segments(lib, LIB_SHA)
    if not 0 < xml.stat().st_size <= 65536:
        raise ValueError("bounded stock XML required")
    raw = xml.read_bytes()
    if hashlib.sha256(raw).hexdigest() != XML_SHA:
        raise ValueError("wrong independently pinned stock XML")
    nodes = [node for node in ET.fromstring(raw).findall("feature")
             if node.findtext("config") == "1"]
    names = [node.text.strip() for node in nodes]
    if len(names) != 15 or set(names) != set(PROFILES):
        raise ValueError("expected exactly 15 distinct pinned enabled profiles")
    return nodes


def producer(lib, feature, chip):
    # Deferred imports: no Mac emulator instantiation or import side effects.
    sys.path.insert(0, str(AUDIT))
    from unicorn import UC_HOOK_CODE
    from unicorn.arm64_const import (UC_ARM64_REG_D0, UC_ARM64_REG_X4, UC_ARM64_REG_X21,
        UC_ARM64_REG_X23, UC_ARM64_REG_X25, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
        UC_ARM64_REG_PC)
    from test_b41_startup import Machine, LIB_SHA, DATA, STACK, STOP, REGS
    messages, controls, allocations, released = [], [], [], []
    with Machine(lib, LIB_SHA, [(0x4fd870, 0x4ff868), (0x50c130, 0x50c1d8)]) as m:
        m.u.mem_write(DATA, feature)
        m.u.mem_write(m.global_at(0x6e6610), struct.pack("<I", chip))
        addresses = iter((DATA + 0x4000, DATA + 0x6000))
        def allocate(a):
            assert a[0] in (0x400, 0x5000)
            address = next(addresses); allocations.append(address); return address
        def cstr(address):
            for length in range(4096):
                if bytes(m.u.mem_read(address + length, 1)) == b"\0":
                    return bytes(m.u.mem_read(address, length))
            raise AssertionError("bounded C string exhausted")
        def clear(a):
            assert a[2] in (0x400, 0x5000)
            m.u.mem_write(a[0], bytes([a[1]]) * a[2]); return a[0]
        def compare(a):
            assert a[2] <= 20
            return 0 if cstr(a[0])[:a[2]] == cstr(a[1])[:a[2]] else 1
        def formatter(a):
            fmt = cstr(a[2])
            double = struct.unpack("<d", struct.pack("<Q", m.u.reg_read(UC_ARM64_REG_D0)))[0]
            if fmt == b"XML:%s,v%.2f,Cfg":
                text = b"XML:" + cstr(a[3]) + f",v{double:.2f},Cfg".encode()
            elif fmt in (b",%f", b",%.0f"):
                text = (f",{double:.6f}" if fmt == b",%f" else f",{double:.0f}").encode()
            elif fmt == b"$%s*%02X\r\n":
                checksum = m.u.reg_read(UC_ARM64_REG_X4)
                text = b"$" + cstr(a[3]) + f"*{checksum:02X}\r\n".encode()
            else:
                raise AssertionError(("unreviewed format", fmt))
            assert len(text) < a[0], "no OEM truncation path is emulated"
            m.u.mem_write(a[1], text + b"\0"); return len(text)
        def capture(a):
            assert a[0] == 1 and a[2:] == (5, 0), ("non-tail output", a)
            pointer = m.u.reg_read(UC_ARM64_REG_X4)
            text = bytes(m.u.mem_read(pointer, a[1]))
            assert cstr(pointer) == text
            messages.append(text); return 0
        def checkpoint(uc, address, size, user_data):
            if address == 0x4fe320:
                assert uc.reg_read(UC_ARM64_REG_X21) == DATA
                counted = struct.unpack("<I", uc.mem_read(uc.reg_read(UC_ARM64_REG_SP) + 12, 4))[0]
                controls.append((uc.reg_read(UC_ARM64_REG_X25), uc.reg_read(UC_ARM64_REG_X23), counted))
        m.mock(0x508010, allocate)
        m.mock(0x508004, lambda a: released.append(a[0]) or 0)
        m.mock(0x6e48d0, clear)
        m.mock(0x6e4a70, compare)
        m.mock(0x6e4960, lambda a: len(cstr(a[0])))
        m.mock(0x65664c, formatter)
        m.mock(0x50c1d8, capture)  # Never execute output/queues/device/callbacks.
        m.mock(0x5214b0, lambda a: 0)  # Fixture optional logging disabled, not production policy.
        hook = m.u.hook_add(UC_HOOK_CODE, checkpoint)
        try:
            m.set(UC_ARM64_REG_SP, STACK + 0xf000); m.set(UC_ARM64_REG_LR, STOP)
            for reg, value in zip(REGS, (1, DATA)): m.set(reg, value)  # Actual XML root gps.
            m.u.emu_start(0x4fd870, STOP, count=100000)
            assert m.u.reg_read(UC_ARM64_REG_PC) == STOP, "bounded SET instruction budget"
        finally:
            m.u.hook_del(hook)
        assert m.args()[0] == 1 and released == allocations
        assert len(messages) == len(controls) == 1
        return messages[0], controls[0]


def main():
    if os.environ.get("CI") != "true" or platform.system() != "Linux":
        raise SystemExit("SET emulation is Linux CI-only; no local Mac emulator retries")
    if len(sys.argv) != 4:
        raise SystemExit("usage: test_b41_xml_set_tail_oracle.py libmnl.so MNL_Config.xml native-fixture")
    lib, xml, native = map(Path, sys.argv[1:])
    nodes = load_stock(lib, xml)  # No emulator import/instantiation before admission.
    sys.path.insert(0, str(AUDIT))
    from test_b41_xml_producer import decode
    with tempfile.TemporaryDirectory() as temporary:
        for node in nodes:
            name = node.text.strip()
            feature = decode(lib, xml, name)  # Existing pinned GET, not a generated native mock.
            fixture = Path(temporary) / "get.fc4"; fixture.write_bytes(feature)
            for chip in ((6637, 6686) if name == "DCB" else (6637,)):
                output, controls = producer(lib, feature, chip)
                assert controls == PROFILES[name], (name, controls)
                actual = subprocess.run([str(native.resolve()), str(fixture)], check=True,
                                        stdout=subprocess.PIPE, timeout=20).stdout
                assert actual == output, (name, chip, actual, output)
                print("PASS: pinned SET bytes/recipe", name, chip)


if __name__ == "__main__":
    main()
