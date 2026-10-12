#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Bounded, identity-pinned RV33 static audit. Never execute firmware or emit it.

Requires Capstone 5.0.6. Input is the private authenticated primary snapshot,
not a firmware container. Caller-CFG dominance assumes calls return to their
link address; opaque callees prevent an unconditional whole-startup proof.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile

import capstone
from capstone import Cs, CS_ARCH_ARM64, CS_ARCH_RISCV, CS_MODE_ARM
from capstone import CS_MODE_RISCV32, CS_MODE_RISCVC
from capstone.riscv import RISCV_OP_IMM, RISCV_OP_REG


PRIMARY_BYTES = 156064
PRIMARY_SHA = "9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7"
LK_SHA = "431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a"
LK_LIMIT = 8 * 1024 * 1024
MAX_INSTRUCTIONS = 512
WINDOWS = (
    (0, 0x20, "b3b0759707783a40cec87990cdfd18b321aba0dc6db08bd8364a1d1ffe2318f0"),
    (0xac, 0x354, "e1bd07da5daf0026e0dc2060fa7396f4d00f97fd6fe653dec999b0a655191224"),
    (0x1da8, 0x1dbc, "91d1d3237cbbd19d6ce0b79e9a52a28e80d5c23d4e1c757d85abcc6a968fcd2d"),
    (0x1df8, 0x1eb4, "b1ca72254efc65a9eb1da51478244860ab266300bc91610fe05bbd0abf564959"),
    (0x1eb0, 0x1ec4, "3de1686c3a2a477c4d4d8ba164a4074e3c6d5c595a088b268f35699304e4827b"),
    (0x107fe, 0x10814, "66a5aaff1398578397b3a4abcf3170a656b51c100616bb28ca1a88b7a7974856"),
    (0x10078, 0x10098, "3cb8816c753749acbf3141b506e6d3bc2b520454793ced08d047b83a39eb0f12"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decoder():
    require(capstone.__version__ == "5.0.6", "unsupported decoder version")
    result = Cs(CS_ARCH_RISCV, CS_MODE_RISCV32 | CS_MODE_RISCVC)
    result.detail = True
    return result


def decode_window(data, start, end, opaque=()):
    """No resynchronization or skipdata; declared opaque words stay opaque."""
    require(0 <= start < end <= len(data) and start % 2 == end % 2 == 0,
            "invalid decode bounds")
    engine, instructions, pc = decoder(), {}, start
    opaque = frozenset(opaque)
    require(all(start <= address < end and address % 2 == 0 for address in opaque),
            "opaque address outside window")
    while pc < end:
        require(len(instructions) < MAX_INSTRUCTIONS, "decode budget exceeded")
        half = int.from_bytes(data[pc:pc + 2], "little")
        require(half & 0x1f != 0x1f, "unsupported long instruction")
        width = 2 if half & 3 != 3 else 4
        require(pc + width <= end, "instruction crosses decode boundary")
        decoded = list(engine.disasm(data[pc:pc + width], pc, count=1))
        if pc in opaque:
            require(width == 4 and not decoded, "opaque instruction profile changed")
            instructions[pc] = None
        else:
            require(len(decoded) == 1 and decoded[0].address == pc and
                    decoded[0].size == width, "undecoded instruction")
            instructions[pc] = decoded[0]
        pc += width
    require(opaque <= instructions.keys(), "opaque address is not an instruction boundary")
    return instructions


def expect(code, address, mnemonic, operands):
    instruction = code.get(address)
    require(instruction is not None and instruction.mnemonic == mnemonic and
            instruction.op_str == operands, "instruction profile mismatch")
    return instruction


def immediate(instruction):
    require(instruction.operands and instruction.operands[-1].type == RISCV_OP_IMM,
            "missing immediate operand")
    return instruction.operands[-1].imm


def relative_target(instruction):
    require(instruction.mnemonic in {"j", "jal", "beq", "beqz", "bgeu", "bltu"},
            "unsupported relative control transfer")
    target = instruction.address + immediate(instruction)
    require(0 <= target < PRIMARY_BYTES and target % 2 == 0,
            "control target outside signed primary")
    return target


def address_pair(code, first, second, register, upper="auipc"):
    a, b = code[first], code[second]
    require(a is not None and b is not None and a.mnemonic == upper and
            b.mnemonic == "addi", "address producer mismatch")
    require(len(a.operands) == 2 and a.operands[0].type == RISCV_OP_REG and
            a.reg_name(a.operands[0].reg) == register and
            len(b.operands) == 3 and
            all(o.type == RISCV_OP_REG and b.reg_name(o.reg) == register
                for o in b.operands[:2]), "address register mismatch")
    high = immediate(a)
    require(0 <= high < 1 << 20, "invalid upper immediate")
    high = high - (1 << 20) if high & (1 << 19) else high
    return ((a.address if upper == "auipc" else 0) +
            (high << 12) + immediate(b)) & 0xffffffff


def caller_dominators(code):
    """Static caller graph only: every jal has a conditional return edge."""
    edges = {}
    for pc, ins in code.items():
        require(ins is not None, "opaque caller instruction")
        next_pc = pc + ins.size
        if ins.mnemonic == "j":
            successors = [relative_target(ins)]
        elif ins.mnemonic in {"beq", "beqz"}:
            successors = [relative_target(ins), next_pc]
        elif ins.mnemonic == "jal":
            relative_target(ins)
            successors = [next_pc]
        else:
            successors = [next_pc]
        for target in successors:
            if 0 <= target < 4 or 0xac <= target < 0x354:
                require(target in code, "caller edge is not an instruction boundary")
        edges[pc] = [target for target in successors if target in code]
    reachable, pending = set(), [0]
    while pending:
        pc = pending.pop()
        if pc not in reachable:
            reachable.add(pc)
            pending.extend(edges[pc])
    parents = {pc: set() for pc in reachable}
    for pc in reachable:
        for target in edges[pc]:
            parents[target].add(pc)
    dom = {pc: ({0} if pc == 0 else set(reachable)) for pc in reachable}
    changed = True
    while changed:
        changed = False
        for pc in sorted(reachable - {0}):
            candidate = {pc} | set.intersection(*(dom[p] for p in parents[pc]))
            if candidate != dom[pc]:
                dom[pc], changed = candidate, True
    return dom


def prove_layout(data):
    """Internal semantic checks, also exercised with mutations by unit tests.

    Production admission is audit(), which additionally requires both identities
    and window pins. This function does not admit alternate firmware profiles.
    """
    require(len(data) == PRIMARY_BYTES, "wrong primary size")
    require(struct.unpack_from("<8I", data) ==
            (0x0ac0006f, 0, 0, 0, 0, 0, 0, 0x1b170), "header profile mismatch")
    code = decode_window(data, 0, 4)
    code.update(decode_window(data, 0xac, 0x354))
    checks = (
        (0, "j", "0xac"),
        (0xac, "lui", "t0, 0x40"), (0xb0, "addi", "t0, t0, -0x288"),
        (0xb4, "lw", "t1, 0(t0)"), (0xb8, "addi", "t2, zero, 7"),
        (0xbc, "and", "t1, t1, t2"), (0xc0, "addi", "t2, zero, 7"),
        (0xc4, "beq", "t1, t2, 8"), (0xc8, "j", "0x7c"),
        (0x144, "lui", "t0, 0x40"), (0x148, "addi", "t0, t0, -0x2e0"),
        (0x14c, "lw", "t1, 0(t0)"), (0x150, "beqz", "t1, 8"),
        (0x154, "j", "0x1d30"), (0x15c, "jal", "gp, 0x1cdc"),
        (0x268, "jal", "0x1c48"),
        (0x30c, "mv", "a2, zero"), (0x310, "jal", "0x1a98"),
        (0x324, "mv", "a2, zero"), (0x328, "jal", "0x1a80"),
        (0x33c, "lui", "a2, 0xababb"), (0x340, "addi", "a2, a2, -0x455"),
        (0x344, "jal", "0x1a64"), (0x350, "j", "0x12ee0"),
    )
    for check in checks:
        expect(code, *check)
    helper = decode_window(data, 0x1da8, 0x1dbc)
    for check in ((0x1da8, "bgeu", "a0, a1, 0x10"),
                  (0x1dac, "sw", "a2, 0(a0)"),
                  (0x1db0, "addi", "a0, a0, 4"),
                  (0x1db4, "j", "-0xc"), (0x1db8, "ret", "")):
        expect(helper, *check)
    require(relative_target(helper[0x1da8]) == 0x1db8 and
            relative_target(helper[0x1db4]) == 0x1da8, "fill loop control mismatch")
    dom = caller_dominators(code)
    for site in (0x310, 0x328, 0x344):
        require({0xc4, 0xc8, 0x144, 0x150, 0x158} <= dom[site] and
                0xcc not in dom[site] and 0x154 not in dom[site],
                "cold caller dominance failed")
        require(relative_target(code[site]) == 0x1da8, "wrong fill helper")
    fills = []
    for first, second, site, label in ((0x2fc, 0x304, 0x310, "bss_zero"),
                                      (0x314, 0x31c, 0x328, "empty_zero"),
                                      (0x32c, 0x334, 0x344, "stack_pattern")):
        start = address_pair(code, first, first + 4, "a0")
        end = address_pair(code, second, second + 4, "a1")
        require(0 <= start <= end <= len(data) and start % 4 == end % 4 == 0,
                "fill range outside signed primary or unaligned")
        fills.append({"kind": label, "call": site, "start": start,
                      "end_exclusive": end, "bytes": end - start,
                      "word": 0 if label != "stack_pattern" else
                      address_pair(code, 0x33c, 0x340, "a2", "lui")})
    require([(f["start"], f["end_exclusive"]) for f in fills] ==
            [(0x1b538, 0x2619c), (0x1b538, 0x1b538), (0x18c00, 0x197f0)],
            "fill range profile mismatch")
    require(fills[2]["word"] == 0xabababab, "stack pattern mismatch")
    require(not any(data[0x1b538:0x2619c]), "primary BSS is not all zero")
    stack = address_pair(code, 0x348, 0x34c, "sp")
    require(stack == fills[2]["end_exclusive"], "stack pointer mismatch")

    # The alternate path reuses a checked loop; it is not the BSS fill helper.
    copy = decode_window(data, 0x1df8, 0x1eb0)
    for check in (
        (0x1df8, "mv", "t5, zero"), (0x1e04, "lw", "t0, 0(t0)"),
        (0x1e08, "srli", "t0, t0, 0x1c"), (0x1e0c, "slli", "t1, t0, 4"),
        (0x1e10, "or", "t1, t1, t5"), (0x1e20, "ret", ""),
        (0x1e24, "lui", "t5, 0x50000"), (0x1e28, "slli", "t4, t4, 4"),
        (0x1e2c, "srli", "t4, t4, 4"), (0x1e30, "add", "t4, t4, t5"),
        (0x1e34, "ret", ""), (0x1e38, "jal", "-0x40"),
        (0x1e3c, "mv", "t2, zero"), (0x1e48, "lw", "t4, 8(t0)"),
        (0x1e4c, "jal", "-0x28"), (0x1e50, "mv", "t3, t4"),
        (0x1e54, "lw", "t1, 0xc(t0)"), (0x1e58, "lw", "t0, 4(t0)"),
        (0x1e5c, "j", "0x1c"), (0x1e64, "add", "t5, t3, t2"),
        (0x1e68, "lw", "t4, 0(t5)"), (0x1e6c, "add", "t5, t0, t2"),
        (0x1e70, "sw", "t4, 0(t5)"), (0x1e74, "addi", "t2, t2, 4"),
        (0x1e78, "bltu", "t2, t1, -0x14"), (0x1e7c, "jr", "gp"),
        (0x1e84, "jal", "-0x8c"), (0x1e88, "mv", "t2, zero"),
        (0x1e94, "lw", "t4, 0x10(t0)"), (0x1e98, "jal", "-0x74"),
        (0x1e9c, "lui", "t1, 0x40"), (0x1ea0, "mv", "t3, zero"),
        (0x1ea4, "mv", "t0, t4"), (0x1ea8, "jal", "gp, -0x30"),
    ):
        expect(copy, *check)
    for first, second in ((0x1dfc, 0x1e00), (0x1e40, 0x1e44), (0x1e8c, 0x1e90)):
        require(address_pair(copy, first, second, "t0") == 4, "copy header address mismatch")
    for site, target in ((0x1e38, 0x1df8), (0x1e4c, 0x1e24), (0x1e5c, 0x1e78),
                         (0x1e78, 0x1e64), (0x1e84, 0x1df8), (0x1e98, 0x1e24),
                         (0x1ea8, 0x1e78)):
        require(relative_target(copy[site]) == target, "copy control mismatch")
    require(relative_target(code[0x154]) == 0x1e84 and
            relative_target(code[0x15c]) == 0x1e38, "alternate copy route mismatch")
    require(address_pair(code, 0xac, 0xb0, "t0", "lui") == 0x3fd78 and
            address_pair(code, 0x144, 0x148, "t0", "lui") == 0x3fd20,
            "startup selector address mismatch")
    opaque = decode_window(data, 0x1eb0, 0x1ec4, (0x1eb0, 0x1eb4, 0x1eb8, 0x1ebc))
    expect(opaque, 0x1ec0, "ret", "")
    require(relative_target(code[0x268]) == 0x1eb0, "opaque cold callee mismatch")
    warm = decode_window(data, 0x107fe, 0x10814, (0x10810,))
    expect(warm, 0x107fe, "lui", "a0, 0x26")
    expect(warm, 0x1080e, "c.mv", "a1, a0")
    require(address_pair(warm, 0x107fe, 0x10806, "a0", "lui") == 0x26158,
            "warm operand producer mismatch")
    pointers = decode_window(data, 0x10078, 0x10098)
    for check in ((0x1007c, "lui", "a0, 0x24"), (0x10084, "sw", "a1, -0x494(a0)"),
                  (0x1008c, "lui", "a0, 0x24"), (0x10094, "sw", "a1, -0x490(a0)")):
        expect(pointers, *check)
    require(address_pair(pointers, 0x10078, 0x10080, "a1", "lui") == 0x3f2b8 and
            address_pair(pointers, 0x10088, 0x10090, "a1", "lui") == 0x3f6b8,
            "post-copy pointer producer mismatch")
    return {
        "entry": 0xac,
        "selection": {"gpr": 0x3fd78, "mask": 7, "warm_if_equal": 7,
                      "warm_target": relative_target(code[0xc4]),
                      "cold_target": relative_target(code[0xc8]),
                      "alternate_gpr": 0x3fd20, "continue_cold_if": 0},
        "fills": fills, "stack_pointer": stack,
        "caller_dominance": {
            "proven": True, "dominating_cold_nodes": [0xc8, 0x144, 0x150, 0x158],
            "scope": "bounded caller CFG; assumes callees return to link addresses",
            "unconditional_startup_proven": False,
            "barrier": {"call": 0x268, "opaque_start": 0x1eb0, "opaque_end": 0x1ec0}},
        "early_copy": {"call": 0x15c, "helper": 0x1e38, "header_size": 0,
                       "source_reads": 0, "reason": "pretest t2=0 < header count=0 is false"},
        "alternate_tail_consumer": {
            "condition": "GPR 0x3fd78 & 7 != 7 and GPR 0x3fd20 != 0",
            "helper": 0x1e84, "load_instruction": 0x1e68,
            "source_start": 0, "source_end_exclusive": 0x40000,
            "destination_start": 0x50000000,
            "scope": "local copy-loop semantics; reachability and physical alias ownership unproven",
            "requires_initial_tail_payload": "unresolved; consuming SRAM does not prove its initial producer"},
        "opaque_warm_operand": {"instruction": 0x10810, "a0_a1": 0x26158,
                                "semantics": "opaque RV33/vendor instruction; no inferred memory access"},
        "post_copy_pointer_producers": {
            "instructions": [0x10084, 0x10094], "values": [0x3f2b8, 0x3f6b8],
            "stored_at": [0x23b6c, 0x23b70],
            "scope": "pointer stores only; later consumers and reachability unproven"},
    }


def prove_lk(container):
    require(512 <= len(container) <= LK_LIMIT, "invalid LK size")
    header = container[:512]
    magic, size = struct.unpack_from("<II", header)
    require(magic == 0x58881688 and header[8:40] == b"lk".ljust(32, b"\0") and
            struct.unpack_from("<II", header, 48) == (0x58891689, 512) and
            0 < size <= len(container) - 512, "LK header mismatch")
    code = container[512:512 + size]
    require(hashlib.sha256(code).hexdigest() == LK_SHA, "LK identity mismatch")
    engine = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    for pc, mnemonic, operands in (
        (0x1ede8, "mov", "w2, #0x40000"), (0x1edfc, "bl", "#0x6a98c"),
        (0x1ee00, "mov", "w8, #0xf2bc"), (0x1ee04, "movk", "w8, #3, lsl #16"),
        (0x1ee08, "ldr", "w9, [x23], #4"), (0x1ee0c, "sub", "w8, w8, #4"),
        (0x1ee10, "cmp", "w8, #4"), (0x1ee14, "str", "w9, [x26], #4"),
        (0x1ee18, "b.hi", "#0x1ee08"),
    ):
        ins = list(engine.disasm(code[pc:pc + 4], pc, count=1))
        require(len(ins) == 1 and ins[0].size == 4 and ins[0].mnemonic == mnemonic and
                ins[0].op_str == operands, "LK copy profile mismatch")
    return {"payload_sha256": LK_SHA, "copy_bytes": 0x3f2bc - 4,
            "clear_bytes": 0x40000, "copy_loop": 0x1ee08,
            "scope": "pinned B4.1 LK caller instructions; no secure-handler execution"}


def audit(primary, lk_container):
    require(len(primary) == PRIMARY_BYTES and
            hashlib.sha256(primary).hexdigest() == PRIMARY_SHA, "primary identity mismatch")
    for start, end, digest in WINDOWS:
        require(hashlib.sha256(primary[start:end]).hexdigest() == digest,
                "window identity mismatch")
    result = prove_layout(primary)
    lk = prove_lk(lk_container)
    result.update({
        "schema": 1, "decoder": capstone.__version__,
        "primary": {"bytes": PRIMARY_BYTES, "sha256": PRIMARY_SHA,
                    "identity_basis": "parent-provided authenticated leaf digest; not re-authenticated here"},
        "lk": lk,
        "layout_gap": {"start": PRIMARY_BYTES, "end_exclusive": lk["copy_bytes"],
                       "bytes": lk["copy_bytes"] - PRIMARY_BYTES,
                       "classification": "unknown LK copy source tail; not BSS",
                       "bss_end_to_primary_end_bytes": PRIMARY_BYTES - 0x2619c,
                       "stock_clear_only_start": lk["copy_bytes"],
                       "stock_clear_only_end_exclusive": lk["clear_bytes"],
                       "cold_fill_overlap_bytes": 0},
        "conclusion": {
            "selected_text_and_fill_ranges_inside_primary": True,
            "all_required_initial_sram_text_data_proven": False,
            "tail_initialization_producer": "unresolved",
            "remaining_gap": "unknown cold callee effects/control; transitive/indirect/interrupt accesses; LK source-tail producer",
            "activation_permitted": False,
            "scope": "bounded static disassembly and checked instruction semantics; no emulation or firmware execution"},
    })
    return result


def read_bounded(path, limit, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
                "input is not a bounded regular file")
        require(not private or before.st_mode & 0o077 == 0, "snapshot permissions are not private")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(data) == before.st_size and before.st_size == after.st_size and
                before.st_mtime_ns == after.st_mtime_ns and
                before.st_ctime_ns == after.st_ctime_ns, "input changed during read")
        return data


def write_atomic(path, report, inputs):
    path = Path(path)
    for source in inputs:
        require(path.resolve() != Path(source).resolve() and
                not (path.exists() and os.path.samefile(path, source)), "output aliases input")
    fd, temporary = tempfile.mkstemp(prefix=".rv33-audit-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--lk", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit(read_bounded(args.snapshot, PRIMARY_BYTES, private=True),
                       read_bounded(args.lk, LK_LIMIT))
        if args.output:
            write_atomic(args.output, report, (args.snapshot, args.lk))
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
    except Exception as error:
        parser.exit(1, f"RV33 static audit failed ({type(error).__name__}); no report published\n")


if __name__ == "__main__":
    main()
