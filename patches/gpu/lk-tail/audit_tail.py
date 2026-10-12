#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""B4.1 LK source-tail evidence candidate; static inspection, never execution.

Exit 0 means a valid evidence report, NOT a completed producer proof.
--require-closure exits 2 while any writer/caller obligation is unresolved.
No RV33 instruction is decoded. No private bytes are emitted.
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
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM, CS_AC_WRITE, CS_GRP_JUMP
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM

LK_SHA = "431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a"
PRIMARY_SHA = "9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7"
PRIMARY_BYTES = 0x261a0
COPY_BYTES = 0x3f2b8
LIMIT = 8 * 1024 * 1024
MAX_INSTRUCTIONS = 4096

# Complete contiguous instruction windows, not isolated matching instructions.
# The top caller ends at the copy-loop exit, not at a function return.
WINDOWS = (
    ("caller", 0x1ec54, 0x1ee1c, "7cb863d962350735da608ab11d29f3260d07ea16ba6951f193496a5d8edd11ba"),
    ("reserve", 0x140ec, 0x14190, "a35e3b4eb57666ffd1d3879cc14ce8d11039e30ae90339740caac5197ec4fed1"),
    ("mblock", 0x14190, 0x148dc, "716f8c4493d0743ce142f28671c29f1e49ba85d5f206b613885090ef77254b20"),
    ("mblock_merge", 0x16acc, 0x16c00, "6481f869901571070b84c45905e7c73e85ebb096484ff550447cee2440383ead"),
    ("high_address_selector", 0x16ec0, 0x16ec8, "2b59db05426e0f313d72b30f3398c65721de2562a59dc46ceeba224f98d0b876"),
    ("map", 0x67894, 0x67a38, "b1188cb9a3973715062a48608a66cf9ca1b807a72d5d92cd380b4a82334db597"),
    ("map_descriptor", 0x675c0, 0x67894, "ba44571452bf80b79d6ab94b649a56017a29a594a2d923a92a9ad30b9c6e0926"),
    ("arch_map", 0x6f94, 0x71d4, "a52b22676c82b997e6f930efd43acf803471175f45315423dc2ea02173939064"),
    ("page_table", 0x6a18, 0x6d6c, "db087abcb77d9c93d1b6081049a3c085e647d4234eece7476e20c68b9ce5af6c"),
    ("loader", 0x74da0, 0x7524c, "37fbf6132fc3fbf21e3cd3a9918b348d600933ee1e0f879a4a957d242eea4434"),
    ("post_load", 0x7db00, 0x7dcec, "36b4f576ddc910ca0b65547c17f0377ef9b433b7475f66593e6c4704d6b0c00e"),
    ("strcmp", 0x6ab24, 0x6ab44, "907f0ab9a83415ae47b60ebc724515131a5e76dbee70db3d39c951049fe5d73e"),
    ("cache", 0x5e74, 0x5e94, "5bf61889c1dd84c7bc0af3de04aff0e963802683aab8753eb5d534fcc5c7e36a"),
    ("memset", 0x6a98c, 0x6aaf8, "b9a5950864ab631a1874cceb62fbe869f43759eaa5aab1faf4949302b9d12e0a"),
    ("logger", 0x69c28, 0x69cf8, "fdd21e44465c449759253ead7a1894ec58bc747b4f68de3285d5fe3fe834f6c3"),
    ("byte_reader_dispatch", 0x67edc, 0x67f0c, "93c30eca152109a73862c45339ad6e226bee65c49ab3e5f6d92faa040acf96d5"),
    ("allocator_name_copy", 0x6ace8, 0x6ad7c, "e758321b01e31f7a7c9a73fca67e102960aeefc36096d6021f88b2dd797aed04"),
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(data, start, end):
    require(capstone.__version__ == "5.0.6", "Capstone 5.0.6 required")
    require(0 <= start < end <= len(data) and start % 4 == end % 4 == 0,
            "invalid window")
    require((end - start) // 4 <= MAX_INSTRUCTIONS, "instruction budget")
    engine = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    engine.detail = True
    ins = list(engine.disasm(data[start:end], start))
    require(len(ins) == (end - start) // 4 and
            all(i.address == start + n * 4 and i.size == 4 for n, i in enumerate(ins)),
            "incomplete decode")
    return {i.address: i for i in ins}


def expect(code, pc, mnemonic, operands):
    i = code.get(pc)
    require(i is not None and (i.mnemonic, i.op_str) == (mnemonic, operands),
            f"instruction mismatch at {pc:#x}")


def target(i):
    require(i.operands and i.operands[-1].type == ARM64_OP_IMM,
            "non-direct transfer")
    return i.operands[-1].imm


def cfg(code, entry, decisions=None, jump_edges=None):
    """Caller CFG only. Calls MAY return; every callee remains an obligation.

    Decisions are supplied only by the separately checked local semantic
    proofs below. No machine state is run or emulated, and no generic branch
    feasibility is inferred. Unknown indirect jumps end in explicit frontiers.
    """
    decisions = decisions or {}
    jump_edges = jump_edges or {}
    require(entry in code, "entry outside window")
    edges, external, pending, reached = {}, [], [entry], set()
    while pending:
        pc = pending.pop()
        if pc in reached:
            continue
        reached.add(pc)
        require(len(reached) <= MAX_INSTRUCTIONS, "CFG budget")
        i = code[pc]
        if i.mnemonic == "ret":
            successors = []
        elif pc in jump_edges:
            require(i.mnemonic == "br" and jump_edges[pc] and
                    all(dest in code for dest in jump_edges[pc]), "invalid jump table")
            successors = jump_edges[pc]
        elif i.mnemonic in {"br", "eret", "smc", "hvc", "svc", "brk"}:
            external.append({"site": pc, "kind": i.mnemonic, "target": None})
            successors = []
        elif i.mnemonic in {"bl", "blr"}:
            successors = [pc + 4]
        elif i.mnemonic == "b":
            successors = [target(i)]
        elif i.group(CS_GRP_JUMP):
            successors = [target(i), pc + 4]
        else:
            successors = [pc + 4]
        if pc in decisions:
            require(len(successors) == 2 and decisions[pc] in successors,
                    "invalid branch decision")
            successors = [decisions[pc]]
        edges[pc] = successors
        for dest in successors:
            if dest in code:
                pending.append(dest)
            else:
                external.append({"site": pc, "kind": "window_exit", "target": dest})
    require(set(decisions) <= reached, "unused branch decision")
    require(set(jump_edges) <= reached, "unused jump table")
    return reached, edges, external


def memory_writers(code):
    result = []
    for pc, i in sorted(code.items()):
        memory = [o for o in i.operands if o.type == ARM64_OP_MEM]
        writes = [o for o in memory if o.access & CS_AC_WRITE]
        # Include store families even when decoder access metadata is absent.
        if writes or (memory and i.mnemonic.startswith(("st", "cas", "swp"))):
            result.append({"site": pc, "operation": i.mnemonic,
                           "bases": [i.reg_name(o.mem.base) for o in memory],
                           "alias_proof": "not established by census"})
        elif i.mnemonic in {"dc", "sys", "msr", "smc", "hvc", "svc"}:
            result.append({"site": pc, "operation": i.mnemonic,
                           "bases": [], "alias_proof": "system effect; requires separate contract"})
    return result


def mapper_tables(payload, code):
    """Resolve all four signed table entries from the checked two-bit index."""
    for check in (
        (0x702c, "adrp", "x12, #0xce000"), (0x7030, "add", "x12, x12, #0xbc"),
        (0x7038, "ubfx", "w11, w8, #2, #2"), (0x703c, "adr", "x13, #0x703c"),
        (0x7040, "ldrsw", "x14, [x12, x11, lsl #2]"),
        (0x7044, "add", "x13, x13, x14"), (0x7048, "br", "x13"),
        (0x7060, "adr", "x12, #0xce0ac"),
        (0x7068, "ubfx", "w11, w8, #2, #2"), (0x706c, "adr", "x13, #0x706c"),
        (0x7070, "ldrsw", "x14, [x12, x11, lsl #2]"),
        (0x7074, "add", "x13, x13, x14"), (0x7078, "br", "x13"),
    ):
        expect(code, *check)
    result = {}
    for site, table, base, expected in (
        (0x7048, 0xce0bc, 0x703c, (84, 16, 72, 80)),
        (0x7078, 0xce0ac, 0x706c, (184, 16, 172, 180)),
    ):
        offsets = struct.unpack_from("<4i", payload, table)
        require(offsets == expected, "mapper table changed")
        destinations = [base + offset for offset in offsets]
        require(all(0x6f94 <= dest < 0x71d4 and dest in code for dest in destinations),
                "mapper table escapes window")
        result[site] = destinations
    return result


def allocator_name_copy_contract(code):
    """Close one leaf writer's bounds, without assuming its destination aliases.

    This is a fixed instruction/CFG proof, not execution or emulation. At
    entry let D=x0, S=x1, n=x2. The byte loop writes offsets 0 through n-1,
    stopping at a first NUL k. Padding then covers [k, n): even pairs followed
    by at most one residual byte. All stores derive from D; no stack stores,
    calls or system effects exist. Valid nonwrapping buffers are a precondition.
    """
    start, end = 0x6ace8, 0x6ad7c
    leaf = {pc: i for pc, i in code.items() if start <= pc < end}
    require(set(leaf) == set(range(start, end, 4)), "incomplete name-copy leaf")
    instructions = (
        ("mov", "x8, xzr"), ("cbz", "x2, #0x6ad0c"),
        ("ldrb", "w9, [x1, x8]"), ("strb", "w9, [x0, x8]"),
        ("cbz", "w9, #0x6ad1c"), ("add", "x8, x8, #1"),
        ("cmp", "x2, x8"), ("b.ne", "#0x6acf0"),
        ("b", "#0x6ad78"), ("mov", "x11, x0"),
        ("cmp", "x8, x2"), ("b.lo", "#0x6ad28"),
        ("b", "#0x6ad78"), ("add", "x11, x0, x8"),
        ("cmp", "x8, x2"), ("b.hs", "#0x6ad78"),
        ("sub", "x10, x2, x8"), ("cmp", "x10, #2"),
        ("b.hs", "#0x6ad3c"), ("mov", "x9, x11"),
        ("b", "#0x6ad68"), ("and", "x12, x10, #0xfffffffffffffffe"),
        ("add", "x8, x8, x12"), ("add", "x9, x11, x12"),
        ("add", "x11, x11, #1"), ("mov", "x13, x12"),
        ("sturh", "wzr, [x11, #-1]"), ("add", "x11, x11, #2"),
        ("subs", "x13, x13, #2"), ("b.ne", "#0x6ad50"),
        ("cmp", "x10, x12"), ("b.eq", "#0x6ad78"),
        ("sub", "x8, x2, x8"), ("subs", "x8, x8, #1"),
        ("strb", "wzr, [x9], #1"), ("b.ne", "#0x6ad6c"),
        ("ret", ""),
    )
    require(len(instructions) == len(leaf), "name-copy proof coverage")
    for offset, (mnemonic, operands) in enumerate(instructions):
        expect(leaf, start + 4 * offset, mnemonic, operands)
    for check in (
        (0x145b4, "bl", "#0x6ac9c"), (0x145b8, "cmp", "x0, #0x7f"),
        (0x145bc, "b.hi", "#0x14618"), (0x145c0, "mov", "x2, x0"),
        (0x145c4, "mov", "x0, x27"), (0x145c8, "mov", "x1, x19"),
        (0x145cc, "bl", "#0x6ace8"),
    ):
        expect(code, *check)
    caller = {pc: i for pc, i in code.items() if 0x14190 <= pc < 0x148dc}
    reached, edges, _ = cfg(caller, 0x14190)
    require(0x145cc in reached, "name-copy call unreachable")
    # Check every incoming edge to the argument block, including error paths
    # whose callees may return. No path may enter after the unsigned cap.
    for pc in range(0x145bc, 0x145d0, 4):
        incoming = {source for source, targets in edges.items() if pc in targets}
        require(incoming == {pc - 4}, "name-copy count guard bypass")
    leaf_reached, _, exits = cfg(leaf, start)
    require(leaf_reached == set(leaf) and not exits, "name-copy leaf CFG escapes")
    require(not any(i.mnemonic in {"bl", "blr"} for i in leaf.values()),
            "name-copy leaf has calls")
    require([(w["site"], w["operation"], w["bases"]) for w in memory_writers(leaf)] ==
            [(0x6acf4, "strb", ["x0"]), (0x6ad50, "sturh", ["x11"]),
             (0x6ad70, "strb", ["x9"])], "name-copy writer set changed")
    return {
        "call": 0x145cc, "entry": start, "end_exclusive": end,
        "callee_transitive_write_extent_proven": True,
        "destination": "caller x27 (allocator record name field)",
        "source": "caller x19 (allocation name)",
        "count": "unsigned x0 after 0x145b4, capped by 0x145b8/0x145bc",
        "count_range_inclusive": [0, 127],
        "write_interval_relative_to_destination": "[0, count)",
        "maximum_write_interval_relative_to_destination": [0, 127],
        "read_interval_relative_to_source": "[0, count); stops after first NUL",
        "return": "original destination x0; unchanged",
        "zero_count_writes": False,
        "padding": "after first NUL k, zeroes [k, count); no extra terminator",
        "writer_sites": [0x6acf4, 0x6ad50, 0x6ad70],
        "nested_calls": [], "system_effects": [], "window_exits": exits,
        "preconditions": "valid nonwrapping buffers; normal AAPCS64 returns; no async writers",
        "strlen_behavior_proven": False,
        "destination_nonalias_with_staging_proven": False,
        "initializes_source_tail_proven": False,
        "remaining_obligation": "allocator record destination must be proven disjoint from staging",
    }


def local_proofs(code, payload):
    checks = (
        (0x16ec0, "mov", "w0, wzr"), (0x16ec4, "ret", ""),
        (0x1ec80, "bl", "#0x16ec0"), (0x1ec84, "cbz", "w0, #0x1ed30"),
        (0x1ed74, "ldr", "x8, [sp, #8]"),
        (0x1ed8c, "add", "x23, x8, #0x18"),
        (0x1ed90, "mov", "x2, x23"), (0x1ed94, "bl", "#0x74da0"),
        (0x1ed98, "tbnz", "w0, #0x1f, #0x1ee84"),
        (0x1ed9c, "ldr", "x0, [sp, #8]"), (0x1eda0, "mov", "w1, #0x100000"),
        (0x1edbc, "bl", "#0x5e74"), (0x1edd0, "bl", "#0x69c28"),
        (0x1edd8, "mov", "x0, #0x13c00000"),
        (0x1ede0, "movk", "x0, #0xffff, lsl #48"),
        (0x1ede4, "mov", "w1, wzr"), (0x1ede8, "mov", "w2, #0x40000"),
        (0x1edec, "mov", "x26, #0x13c00000"),
        (0x1edf4, "movk", "x26, #0xffff, lsl #48"),
        (0x1edfc, "bl", "#0x6a98c"),
        (0x1ee00, "mov", "w8, #0xf2bc"), (0x1ee04, "movk", "w8, #3, lsl #16"),
        (0x1ee08, "ldr", "w9, [x23], #4"), (0x1ee0c, "sub", "w8, w8, #4"),
        (0x1ee10, "cmp", "w8, #4"), (0x1ee14, "str", "w9, [x26], #4"),
        (0x1ee18, "b.hi", "#0x1ee08"),
        (0x5e74, "add", "x2, x0, x1"),
        (0x5e78, "and", "x3, x0, #0xffffffffffffffc0"),
        (0x5e7c, "dc", "civac, x3"), (0x5e80, "add", "x3, x3, #0x40"),
        (0x5e84, "cmp", "x3, x2"), (0x5e88, "b.lo", "#0x5e7c"),
        (0x5e8c, "dsb", "sy"), (0x5e90, "ret", ""),
        (0x74dc8, "mov", "x21, x2"), (0x75180, "ldr", "w25, [x19, #4]"),
        (0x75024, "mov", "x1, x21"), (0x7502c, "mov", "x3, x25"),
        (0x75030, "bl", "#0x67edc"),
        (0x750ec, "add", "x0, x19, #8"), (0x750f0, "mov", "x1, x21"),
        (0x750f4, "mov", "x2, x25"), (0x750f8, "bl", "#0x7db00"),
        (0x7db20, "mov", "x19, x0"),
        (0x7db38, "adrp", "x1, #0xb8000"), (0x7db3c, "add", "x1, x1, #0xf5"),
        (0x7db40, "mov", "x0, x19"), (0x7db48, "bl", "#0x6ab24"),
        (0x7db4c, "cbnz", "w0, #0x7dbbc"),
        (0x7dbbc, "adrp", "x1, #0xc9000"), (0x7dbc0, "add", "x1, x1, #0xecb"),
        (0x7dbc4, "mov", "x0, x19"), (0x7dbc8, "bl", "#0x6ab24"),
        (0x7dbcc, "cbnz", "w0, #0x7dc3c"),
        (0x7dc3c, "adrp", "x1, #0xb0000"), (0x7dc40, "add", "x1, x1, #0x829"),
        (0x7dc44, "mov", "x0, x19"), (0x7dc48, "bl", "#0x6ab24"),
        (0x7dc4c, "cbnz", "w0, #0x7dcbc"),
        (0x6ab24, "ldrb", "w8, [x0], #1"), (0x6ab28, "ldrb", "w9, [x1], #1"),
        (0x6ab2c, "cbz", "w8, #0x6ab38"), (0x6ab30, "cmp", "w8, w9"),
        (0x6ab34, "b.eq", "#0x6ab24"), (0x6ab38, "sub", "w8, w8, w9"),
        (0x6ab3c, "sxtb", "w0, w8"), (0x6ab40, "ret", ""),
        (0x67608, "bl", "#0x69248"), (0x675e8, "mov", "w0, #1"),
        (0x675ec, "mov", "w1, #0x58"),
        (0x6c28, "bl", "#0x670ac"), (0x6c2c, "mov", "w1, wzr"),
        (0x6c30, "ldr", "x2, [sp, #0x30]"), (0x6c34, "mov", "x23, x0"),
        (0x6c38, "bl", "#0x6a98c"), (0x6c4c, "str", "x8, [x7, x26, lsl #3]"),
    )
    for check in checks:
        expect(code, *check)
    for pc, name in ((0xc9257, b"tinysys-gpueb-RV33_A"), (0xb80f5, b"pvmfw"),
                     (0xc9ecb, b"atf"), (0xb0829, b"tee")):
        require(payload[pc:pc + len(name) + 1] == name + b"\0", "name mismatch")
    # Every name differs from RV33 at byte zero. The checked strcmp returns
    # that nonzero byte difference; none of the three action blocks is entered.
    post = {pc: i for pc, i in code.items() if 0x7db00 <= pc < 0x7dcec}
    reached, _, exits = cfg(post, 0x7db00,
                           {0x7db4c: 0x7dbbc, 0x7dbcc: 0x7dc3c, 0x7dc4c: 0x7dcbc})
    actions = [pc for pc in reached if post[pc].mnemonic == "bl" and
               target(post[pc]) in {0x978a0, 0x98a04}]
    require(not actions, "RV33 action block reachable")
    return {
        "high_address_allocation_branch_excluded": True,
        "source_expression": "mapped_reservation + 0x18 + copy_index",
        "tail_source_relative_to_mapping": [0x261b8, 0x3f2d0],
        "tail_destination_relative_to_sram": [PRIMARY_BYTES, COPY_BYTES],
        "tail_bytes": COPY_BYTES - PRIMARY_BYTES,
        "copy_words": (0x3f2bc - 4) // 4,
        "post_load_cache": {"call": 0x1edbc, "entry": 0x5e74,
                            "bytes": 0x100000, "fills_memory": False,
                            "effect": "clean/invalidate; can write back existing dirty bytes"},
        "post_load_callback": {"rv33_action_calls": actions,
                               "reachable_sites": sorted(reached), "window_exits": exits,
                               "assumption": "selected header name is RV33; normal AAPCS64 callee returns"},
        "other_zero_candidates": [
            {"call": 0x67608, "bytes": 88, "object": "mapping descriptor"},
            {"call": 0x6c38, "object": "page-table buffer from 0x670ac",
             "nonalias_with_staging_proven": False},
            {"call": 0x1edfc, "bytes": 0x40000, "object": "SRAM destination"}],
        "read_request": {"call": 0x75030, "count_producer": 0x75180,
                         "count_source": "selected member header +4; not the 1 MiB limit",
                         "lower_driver_write_extent_proven_here": False},
    }


def audit(primary, raw):
    require(len(primary) == PRIMARY_BYTES and sha(primary) == PRIMARY_SHA,
            "primary identity mismatch")
    require(512 <= len(raw) <= LIMIT, "LK size")
    magic, size = struct.unpack_from("<II", raw)
    require(magic == 0x58881688 and raw[8:40] == b"lk".ljust(32, b"\0") and
            struct.unpack_from("<II", raw, 48) == (0x58891689, 512) and
            0 < size <= len(raw) - 512, "LK framing")
    payload = raw[512:512 + size]
    require(sha(payload) == LK_SHA, "LK identity mismatch")
    all_code, windows = {}, {}
    for name, start, end, digest in WINDOWS:
        require(sha(payload[start:end]) == digest, "window identity mismatch")
        code = decode(payload, start, end)
        require(not all_code.keys() & code.keys(), "overlapping windows")
        all_code.update(code)
        windows[name] = code
    proofs = local_proofs(all_code, payload)
    proofs["allocator_name_copy"] = allocator_name_copy_contract(all_code)
    tables = mapper_tables(payload, all_code)
    proofs["mapper_jump_tables"] = [
        {"site": site, "targets": targets, "index_bits": 2}
        for site, targets in sorted(tables.items())]
    census, frontier = [], []
    entries = {start for _, start, _, _ in WINDOWS}
    for name, start, end, digest in WINDOWS:
        code = windows[name]
        decisions = {0x1ec84: 0x1ed30} if name == "caller" else None
        if name == "post_load":
            decisions = {0x7db4c: 0x7dbbc, 0x7dbcc: 0x7dc3c, 0x7dc4c: 0x7dcbc}
        reached, _, exits = cfg(code, start, decisions,
                               tables if name == "arch_map" else None)
        calls = []
        for pc, i in sorted(code.items()):
            if i.mnemonic not in {"bl", "blr"}:
                continue
            dest = target(i) if i.mnemonic == "bl" else None
            call = {"site": pc, "target": dest, "caller_reachable": pc in reached,
                    "callee_window_present": dest in entries}
            if pc == proofs["allocator_name_copy"]["call"]:
                call["write_contract"] = "local_proofs.allocator_name_copy"
            calls.append(call)
            if pc in reached and dest not in entries:
                frontier.append({"window": name, **call})
        census.append({"name": name, "start": start, "end_exclusive": end,
                       "sha256": digest, "decoded_instructions": len(code),
                       "caller_reachable_instructions": len(reached),
                       "calls": calls, "writers": memory_writers(code), "exits": exits})
    return {
        "schema": 1, "decoder": capstone.__version__,
        "identity": {"lk_payload_sha256": LK_SHA, "primary_sha256": PRIMARY_SHA,
                     "primary_bytes": len(primary),
                     "basis": "exact supplied digest pins; signatures not reauthenticated here"},
        "local_proofs": proofs, "census": census, "unexpanded_call_frontier": frontier,
        "coverage": {"complete_decode_of_declared_windows": True,
                     "whole_program_or_transitive_writer_proof": False,
                     "cfg_scope": "caller may-return overapproximation; indirect jumps are explicit exits",
                     "assumptions": "normal AAPCS64 returns; callback receives selected RV33 header name",
                     "resolved_indirect_mapper_sites": [0x7048, 0x7078],
                     "closed_leaf_write_contract_calls": [0x145cc],
                     "indirect_storage_site": 0x67f08},
        "unresolved_obligations": [
            "All unexpanded reachable callees and indirect exits need write/alias contracts.",
            "Allocator metadata, heap/page tables and logger globals must be disjoint from staging.",
            "Storage DMA, authentication/secure transforms and callbacks need transitive bounds.",
            "Initial reserved DRAM contents and earlier/async writers are not in these inputs.",
            "RV33 transitive startup memory requirements remain outside this ARM64-only audit."],
        "conclusion": {"producer_resolved": False, "scratch_proven": False,
                       "zero_proven": False, "tail_classification": "unresolved",
                       "copy_or_padding_authorized": False, "activation_permitted": False,
                       "closed_boundary": "cache operation is not a fill; RV33 skips named post-load action blocks",
                       "remaining_boundary": "complete producer/alias proof before enlarging signed upload or starting"},
    }


def read_bounded(path, limit, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
                "not a bounded regular input")
        require(not private or before.st_mode & 0o077 == 0, "snapshot must be private")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(data) == before.st_size == after.st_size and
                before.st_mtime_ns == after.st_mtime_ns and
                before.st_ctime_ns == after.st_ctime_ns, "input changed")
        return data


def write_report(path, report, inputs):
    path = Path(path)
    for source in inputs:
        require(path.resolve() != Path(source).resolve() and
                not (path.exists() and os.path.samefile(path, source)), "output aliases input")
    require(not path.is_symlink(), "output is a symlink")
    fd, temporary = tempfile.mkstemp(prefix=".lk-tail-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--lk", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-closure", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(read_bounded(args.snapshot, PRIMARY_BYTES, True),
                       read_bounded(args.lk, LIMIT))
        if args.output:
            write_report(args.output, report, (args.snapshot, args.lk))
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
    except Exception as error:
        parser.exit(1, f"LK tail audit rejected input ({type(error).__name__}); no new report\n")
    if args.require_closure:
        parser.exit(2, "LK tail producer closure incomplete; upload/start gate remains closed\n")


if __name__ == "__main__":
    main()
