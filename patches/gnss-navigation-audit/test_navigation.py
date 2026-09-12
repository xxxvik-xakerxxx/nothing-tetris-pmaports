#!/usr/bin/env python3
"""Pinned B4.1 post-init/dispatch audit; ARM64 emulation, no external I/O."""
import hashlib
from pathlib import Path
import struct
import sys

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
    UC_ARM64_REG_X4, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21,
    UC_ARM64_REG_X22, UC_ARM64_REG_X23, UC_ARM64_REG_X24, UC_ARM64_REG_X25, UC_ARM64_REG_X28,
    UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0,
)

SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
DATA, STACK, TLS, STOP = 0x2000000, 0x2010000, 0x2020000, 0x2030000
RANGES = (
    (0x52f2c0, 0x52f2e8), (0x52f334, 0x52f394),
    (0x50fda0, 0x50fddc), (0x510028, 0x510034),
    (0x52fe14, 0x52fe78), (0x530228, 0x530250), (0x5323d4, 0x5323dc),
    (0x5c6644, 0x5c66bc), (0x699c50, 0x699eb8),
    (0x50bd60, 0x50bf18), (0x554ae8, 0x554c64), (0x683b9c, 0x683c1c),
    (0x542bfc, 0x542c28), (0x53cef4, 0x53cf44),
    (0x4fa630, 0x4fa67c), (0x530c80, 0x530c88),
    (0x533674, 0x5336dc), (0x534c88, 0x534c8c),
)
TABLES = ((0x9e20, 8), (0x4c447e, 268), (0x4c4cf2, 1362),
          (0x4c4b44, 430), (0x4c5244, 42))
REGS = (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
        UC_ARM64_REG_X3, UC_ARM64_REG_X4)


class Audit:
    def __init__(self, path):
        if hashlib.sha256(path.read_bytes()).hexdigest() != SHA:
            raise ValueError("wrong B4.1 libmnl SHA-256")
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.pages = set()
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            for start, end in RANGES:
                self.load(elf, start, end - start)
            for start, size in TABLES:
                self.load(elf, start, size)
        for address in (DATA, STACK, TLS, STOP, 0x6e6000, 0x6e7000):
            self.map(address)
        self.hooks = {}
        self.uc.hook_add(UC_HOOK_CODE, self.hook)
        self.set(UC_ARM64_REG_TPIDR_EL0, TLS)

    def map(self, address):
        page = address & ~4095
        if page not in self.pages:
            self.uc.mem_map(page, 4096)
            self.pages.add(page)

    def load(self, elf, address, size):
        for page in range(address & ~4095, (address + size + 4095) & ~4095, 4096):
            self.map(page)
        for segment in elf.iter_segments():
            off = address - segment["p_vaddr"]
            if segment["p_type"] == "PT_LOAD" and 0 <= off and off + size <= segment["p_filesz"]:
                self.uc.mem_write(address, segment.data()[off:off + size])
                return
        raise ValueError(f"unbacked ELF interval {address:#x}+{size}")

    def set(self, reg, value):
        self.uc.reg_write(reg, value)

    def args(self):
        return tuple(self.uc.reg_read(reg) for reg in REGS)

    def q(self, address, value):
        self.uc.mem_write(address, struct.pack("<Q", value))

    def hook(self, uc, address, size, _):
        if address in self.hooks:
            result = self.hooks[address](self.args())
            uc.reg_write(UC_ARM64_REG_X0, result)
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
        elif not any(start <= address < end for start, end in RANGES):
            raise RuntimeError(f"forbidden external execution {address:#x}")

    def mock(self, address, fn):
        self.map(address)
        self.hooks[address] = fn

    def run(self, start, end, count=4096):
        self.map(end)
        self.uc.emu_start(start, end, count=count)
        assert self.uc.reg_read(UC_ARM64_REG_PC) == end, "instruction limit"


