#!/usr/bin/env python3
"""Verify a private, pinned preloader policy table and both real table walkers."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
                                UC_ARM64_REG_X2, UC_ARM64_REG_PC,
                                UC_ARM64_REG_SP, UC_ARM64_REG_LR)

SHA = "5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f"
BASE, TABLE, STRIDE = 0x02000F00, 0x020BF058, 0x410
STACK, DONE = 0x70000000, 0x7000F000


def extract(path):
    data = path.read_bytes()
    if data.startswith(b"UFS_BOOT\0"):
        data = data[0x1000:]
    if data[:4] != b"MMM\x01" or len(data) < 0x38:
        raise ValueError("expected pinned GFH image or UFS boot LUN")
    size = struct.unpack_from("<I", data, 0x20)[0]
    image = data[:size]
    if hashlib.sha256(image).hexdigest() != SHA:
        raise ValueError("unknown preloader; re-audit offsets and policy")
    assert struct.unpack_from("<I", image, 0x1c)[0] == BASE
    return image


def rows(image):
    result = []
    for index in range(64):
        offset = TABLE - BASE + index * STRIDE
        name, = struct.unpack_from("<Q", image, offset)
        label = image[name - BASE:].split(b"\0", 1)[0].decode("ascii") if name else ""
        slot = image[offset + 8]
        phases = []
        for field in (9, 0x209):
            entries = []
            for n in range(256):
                aid, permission = image[offset + field + 2*n:offset + field + 2*n + 2]
                if not aid or permission > 3:
                    break
                entries.append((aid, slot, permission))
            phases.append(entries if index == 0 or slot else [])
        result.append({"index": index, "slot": slot, "name": label, "phases": phases})
    return result


def walk(image, entry):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0x02000000, 0x100000)
    uc.mem_write(BASE, image)
    uc.mem_map(STACK, 0x10000)
    calls, stopped = [], []

    def code(machine, address, size, context):
        if address == DONE:
            stopped.append(address)
            machine.emu_stop()
        elif address == 0x0207D310:
            # Capture arguments at the actual writer boundary, do NOT run MMIO.
            calls.append(tuple(machine.reg_read(reg) for reg in (
                UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)))
            machine.reg_write(UC_ARM64_REG_X0, 0)
            machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))
        else:
            assert (0x0207D3F0 <= address < 0x0207D500 or
                    0x0207D5EC <= address < 0x0207D604), hex(address)

    def write(machine, access, address, size, value, context):
        assert STACK <= address and address + size <= STACK + 0x8000, hex(address)

    uc.hook_add(UC_HOOK_CODE, code)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)
    uc.reg_write(UC_ARM64_REG_SP, STACK + 0x8000)
    uc.reg_write(UC_ARM64_REG_LR, DONE)
    uc.emu_start(entry, DONE + 4, count=100000)
    assert stopped == [DONE], "table walker exceeded instruction budget"
    return calls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image = extract(args.image)
    table = rows(image)
    for phase, entry in enumerate((0x0207D3F0, 0x0207D478)):
        expected = [item for row in table for item in row["phases"][phase]]
        assert walk(image, entry) == expected
    core = {32: ((35, 2), (47, 2)), 33: ((35, 2), (47, 2)),
            34: ((35, 3), (47, 3)), 35: ((35, 3), (47, 2)),
            36: ((35, 3), (47, 3), (93, 3)),
            37: ((35, 3), (47, 2), (93, 2)),
            38: ((35, 2), (47, 3), (93, 3)), 40: ()}
    for slot, values in core.items():
        row = table[slot]
        assert row["slot"] == slot
        assert row["phases"] == [[(aid, slot, perm) for aid, perm in values], []]
    print(json.dumps({"result": "PASS", "image_sha256": SHA,
                      "scope": "both table walkers only; writer intercepted; no MMIO",
                      "modem_rows": table[32:44],
                      "warning": "sparse OR updates, not proof of zero reset state or final policy"}, indent=2))


if __name__ == "__main__":
    main()
