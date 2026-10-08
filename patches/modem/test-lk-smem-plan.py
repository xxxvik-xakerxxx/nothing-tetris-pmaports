#!/usr/bin/env python3
"""Compare B4.1 service placement with real LK callbacks; no phone/MMIO."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm64_const as reg

SHA = "29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f"
STACK, INPUT = 0x70000000, 0x71000000
LOAD = 0xffff000050700000


def check_header_export(payload, container):
    assert hashlib.sha256(container).hexdigest() == "b15207a948125439a5957224d65774d9d44c558c6eb285372a520b27b8d7d6c5"
    cursor, header = 0, None
    for _ in range(128):
        assert cursor + 512 <= len(container)
        magic, size = struct.unpack_from("<II", container, cursor)
        assert magic == 0x58881688 and 0 < size <= len(container) - cursor - 512
        name = container[cursor + 8:cursor + 40].split(b"\0", 1)[0]
        if name == b"md1rom":
            assert size >= 512
            header = container[cursor + size:cursor + size + 512]
            break
        cursor = (cursor + 512 + size + 15) & ~15
    assert header and header[:12] == b"CHECK_HEADER"
    assert struct.unpack_from("<I", header, 508)[0] == 512
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x200000)
    uc.mem_write(0, payload[:0x200000])
    for address in (STACK, INPUT):
        uc.mem_map(address, 0x10000)
    uc.mem_write(INPUT, header)
    exported, stopped = {}, []

    def code(machine, address, size, context):
        if address == 0x243f0:
            stopped.append(True)
            machine.emu_stop()
        elif address == 0x27e70:
            name = machine.reg_read(reg.UC_ARM64_REG_X0)
            name = bytes(machine.mem_read(name, 64)).split(b"\0", 1)[0].decode()
            pointer = machine.reg_read(reg.UC_ARM64_REG_X1)
            assert machine.reg_read(reg.UC_ARM64_REG_X2) == 4
            assert STACK <= pointer <= STACK + 0xfffc
            assert name not in exported
            exported[name] = struct.unpack("<I", bytes(machine.mem_read(pointer, 4)))[0]
            machine.reg_write(reg.UC_ARM64_REG_X0, 0)
            machine.reg_write(reg.UC_ARM64_REG_PC, machine.reg_read(reg.UC_ARM64_REG_LR))
        else:
            assert 0x24370 <= address < 0x243f0, hex(address)

    def write(machine, access, address, size, value, context):
        assert STACK <= address and address + size <= STACK + 0x10000

    uc.hook_add(UC_HOOK_CODE, code)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)
    uc.reg_write(reg.UC_ARM64_REG_X19, INPUT)
    uc.reg_write(reg.UC_ARM64_REG_SP, STACK + 0x8000)
    uc.emu_start(0x24370, 0x243f4, count=1000)
    offsets = {"udc_en": 0x184, "consys_size": 0x180,
               "nv_cache_shm_size": 0x18c, "drdi_version": 0x190}
    assert stopped and exported == {name: struct.unpack_from("<I", header, offset)[0]
                                   for name, offset in offsets.items()}
    print("PASS: real signed-ROM header fields match actual LK tag export " +
          json.dumps(exported, sort_keys=True), file=sys.stderr)


def run(payload, cache, udc, consys, nv, gear):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x200000)
    uc.mem_write(0, payload[:0x200000])
    for address in (STACK, INPUT):
        uc.mem_map(address, 0x10000)
    count, source = (5, 0x198558) if cache else (18, 0x198318)
    for index in range(count):
        row = list(struct.unpack_from("<6IQ", payload, source + index * 32))
        if row[-1]:
            row[-1] -= LOAD
        uc.mem_write(INPUT + index * 32, struct.pack("<6IQ", *row))
    start, stop = (0x22a94, 0x22bec) if cache else (0x223cc, 0x22568)
    stopped, seen = [], []
    tags = {"drdi_version": 3, "udc_en": udc, "consys_size": consys,
            "nv_cache_shm_size": nv}

    def finish(machine, value):
        machine.reg_write(reg.UC_ARM64_REG_X0, value)
        machine.reg_write(reg.UC_ARM64_REG_PC, machine.reg_read(reg.UC_ARM64_REG_LR))

    def code(machine, address, size, context):
        if address == stop:
            stopped.append(True)
            machine.emu_stop()
        elif address in (0x817c8, 0x817e0):
            target = machine.reg_read(reg.UC_ARM64_REG_X0)
            assert STACK <= target < STACK + 0x10000
            machine.mem_write(target, struct.pack("<I", count))
            finish(machine, INPUT)
        elif address == 0x27f78:
            name = machine.reg_read(reg.UC_ARM64_REG_X0)
            name = bytes(machine.mem_read(name, 64)).split(b"\0", 1)[0].decode()
            target = machine.reg_read(reg.UC_ARM64_REG_X1)
            assert machine.reg_read(reg.UC_ARM64_REG_X2) == 4
            assert STACK <= target < STACK + 0x10000
            seen.append(name)
            machine.mem_write(target, struct.pack("<I", tags[name]))
            finish(machine, 4)
        elif address == 0x34f60:
            name = machine.reg_read(reg.UC_ARM64_REG_X0)
            assert bytes(machine.mem_read(name, 64)).split(b"\0", 1)[0] == b"md1_ccb_cap_gear"
            finish(machine, INPUT + 0xf000 if gear else 0)
        elif address == 0x69394:
            finish(machine, gear)
        elif address == 0x69c28:
            finish(machine, 0)
        else:
            assert (start <= address < stop or 0x21b1c <= address < 0x21fe0), hex(address)

    def write(machine, access, address, size, value, context):
        assert (STACK <= address and address + size <= STACK + 0x10000 or
                INPUT <= address and address + size <= INPUT + count * 32 or
                address == 0x1b5df8 and size == 4), hex(address)

    uc.hook_add(UC_HOOK_CODE, code)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)
    uc.reg_write(reg.UC_ARM64_REG_SP, STACK + 0x8000)
    uc.reg_write(reg.UC_ARM64_REG_X29, STACK + 0x8030)
    uc.emu_start(start, stop + 4, count=100000)
    assert stopped
    assert sorted(seen) == sorted(["consys_size", "nv_cache_shm_size", "udc_en"]
                                  if cache else ["drdi_version"])
    rows, cursor, expected_count = [], 0, count
    for index in range(count):
        ident, offset, size, align, flags, md, _ = struct.unpack(
            "<6IQ", bytes(uc.mem_read(INPUT + index * 32, 32)))
        expected_offset = (cursor + align - 1) & -align if align else cursor
        assert offset == md == expected_offset
        expected_count += offset != cursor
        rows.append([ident, offset, size, flags])
        cursor = offset + size
    capacity = uc.reg_read(reg.UC_ARM64_REG_X20 if cache else reg.UC_ARM64_REG_X22)
    assert capacity == (cursor + 0xffff) & ~0xffff
    assert uc.reg_read(reg.UC_ARM64_REG_X3) == expected_count
    return {"entries": rows, "capacity": capacity, "rows": expected_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--modem", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    assert hashlib.sha256(image).hexdigest() == SHA
    if args.modem:
        check_header_export(image[512:], args.modem.read_bytes())
    cases = []
    for gear in (0, 1, 2, 3, 4, 11, 12):
        for udc in (0, 1):
            for consys, nv in ((0x2b00000, 0), (0x100000, 0x200000),
                               (0xd80000, 0x16a040)):
                inputs = [3, udc, consys, nv, gear]
                cases.append({"inputs": inputs,
                              "nc": run(image[512:], False, udc, consys, nv, gear),
                              "cache": run(image[512:], True, udc, consys, nv, gear)})
    print('{"lk_sha256": ' + json.dumps(SHA) + ', "cases": [')
    print(",\n".join(json.dumps(case, separators=(",", ":")) for case in cases))
    print("]}")


if __name__ == "__main__":
    main()
