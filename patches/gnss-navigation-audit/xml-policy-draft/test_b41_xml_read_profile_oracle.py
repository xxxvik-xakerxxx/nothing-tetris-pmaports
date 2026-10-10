#!/usr/bin/env python3
"""Linux-CI-only real selector/scanner; stop BEFORE reader, SET or engine."""
import os
from pathlib import Path
import platform
import struct
import sys

from b41_xml_read_profile import (LIB_SHA, PRIMARY, PREFERRED, elf_bytes,
    pinned_segments, select_documents, validate_sources)
from test_b41_xml_read_profile import cases, document


def producer(lib, mnld, primary, preferred, empty_directories=False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from unicorn import UC_HOOK_CODE
    from unicorn.arm64_const import (UC_ARM64_REG_D0, UC_ARM64_REG_SP,
                                     UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_X4)
    from test_b41_startup import Machine, STACK, STOP
    from b41_xml_read_profile import MNLD_SHA
    library = pinned_segments(lib, LIB_SHA)
    producer_bytes = pinned_segments(mnld, MNLD_SHA)
    scans, opened, closed, files = [], [], [], {}
    available = {PRIMARY.encode(): primary, PREFERRED.encode(): preferred}
    with Machine(lib, LIB_SHA, [(0x4fd20c, 0x4fd460), (0x4fd53c, 0x4fd604),
                                (0x500910, 0x500bbc)]) as machine:
        m = machine
        config = m.global_at(0x6e69d0)
        for offset, address in ((0x406, 0x88b78), (0x424, 0x88b98), (0x208, 0x88ae0)):
            m.u.mem_write(config + offset, elf_bytes(producer_bytes, address, 30))
        if empty_directories:
            m.u.mem_write(config + 0x406, b"\0" * 30)
            m.u.mem_write(config + 0x424, b"\0" * 30)
        # This GOT target is a real immutable code table, not synthetic state.
        m.q(0x6e69b8, struct.unpack("<Q", elf_bytes(library, 0x6e69b8, 8))[0])

        def cstr(pointer, limit=4096):
            for length in range(limit):
                if m.u.mem_read(pointer + length, 1) == b"\0":
                    return bytes(m.u.mem_read(pointer, length))
            raise AssertionError("bounded C string exhausted")

        def clear(a):
            assert a[1] == 0 and 0 <= a[2] <= 0xfc4
            m.u.mem_write(a[0], b"\0" * a[2]); return a[0]

        def copy(a):
            assert a[3] == 50 and m.u.reg_read(UC_ARM64_REG_X4) == 30
            text = cstr(a[1], 30)
            assert a[2] == len(text) and len(text) < 30
            m.u.mem_write(a[0], text); return a[0]

        def append(a):
            assert a[3] == 50
            text = cstr(a[0], 50) + cstr(a[1], 15)[:a[2]]
            assert len(text) < 50
            m.u.mem_write(a[0], text + b"\0"); return a[0]

        def memcpy(a):
            assert a[3] == 1024 and 0 <= a[2] < 1024
            m.u.mem_write(a[0], bytes(m.u.mem_read(a[1], a[2]))); return a[0]

        def fopen(a):
            path, mode = cstr(a[0], 50), cstr(a[1], 2)
            assert mode == b"r" and path in available  # No write/logging/host file opens.
            opened.append(path)
            content = available[path]
            if content is None: return 0
            handle = 0x2008000 + 0x100 * len(files)
            files[handle] = [content, 0]
            return handle

        def fgets(a):
            assert a[1] == 1024 and a[2] in files and a[2] not in closed
            content, position = files[a[2]]
            if position == len(content): return 0
            end = min(position + 1023, len(content))
            newline = content.find(b"\n", position, end)
            if newline >= 0: end = newline + 1
            m.u.mem_write(a[0], content[position:end] + b"\0")
            files[a[2]][1] = end; return a[0]

        def fclose(a):
            assert a[0] in files and a[0] not in closed
            closed.append(a[0]); return 0

        def strstr(a):
            index = cstr(a[0], 1024).find(cstr(a[1], 32))
            return 0 if index < 0 else a[0] + index

        cursor = [0]
        def strtok(a):
            assert cstr(a[1], 2) == b"."
            if a[0]: cursor[0] = a[0]
            pointer = cursor[0]
            if pointer == 0: return 0
            while m.u.mem_read(pointer, 1) == b".": pointer += 1
            if m.u.mem_read(pointer, 1) == b"\0": cursor[0] = 0; return 0
            text = cstr(pointer, 1024)
            dot = text.find(b".")
            if dot < 0: cursor[0] = 0
            else:
                m.u.mem_write(pointer + dot, b"\0"); cursor[0] = pointer + dot + 1
            return pointer

        def atof(a):
            value = float(cstr(a[0], 32).decode("ascii"))
            m.set(UC_ARM64_REG_D0, struct.unpack("<Q", struct.pack("<d", value))[0])
            return 0

        def diagnostic(a):
            assert a[0] == 0 and a[2] == 7  # Capture only, never dispatch.
            return 0

        def checkpoint(uc, address, size, user_data):
            if address == 0x500ad8:
                scans.append(m.args()[0])

        m.mock(0x6e48d0, clear)
        m.mock(0x6e4a80, lambda a: len(bytes(m.u.mem_read(a[0], a[1])).split(b"\0", 1)[0]))
        m.mock(0x6e4b90, copy); m.mock(0x6e4ba0, append); m.mock(0x6e4ad0, memcpy)
        m.mock(0x6e4af0, fopen); m.mock(0x6e4be0, fgets); m.mock(0x6e4b20, fclose)
        m.mock(0x6e4bf0, strstr); m.mock(0x6e4c00, strtok); m.mock(0x6e4c10, atof)
        m.mock(0x6e4a70, lambda a: int(cstr(a[0])[:a[2]] != cstr(a[1])[:a[2]]))
        m.mock(0x50c1d8, diagnostic)
        m.mock(0x5214b0, lambda a: 0)  # Optional logging off ONLY in this fixture.
        hook = m.u.hook_add(UC_HOOK_CODE, checkpoint)
        try:
            m.set(UC_ARM64_REG_SP, STACK + 0xf000); m.set(UC_ARM64_REG_LR, STOP)
            m.u.emu_start(0x4fd20c, 0x4fd600, count=300000)
            assert m.u.reg_read(UC_ARM64_REG_PC) == 0x4fd600, "bounded selector budget"
        finally:
            m.u.hook_del(hook)
        policy, read, write, scratch = m.args()
        sp = m.u.reg_read(UC_ARM64_REG_SP)
        compared = struct.unpack("<2d", m.u.mem_read(sp + 8, 16))
        result = (cstr(read + 8).decode(), cstr(write + 8).decode(),
                  m.u.mem_read(policy, 1)[0], tuple(scans), compared)
        assert opened == [PRIMARY.encode(), PREFERRED.encode()]
        assert set(closed) == set(files) and len(closed) == len(files)
        return result


def main():
    if os.environ.get("CI") != "true" or platform.system() != "Linux":
        raise SystemExit("selector oracle is Linux CI-only; no local Mac emulator retries")
    if len(sys.argv) != 4:
        raise SystemExit("usage: test_b41_xml_read_profile_oracle.py libmnl.so mnld MNL_Config.xml")
    lib, mnld, xml = map(Path, sys.argv[1:])
    stock = validate_sources(lib, mnld, xml)
    vectors = list(cases(stock))
    vectors.extend(("root-code-" + code, stock, document("21111602.6." + code), PREFERRED, 3)
                   for code in ("0O", "0L", "0S", "0H", "0V", "AB"))
    for name, primary, preferred, path, policy in vectors:
        expected = select_documents(primary, preferred)
        actual = producer(lib, mnld, primary, preferred)
        assert actual == (path, PREFERRED, policy,
            (expected.primary.status, expected.preferred.status),
            (expected.preferred.compared_version, expected.primary.compared_version)), (name, actual, expected)
        print("PASS: real selector + real scanner", name)
    actual = producer(lib, mnld, stock, None, empty_directories=True)
    assert actual[:4] == (PRIMARY, PREFERRED, 7, (1, 0))
    print("PASS: source fallback directories (empty fields), before reader call")


if __name__ == "__main__":
    main()
