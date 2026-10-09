#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Pinned original LK RV33 call trace. Offline only; never run a secure handler.

All results are checked against the hash-pinned signed original LK.
The selector calculation follows checked UBFX operands, without execution.
Neither stock images nor wrapped material/decrypted contents are emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

from gpueb_firmware import certificate, metadata, bits, require

LK_SHA = "f8e8d492597ec13c7568f927832020c1e971f98ac8b5f8921eb0e3815bc25c50"
ROOT_PIN = "e1b5235d9411473a358c754f84843801b91f05b8fb9dc4863393e378e41a115e"
LK_BASE = 0xffff000050700000
MAX_CONTAINER = 8 * 1024 * 1024
SOURCE = "https://github.com/R0rt1z2/fenrir/blob/59b92eb6c1a82c0d5270f750b87e93758cad6d5f/bin/tetris.bin"


def original_lk(data):
    require(0 < len(data) <= MAX_CONTAINER, "invalid LK container size")
    parts, offset = [], 0
    for name in ("lk", "cert1", "cert2"):
        require(offset + 512 <= len(data), "truncated LK header")
        header = data[offset:offset + 512]
        magic, size = struct.unpack_from("<II", header)
        require(magic == 0x58881688 and
                header[8:40] == name.encode().ljust(32, b"\0"), "LK member mismatch")
        require(0 < size <= len(data) - offset - 512, "LK member size mismatch")
        require(struct.unpack_from("<II", header, 48) == (0x58891689, 512),
                "unsupported LK header")
        parts.append((header, data[offset + 512:offset + 512 + size]))
        offset = (offset + 512 + size + 15) & ~15
    payload = parts[0][1]
    require(hashlib.sha256(payload).hexdigest() == LK_SHA, "unsupported LK payload; re-audit")
    root, fields = certificate(parts[1][1])
    leaf, leaf_fields = certificate(parts[2][1])
    require(hashlib.sha256(root).hexdigest() == ROOT_PIN, "LK root pin mismatch")
    require(metadata(fields, 1, 2).encoded == leaf, "LK leaf delegation mismatch")
    require(bits(metadata(leaf_fields, 2, 1), 32) == hashlib.sha256(payload).digest(),
            "signed LK digest mismatch")
    require(bits(metadata(leaf_fields, 2, 4), 32) == hashlib.sha256(parts[0][0]).digest(),
            "signed LK header mismatch")
    return payload


def expect(code, offset, mnemonic, operands):
    decoded = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(code[offset:offset + 4], offset))
    require(len(decoded) == 1 and decoded[0].mnemonic == mnemonic and
            decoded[0].op_str == operands, f"instruction mismatch at {offset:#x}")


def split_signed_word(code, word):
    require(0 <= word <= 0xffffffff, "invalid signed transform word")
    require(struct.unpack_from("<Q", code, 0x19a680)[0] == LK_BASE + 0x251a94 and
            struct.unpack_from("<Q", code, 0x19a688)[0] == LK_BASE + 0x251a98,
            "selector pointer identity mismatch")
    expect(code, 0x94fec, "ubfx", "w10, w9, #0x10, #4")
    expect(code, 0x94ff0, "ubfx", "w9, w9, #0x14, #4")
    expect(code, 0x94ffc, "str", "w10, [x8]")
    expect(code, 0x95000, "str", "w9, [x11]")
    return (word >> 16) & 15, (word >> 20) & 15