def dispatch_tests(path):
    a = Audit(path)
    a.q(0x6e79c8, DATA + 0xa00)
    for result in (18, 17, 0):
        a.set(UC_ARM64_REG_X0, result)
        a.run(0x52f2c0, 0x52f2e8)
        assert a.uc.reg_read(UC_ARM64_REG_X19) == (18 if result == 18 else 17)
    # Execute the constructor, including its branch which omits param42.
    for chipset in (0xffff6878, 0x40):
        a.uc.mem_write(DATA + 0x28, struct.pack("<I", chipset))
        a.uc.mem_write(STACK, b"\xa5" * 1024)
        a.set(UC_ARM64_REG_SP, STACK)
        a.set(UC_ARM64_REG_X21, STACK + 0x20)
        a.set(UC_ARM64_REG_X22, DATA)
        endpoint = 0x52f394 if chipset == 0x40 else 0x6e4c50
        a.run(0x52f334, endpoint)
        if chipset != 0x40:
            assert a.args()[:2] == (42, STACK + 0x20)
            assert bytes(a.uc.mem_read(STACK + 0x20, 232)) == struct.pack("<II", 3, 1) + bytes(224)
    for command, message, size in ((0, 1001, 0), (1, 1002, 0), (42, 1016, 232)):
        a.set(UC_ARM64_REG_X19, command)
        a.run(0x50fda0, 0x51036c)
        assert a.uc.reg_read(UC_ARM64_REG_X24) == message
        assert a.uc.reg_read(UC_ARM64_REG_X25) == size
    a.set(UC_ARM64_REG_X19, 134)
    a.run(0x50fda0, 0x510408)
    assert a.args()[0] == 0xffffffff
    for message, target in ((1001, 0x5328b0), (1002, 0x530c80),
                            (1016, 0x530228), (101, 0x52fe6c)):
        a.uc.mem_write(DATA, struct.pack("<HHII", message, 232, 3, 1))
        a.set(UC_ARM64_REG_X24, DATA)
        a.set(UC_ARM64_REG_X20, 0x4c4b44)
        a.run(0x52fe14, target)
    for subtype in (0, 3, 22):
        a.uc.mem_write(DATA + 4, struct.pack("<II", subtype, 1))
        a.set(UC_ARM64_REG_X24, DATA)
        a.run(0x530228, 0x5c6644 if subtype == 3 else 0x52fde0)
        if subtype == 3:
            assert a.args()[0] == 1
    # PMTK161's parsed double is a control argument, not a cold-start proof.
    for parameter, expected in ((0, 0), (1, 1), (2, 2), (7, 2)):
        a.uc.mem_write(DATA + 8, struct.pack("<d", parameter))
        a.set(UC_ARM64_REG_X19, DATA)
        a.run(0x542bfc, 0x50bbe4)
        assert a.args()[:4] == (5, 3, 1, expected)
    # The superficially paired set_param(1) path is not a start request.
    a.run(0x530c80, 0x4fa5f8)
    assert a.args()[0] == 1
    for second_link in (0, 1):
        a.set(UC_ARM64_REG_X0, second_link)
        a.run(0x4fa630, 0x50bbe4)
        assert a.args()[:4] == (5, 3 if second_link else 1, 1, 4)
    print("PASS: constructor/skip, set_param 0/1/42/reject, tables, subtype guards, PMTK161, reset counterexample")


def config_wire_test(path, second_link, missing_primary=False, state=0):
    a = Audit(path)
    contexts = {i: DATA + 0x100 + i * 0x100 for i in range(3)}
    queues = {context + 0x80: i for i, context in contexts.items()}
    output = {i: bytearray() for i in range(3)}
    flushes, calls, logs = [], [], []
    for i, context in contexts.items():
        a.q(context + 8, context + 0x80)
        a.q(context + 16, STOP + 0x100 + 4 * i)
        a.mock(STOP + 0x100 + 4 * i, lambda args, i=i: flushes.append(i) or 0)
    a.q(0x6e7258, DATA + 0x800)
    a.q(0x6e6c50, DATA + 0x810)
    a.q(0x6e6c40, DATA + 0x820)
    a.uc.mem_write(DATA + 0x810, struct.pack("<H", state))
    a.q(0x6e7b18, DATA + 0x830)
    a.uc.mem_write(DATA + 0x830, b"\x04")  # No optional diagnostic history append.
    a.mock(0x651e50, lambda args: 0 if missing_primary and args[0] == 1 else contexts[args[0]])
    a.mock(0x508d0c, lambda args: second_link)
    a.mock(0x693948, lambda args: logs.append("format") or 0)
    a.mock(0x50c1d8, lambda args: logs.append("error") or 0)

    def copy(args):
        queue, pointer, size = args[:3]
        assert size == 2
        output[queues[queue]].extend(a.uc.mem_read(pointer, size))
        return 0

    def byte(args):
        queue, value = args[:2]
        assert value <= 255
        output[queues[queue]].append(value)
        return 0

    a.mock(0x650c80, copy)
    a.mock(0x650b54, byte)
    # Observe arguments but execute the real formatter and sender afterwards.
    def observe(uc, address, size, _):
        if address == 0x699c50:
            args = a.args()
            assert args[:3] == (0, 0x1ccf8, 2) and args[4] == 3
            assert bytes(uc.mem_read(args[3], 8)) == struct.pack("<II", 50, 1)
        if address == 0x50bd60:
            args = a.args()
            calls.append((args[:3], bytes(uc.mem_read(args[3], args[2]))))
    a.uc.hook_add(UC_HOOK_CODE, observe)
    a.set(UC_ARM64_REG_X0, 1)
    a.set(UC_ARM64_REG_SP, STACK + 4096)
    a.set(UC_ARM64_REG_LR, STOP)
    # The diagnostic wrapper dereferences all contexts before the sender.
    # A missing primary context is tested directly at the lower sender.
    if missing_primary:
        a.uc.mem_write(DATA + 0x900, bytes.fromhex("3200000100"))
        for reg, value in zip(REGS, (5, 1, 5, DATA + 0x900)):
            a.set(reg, value)
        a.run(0x50bd60, STOP)
        assert not flushes and not any(output.values()) and "error" in logs
    else:
        a.run(0x5c6644, STOP)
        assert a.uc.reg_read(UC_ARM64_REG_SP) == STACK + 4096
        assert a.args()[0] == 1
        assert a.uc.mem_read(DATA + 0x800, 1) == b"\x01"
        payload = bytes.fromhex("3200000100")
        assert calls == [((5, 1, 5), payload), ((5, 2, 5), payload)]
        frame = bytes.fromhex("aaf0090005fe32000001003f01aa0f")
        assert bytes(output[1]) == frame and not output[0]
        assert bytes(output[2]) == (frame if second_link else b"")
        assert flushes == ([1, 2] if second_link else [1])
        print(f"PASS: post-init FE05/32 frame {frame.hex()}, secondary={second_link}, sender_state={state}")


