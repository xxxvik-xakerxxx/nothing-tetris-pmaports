#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Pinned B4.1 allocation/lifetime evidence; no inferred zero tail or boot."""
import argparse
import hashlib
import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from audit_gpueb_b41 import LK_SHA, signed_lk
from audit_gpueb_lk import expect
from gpueb_firmware import require


def trace(code):
    require(hashlib.sha256(code).hexdigest() == LK_SHA, "not pinned B4.1 LK")
    require(code[0xaa123:].split(b"\0", 1)[0] == b"mblock_alloc_range_no_lock",
            "reservation routine identity changed")
    for check in (
        (0x1ec60, "mov", "w0, #0x100000"),
        (0x1ec64, "mov", "w1, #0x10000"),
        (0x1ec68, "mov", "w2, #-0x80000000"),
        (0x1ec6c, "mov", "x3, xzr"),
        (0x1ec70, "mov", "w4, wzr"),
        (0x1ec74, "bl", "#0x140ec"),
        (0x1ec78, "cbz", "x0, #0x1ed24"),
        (0x1ec7c, "mov", "x19, x0"),
        (0x14134, "mov", "x1, x23"),
        (0x14138, "mov", "x2, xzr"),
        (0x1414c, "bl", "#0x14190"),
        (0x145a8, "stur", "x26, [x27, #-0x14]"),
        (0x145ac, "stur", "x22, [x27, #-0xc]"),
        (0x145b0, "stur", "w21, [x27, #-4]"),
        (0x1ece0, "add", "x3, sp, #8"),
        (0x1ece4, "mov", "w2, #0x100000"),
        (0x1ece8, "mov", "w4, #0xc"),
        (0x1ecf0, "mov", "x5, x19"),
        (0x1ecf4, "mov", "w6, wzr"),
        (0x1ecf8, "mov", "w7, wzr"),
        (0x1ecfc, "bl", "#0x67894"),
        (0x67954, "ldr", "x8, [x21, #0x38]"),
        (0x67958, "str", "x8, [x25]"),
        (0x6796c, "mov", "x2, x22"),
        (0x67974, "lsr", "x3, x23, #0xc"),
        (0x67978, "bl", "#0x6f94"),
        (0x675e8, "mov", "w0, #1"),
        (0x675ec, "mov", "w1, #0x58"),
        (0x67608, "bl", "#0x69248"),
        (0x67628, "stp", "x23, x21, [x19, #0x38]"),
        (0x74dc8, "mov", "x21, x2"),
        (0x74dfc, "mov", "w0, #0x200"),
        (0x74e00, "bl", "#0x691c4"),
        (0x1ed74, "ldr", "x8, [sp, #8]"),
        (0x1ed88, "mov", "w3, #0x100000"),
        (0x1ed8c, "add", "x23, x8, #0x18"),
        (0x1ed90, "mov", "x2, x23"),
        (0x1ed94, "bl", "#0x74da0"),
        (0x1edd8, "mov", "x0, #0x13c00000"),
        (0x1ede0, "movk", "x0, #0xffff, lsl #48"),
        (0x1ede4, "mov", "w1, wzr"),
        (0x1ede8, "mov", "w2, #0x40000"),
        (0x1edf8, "str", "wzr, [x22]"),
        (0x1edfc, "bl", "#0x6a98c"),
        (0x6a9b0, "strb", "w1, [x11], #1"),
        (0x1ee08, "ldr", "w9, [x23], #4"),
        (0x1ee14, "str", "w9, [x26], #4"),
        (0x1ee18, "b.hi", "#0x1ee08"),
        (0x1ee38, "str", "w19, [x23]"),
        (0x1eeec, "ldr", "w8, [x23, #8]"),
        (0x1ef00, "ldr", "x1, [sp, #8]"),
        (0x1ef04, "ldr", "x0, [x0, #0x4f8]"),
        (0x1ef08, "bl", "#0x67c7c"),
        (0x1ef0c, "mov", "x0, x19"),
        (0x1ef10, "bl", "#0x1508c"),
    ):
        expect(code, *check)
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    instructions = list(decoder.disasm(code[0x1ec54:0x1ed98], 0x1ec54))
    require(len(instructions) == (0x1ed98 - 0x1ec54) // 4,
            "incomplete caller decode")
    calls = [(i.address, i.op_str) for i in instructions if i.mnemonic == "bl"]
    require(calls == [(0x1ec74, "#0x140ec"), (0x1ec80, "#0x16ec0"),
                     (0x1ecb0, "#0x148dc"), (0x1ecd0, "#0x7ef84"),
                     (0x1ecfc, "#0x67894"), (0x1ed1c, "#0x69c28"),
                     (0x1ed4c, "#0x140ec"), (0x1ed68, "#0x69c28"),
                     (0x1ed94, "#0x74da0")], "caller call graph changed")
    # The only explicit full-size zero operation is SRAM, AFTER authentication.
    # Reservation bookkeeping, mapping and stack zeros are not a RAM zero proof.
    return {
        "lk_payload_sha256": LK_SHA,
        "reservation": {"bytes": 0x100000, "alignment": 0x10000,
                        "upper_bound_argument": 0x80000000,
                        "routine": "mblock_alloc_range_no_lock"},
        "mapping": {"bytes": 0x100000, "architecture_flags": 12,
                    "allocation_flags": 0, "mapping_flags": 0,
                    "zero_allocated_descriptor_bytes": 88,
                    "descriptor_is_not_firmware_backing": True},
        "reader": {"mapped_offset": 24, "limit_argument": 0x100000,
                   "temporary_header_allocation_bytes": 512,
                   "actual_backing_remaining_bytes": 0x100000 - 24},
        "full_staging_zero_proven": False,
        "zero_tail_is_bss_proven": False,
        "zero_tail_allowed": False,
        "authenticated_primary_bytes": 156064,
        "fixed_copy_bytes": 258744,
        "unauthenticated_copy_excess_bytes": 258744 - 156064,
        "sram_clear": {"base": 0x13c00000, "bytes": 0x40000,
                       "after_reset_assert": True, "includes_gpr_mailbox": True},
        "lifetime": "mapping released then physical reservation freed after boot wait/error",
        "owner_contract": "one SRAM controller; no independent GPR/mailbox claims before clear/copy/BOOT",
        "physical_off_on_error_proven": False,
        "execution_allowed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lk", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(trace(signed_lk(args.lk.read_bytes())), indent=2, sort_keys=True))