def audit(code):
    require(hashlib.sha256(code).hexdigest() == LK_SHA, "unsupported LK payload; re-audit")
    require(code[0xc9352:].split(b"\0", 1)[0] == b"tinysys-gpueb-RV33_A", "RV33 name mismatch")
    require(code[0xd8ee0 + 15 * 64:].split(b"\0", 1)[0] == b"2.16.886.2454.2.9",
            "signed-word OID table mismatch")
    checks = (
        (0x1ebc8, "ldr", "w8, [x24]"),
        (0x1ebcc, "lsr", "w8, w8, #0x1e"),
        (0x1ebd0, "cmp", "w8, #3"),
        (0x1ebd4, "b.lo", "#0x1ec04"),
        (0x1ebdc, "tbnz", "w2, #0xc, #0x1ebf0"),
        (0x1ebe0, "tbnz", "w2, #0xd, #0x1ec54"),
        (0x1ec60, "mov", "w0, #0x100000"),
        (0x1ec64, "mov", "w1, #0x10000"),
        (0x1ec74, "bl", "#0x140ec"),
        (0x1ec98, "mov", "w0, #0x600000"),
        (0x1ec9c, "mov", "w1, #0x10000"),
        (0x1ecbc, "add", "x8, x21, #0x600, lsl #12"),
        (0x1ecc0, "mov", "w9, #0xc"),
        (0x1ecc8, "stp", "x21, x8, [sp, #0x18]"),
        (0x1eccc, "str", "w9, [sp, #0x28]"),
        (0x1ecd0, "bl", "#0x7ef84"),
        (0x1ecd4, "adrp", "x0, #0x19a000"),
        (0x7efd0, "b.eq", "#0x7f070"),
        (0x7f070, "mov", "w0, #0x415"),
        (0x7f074, "ubfx", "x2, x20, #0xc, #0x20"),
        (0x7f078, "ubfx", "x3, x22, #0xc, #0x20"),
        (0x7f07c, "ldr", "w4, [x19, #0x10]"),
        (0x7f084, "movk", "w0, #0x8200, lsl #16"),
        (0x7f088, "mov", "x1, xzr"),
        (0x7f08c, "mov", "x5, xzr"),
        (0x7f090, "mov", "x6, xzr"),
        (0x7f094, "mov", "x7, xzr"),
        (0x7f09c, "bl", "#0x188dc"),
        (0x1ed80, "adrp", "x1, #0xc9000"),
        (0x1ed84, "add", "x1, x1, #0x352"),
        (0x1ed88, "mov", "w3, #0x100000"),
        (0x1ed8c, "add", "x23, x8, #0x18"),
        (0x1ed94, "bl", "#0x74da0"),
        (0x750c4, "bl", "#0x7e348"),
        (0x7e348, "b", "#0x920e4"),
        (0x94d80, "mov", "w0, #0xf"),
        (0x94fec, "ubfx", "w10, w9, #0x10, #4"),
        (0x94ff0, "ubfx", "w9, w9, #0x14, #4"),
        (0x921c0, "ldr", "w2, [x23, #0xa94]"),
        (0x92138, "mov", "w8, #0x20"),
        (0x92148, "strb", "w8, [sp, #0x14]"),
        (0x921cc, "bl", "#0x88078"),
        (0x8808c, "mov", "w1, w2"),
        (0x88090, "bl", "#0x8203c"),
        (0x16ea0, "mov", "w0, #2"),
        (0x82088, "b", "#0x820a0"),
        (0x820dc, "mov", "x23, #0x1000"),
        (0x820e4, "movk", "x23, #0x4840, lsl #16"),
        (0x820f0, "str", "x0, [x23, #0x40]"),
        (0x820f8, "str", "w8, [x23, #0x48]"),
        (0x82100, "str", "x0, [x23, #0x50]"),
        (0x82118, "str", "w8, [x23, #0x58]"),
        (0x82138, "mov", "w0, w19"),
        (0x8213c, "bl", "#0x8216c"),
        (0x8217c, "mov", "w1, w0"),
        (0x82180, "mov", "w0, #0x133"),
        (0x82184, "mov", "x2, xzr"),
        (0x82188, "movk", "w0, #0xc200, lsl #16"),
        (0x8218c, "mov", "x3, xzr"),
        (0x82194, "mov", "x4, xzr"),
        (0x82198, "mov", "x5, xzr"),
        (0x8219c, "mov", "x6, xzr"),
        (0x821a0, "mov", "x7, xzr"),
        (0x821bc, "bl", "#0x188dc"),
        (0x188dc, "smc", "#0"),
        (0x1edf0, "str", "w8, [x25]"),
        (0x1edac, "movk", "x25, #0x13f9, lsl #16"),
        (0x1edb0, "movk", "x22, #0x13c6, lsl #16"),
        (0x1edd4, "mov", "w8, #0xf00"),
        (0x1eddc, "movk", "w8, #1, lsl #16"),
        (0x1edf8, "str", "wzr, [x22]"),
        (0x1ede8, "mov", "w2, #0x40000"),
        (0x1edfc, "bl", "#0x6a98c"),
        (0x1ee08, "ldr", "w9, [x23], #4"),
        (0x1ee00, "mov", "w8, #0xf2bc"),
        (0x1ee04, "movk", "w8, #3, lsl #16"),
        (0x1ee0c, "sub", "w8, w8, #4"),
        (0x1ee10, "cmp", "w8, #4"),
        (0x1ee14, "str", "w9, [x26], #4"),
        (0x1ee38, "str", "w19, [x23]"),
        (0x1ee3c, "str", "wzr, [x23, #4]"),
        (0x1ee40, "str", "wzr, [x23, #0x5c]"),
        (0x1ee44, "str", "w8, [x23, #0x18]"),
        (0x1eed4, "str", "w8, [x23, #0x48]"),
        (0x1eee8, "str", "w8, [x22]"),
        (0x1eed8, "mov", "w8, #0xb"),
        (0x1eee0, "movk", "w8, #0x3f00, lsl #16"),
        (0x1eedc, "mov", "w20, #0x7788"),
        (0x1eee4, "movk", "w20, #0x5566, lsl #16"),
        (0x1eeec, "ldr", "w8, [x23, #8]"),
        (0x1eef0, "cmp", "w8, w20"),
        (0x1eef4, "b.ne", "#0x1ef18"),
        (0x1f0c4, "mov", "w8, #0x5a5a"),
        (0x1f0cc, "movk", "w8, #0x5a5a, lsl #16"),
        (0x1f0e0, "str", "w8, [x23]"),
        (0x1f0ec, "mov", "w22, #-0xd"),
    )
    for check in checks:
        expect(code, *check)
    selector, mode = split_signed_word(code, 0x10000)
    return {
        "source": SOURCE, "lk_payload_sha256": LK_SHA,
        "rv33_loader_call": "0x1ed94 -> 0x74da0",
        "signed_transform_word": "0x10000", "secure_selector": selector,
        "transform_mode": mode, "smc": "0xc2000133",
        "service_page": "0x48401000",
        "descriptor": {"image_pa": "+0x40/u64", "size": "+0x48/u32",
                       "material_pa": "+0x50/u64", "material_bytes": "+0x58/u32"},
        "protection_table": {
            "allocation_bytes": "0x600000", "alignment": "0x10000",
            "lk_call": "0x1ecd0 -> 0x7ef84", "smc": "0x82000415",
            "arguments": {"x1": "0", "x2": "(start_pa >> 12) & 0xffffffff",
                          "x3": "((start_pa + 0x600000) >> 12) & 0xffffffff",
                          "x4": "12", "x5_x6_x7": "0"},
            "atf_permissions": "not inferred from LK caller; handler audit required",
            "lk_checks_return": False,
        },
        "sram_clear_bytes": "0x40000", "sram_copy_bytes": "0x3f2b8",
        "mfg_rpc_initial_write": {"address": "0x13f91030", "value": "0x10f00"},
        "image_data_offset": "0x18", "reset_register": "0x13c60600",
        "reset_hold_write": "0", "reset_release_write": "0x3f00000b",
        "ready": {"gpr_offset": "0x8", "expected": "0x55667788"},
        "timeout_cleanup": "marker 0x5a5a5a5a then error -13; physical OFF unproven",
        "scope": "static original LK and checked UBFX selector operands; no execution",
        "activation_permitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lk_container", type=Path)
    args = parser.parse_args()
    try:
        with args.lk_container.open("rb") as image:
            code = original_lk(image.read(MAX_CONTAINER + 1))
        result = audit(code)
    except Exception as error:
        parser.exit(1, f"GPUEB LK audit failed ({type(error).__name__})\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
