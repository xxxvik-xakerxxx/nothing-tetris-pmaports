#!/usr/bin/env python3
"""Execute the pinned BL33 descriptor builder with synthetic data, never SMC."""
from pathlib import Path
import runpy
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_SP,
)

START, END = 0x2761c, 0x276a4
EP, PARAM, STACK, STOP = 0x2000000, 0x2001000, 0x2002000, 0x2003000


def main():
    helper = runpy.run_path(str(Path(__file__).with_name("inspect-bl2-handoff.py")))
    data = helper["extract"](Path(sys.argv[1]).read_bytes(), "atf")
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for address in (0x27000, 0x11000, 0x19000, EP, PARAM, STACK, STOP):
        uc.mem_map(address, 4096)
    uc.mem_write(START, data[START:END])
    returned = {}
    calls = []

    def guard(machine, address, size, context):
        if START <= address < END:
            return
        if address not in returned:
            raise RuntimeError(f"unmodeled execution {address:#x}")
        calls.append(address)
        machine.reg_write(UC_ARM64_REG_X0, returned[address])
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    uc.hook_add(UC_HOOK_CODE, guard)
    count = 0
    for mode in (0, 1):
        for tags, size, entry in ((0, 0, 0), (0x11223344, 128, 0x22334455),
                                  (0x123456789abcdef0, 0x100000001, 0xfedcba9876543210)):
            before = bytearray(b"\xa5" * 128)
            expected = bytearray(before)
            returned.clear()
            returned.update({0x118ac: 0x1234567887654321,
                             0x118b8: 0x123456789, 0x118c4: 0x1122334455667788,
                             0x19bb4: mode})
            calls.clear()
            uc.mem_write(EP, bytes(before))
            uc.mem_write(PARAM, struct.pack("<QQQ", tags, size, entry))
            uc.reg_write(UC_ARM64_REG_X0, EP)
            uc.reg_write(UC_ARM64_REG_X1, PARAM)
            uc.reg_write(UC_ARM64_REG_SP, STACK + 4096)
            uc.reg_write(UC_ARM64_REG_LR, STOP)
            uc.emu_start(START, STOP, count=128)
            assert uc.reg_read(UC_ARM64_REG_PC) == STOP
            assert uc.reg_read(UC_ARM64_REG_SP) == STACK + 4096
            struct.pack_into("<IIQ", expected, 0, 0x580101,
                             (0xa5a5a5a5 & ~0x20) | 1, entry)
            struct.pack_into("<I", expected, 0x10, 0x3c5 if mode == 0 else 0x3c9)
            for offset, value in ((0x18, tags), (0x30, returned[0x118ac]),
                                  (0x38, tags), (0x40, size),
                                  (0x48, returned[0x118b8] & 0xffffffff),
                                  (0x50, returned[0x118c4])):
                struct.pack_into("<Q", expected, offset, value)
            assert uc.mem_read(EP, 128) == expected
            assert uc.mem_read(PARAM, 24) == struct.pack("<QQQ", tags, size, entry)
            assert calls == [0x118ac, 0x118b8, 0x118c4, 0x19bb4]
            count += 1
    print(f"PASS: {count} pinned BL33 builder cases, full descriptor/guard comparison")
    print("PC=param[2], arg0=arg4=param[0], arg5=param[1]; arg1/arg2 untouched")
    print("No firmware entry, SMC, MMIO or handset access; not a live tag-list validation")


if __name__ == "__main__":
    main()
