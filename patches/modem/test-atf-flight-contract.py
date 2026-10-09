#!/usr/bin/env python3
"""Execute pinned inner FLIGHT handlers offline; never contact a device."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                                UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5,
                                UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC)

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("power_contract", Path(__file__).with_name("test-atf-power-contract.py"))
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)
BASE, STACK, STOP = power.BASE, power.STACK, power.STOP
OUTPUT = power.OUTPUT
REGISTRY, DESCRIPTOR, CALLBACK_LIST = 0xeef08, 0x5a7f0, 0x5a7d0
ENTRIES = (0x5a710, 0x5a750, 0x5a790)
CALLBACKS = (0x33d3c, 0x33aec, 0x33c5c)
POLICY, LOCK = 0x5a9fa, 0xf73b4
RANGES = ((0xbf2c, 0xbfd8), (0x1bf58, 0x1bf84), (0x1ebc8, 0x1ec74),
          (0x1efc0, 0x1f038), (0x33aec, 0x33ea9), (0x3313c, 0x3322c), (0xa638, 0xa660))


class Flight:
    def __init__(self, data, policy=0xa5ff):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(BASE, 0x100000)
        self.uc.mem_write(BASE, data)
        self.uc.mem_map(STACK, 0x10000)
        self.reads, self.writes, self.callbacks = [], [], []
        self.inject = None
        self.uc.hook_add(UC_HOOK_CODE, self.code)
        self.uc.hook_add(UC_HOOK_MEM_READ, self.read)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.write)
        assert self.u64(DESCRIPTOR + 0x10) == BASE + CALLBACK_LIST
        for index, (entry, callback) in enumerate(zip(ENTRIES, CALLBACKS)):
            assert self.u64(CALLBACK_LIST + 8 * index) == BASE + entry
            assert self.u64(entry + 0x18) == BASE + callback
            assert self.u64(entry + 8) == 0  # No registration-time init callback.
        assert self.u64(CALLBACK_LIST + 24) == 0
        self.uc.mem_write(BASE + REGISTRY, bytes(8))
        self.uc.mem_write(BASE + LOCK, bytes(4))
        self.uc.mem_write(BASE + POLICY, struct.pack("<H", policy))
        # Use the actual registration routine, not an invented registry layout.
        assert self.call(0x1ebc8, (BASE + DESCRIPTOR,)) == 0
        assert self.u64(REGISTRY) == BASE + DESCRIPTOR

    def u64(self, offset):
        return struct.unpack("<Q", self.uc.mem_read(BASE + offset, 8))[0]

    def policy(self):
        return struct.unpack("<H", self.uc.mem_read(BASE + POLICY, 2))[0]

    def code(self, uc, address, size, context):
        offset = address - BASE
        if not any(start <= offset < end for start, end in RANGES):
            raise AssertionError(f"unreviewed instruction {offset:#x}")
        if offset in CALLBACKS:
            self.callbacks.append(offset)
            assert uc.reg_read(UC_ARM64_REG_X0) == 0
            assert uc.reg_read(UC_ARM64_REG_X1) == 7
            pointer = uc.reg_read(UC_ARM64_REG_X2)
            assert STACK <= pointer < STACK + 0x10000
            assert struct.unpack("<I", uc.mem_read(pointer, 4))[0] == self.argument & 0xffffffff
            if self.inject and offset == self.inject[0]:
                # Explicit synthetic callback failure; all nonfault paths execute real code.
                uc.reg_write(UC_ARM64_REG_X0, self.inject[1] & 0xffffffff)
                uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    def read(self, uc, access, address, size, value, context):
        self.reads.append((address, size))
        assert (BASE <= address and address + size <= BASE + 0x100000) or (
            STACK <= address and address + size <= STACK + 0x10000)

    def write(self, uc, access, address, size, value, context):
        self.writes.append((address, size, value))
        assert (BASE <= address and address + size <= BASE + 0x100000) or (
            STACK <= address and address + size <= STACK + 0x10000)

    def call(self, offset, arguments):
        self.reads.clear()
        self.writes.clear()
        self.callbacks.clear()
        regs = (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5)
        for reg, value in zip(regs, tuple(arguments) + (0,) * (6 - len(arguments))):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM64_REG_SP, STACK + 0x8000)
        self.uc.reg_write(UC_ARM64_REG_LR, STOP)
        self.uc.emu_start(BASE + offset, STOP, count=1024)
        assert self.uc.reg_read(UC_ARM64_REG_PC) == STOP, "instruction budget exceeded"
        assert self.uc.reg_read(UC_ARM64_REG_SP) == STACK + 0x8000
        return self.uc.reg_read(UC_ARM64_REG_X0)

    def flight(self, argument):
        self.argument = argument
        self.uc.mem_write(OUTPUT, b"\xa5" * 24)
        result = self.call(0xbf2c, (7, argument, 0, 0, 0, OUTPUT))
        assert self.uc.mem_read(OUTPUT, 24) == b"\xa5" * 24  # No defined a1/a2/a3 payload.
        # Only secure policy and its actual spinlock may be written outside the stack.
        for address, size, value in self.writes:
            if not STACK <= address < STACK + 0x10000:
                assert (address, size) in ((BASE + POLICY, 2), (BASE + LOCK, 4))
        assert self.uc.mem_read(BASE + LOCK, 4) == bytes(4)
        return result


def check(data):
    cases = 0
    for initial in (0, 0x40, 0xa5ff, 0xffff):
        for argument in (0, 1, 2, 0xffffffff, 0x100000000, 0x100000001):
            h = Flight(data, initial)
            assert h.flight(argument) == 0
            expected = initial | 0x40 if argument & 0xffffffff == 1 else initial & ~0x40
            assert h.policy() == expected
            assert h.callbacks == list(CALLBACKS)
            cases += 1
    for index, callback in enumerate(CALLBACKS):
        for status in (-1, -14, 1, 0x12345678):
            h = Flight(data)
            h.inject = (callback, status)
            assert h.flight(0) == status & 0xffffffff  # Kernel wrapper zero-extends w0.
            assert h.callbacks == list(CALLBACKS[:index + 1])
            assert h.policy() == 0xa5ff
            cases += 1
    h = Flight(data)
    h.uc.mem_write(BASE + REGISTRY, bytes(8))
    assert h.flight(0) == 0xffffffff and not h.callbacks and h.policy() == 0xa5ff
    cases += 1
    for entry in ENTRIES:
        h = Flight(data)
        h.uc.mem_write(BASE + entry + 0x18, bytes(8))
        assert h.flight(0) == 0 and h.policy() == 0xa5ff
        # A null callback terminates traversal successfully, not skip-and-continue.
        assert h.callbacks == list(CALLBACKS[:ENTRIES.index(entry)])
        cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("container", type=Path, help="private pinned ATF container; never upload it")
    args = parser.parse_args()
    cases = check(power.extract(args.container))
    print(json.dumps({"sha256": power.SHA, "cases": cases, "result": "PASS",
                      "flight": "32-bit argument == 1 sets secure policy bit6; all other values clear it",
                      "effects": "secure RAM policy halfword and spinlock only; no MD MMIO",
                      "first_error": "dispatcher stops on first nonzero callback; kernel zero-extends w0",
                      "proof_boundary": "inner handlers only; no outer admission, boot inhibit, reset or no-concurrent-repower proof"}, indent=2))


if __name__ == "__main__":
    main()