def feed_tests(path):
    a = Audit(path)
    a.mock(0x50c1d8, lambda args: 0)
    for state in (0, 1, 6):
        a.uc.mem_write(DATA, struct.pack("<H", state))
        a.set(UC_ARM64_REG_X28, DATA)
        a.run(0x53cef4, 0x53ce4c if state == 1 else 0x508d84)
        if state != 1:
            assert a.args()[0] == 6
            a.set(UC_ARM64_REG_X0, DATA + 32)
            a.run(0x53cf2c, 0x508d90)
            assert a.uc.mem_read(DATA + 32, 4) == struct.pack("<HH", 101, 0)
    a.set(UC_ARM64_REG_X0, 0)
    a.run(0x53cf2c, 0x53ce30)  # Allocation failure, no enqueue.
    a.set(UC_ARM64_REG_SP, STACK)
    a.q(STACK + 0x88, DATA + 64)
    a.run(0x52fe6c, 0x6e5580)
    assert a.args()[:2] == (DATA + 64, 0)
    print("PASS: RX-ready state 0/6 -> message101 -> main_flow(callback,0); state1/allocation failure excluded")


def output_gate_tests(path):
    a = Audit(path)
    a.q(0x6e7190, DATA + 16)
    a.q(0x6e7170, DATA + 32)
    for ready in (0, 1):
        calls = []
        a.uc.mem_write(DATA, bytes([ready]))
        a.set(UC_ARM64_REG_X23, DATA)
        a.set(UC_ARM64_REG_X19, STOP + 0x100)
        a.mock(0x53457c, lambda args: calls.append("config/output") or 0)
        # Deliberate negative getter/output status: callback0 is still emitted.
        a.mock(0x534b8c, lambda args: calls.append("position/output") or 0xffffffff)
        a.mock(STOP + 0x100, lambda args: calls.append(("callback", args[0])) or 0)
        a.run(0x533674, 0x5336dc if ready else 0x5337b0)
        assert calls == (["config/output", "position/output", ("callback", 0)] if ready else [])
        assert a.uc.mem_read(DATA, 1) == b"\0"
    for result in (0, 18, 0xffffffff):
        a.set(UC_ARM64_REG_X0, result)
        a.run(0x534c88, 0x534ccc if result == 0 else 0x534c8c)
    print("PASS: output-ready flag gate; callback0 is not a fix; get_position requires return0")


def main():
    path = Path(sys.argv[1])
    dispatch_tests(path)
    for secondary, state in ((0, 0), (1, 0), (0, 1)):
        config_wire_test(path, secondary, state=state)
    config_wire_test(path, 0, missing_primary=True)
    print("PASS: missing lower-sender context logs without a frame; no ready-state inference")
    feed_tests(path)
    output_gate_tests(path)
    print("OFFLINE ONLY: queues/logging mocked; no DSP, I/O, full engine or position execution")


if __name__ == "__main__":
    main()
