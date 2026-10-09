#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Offline B4.1 RV33 loader/ATF audit. Never transform, upload, or execute."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_gpueb_lk import ROOT_PIN, LK_BASE, expect
from gpueb_firmware import certificate, metadata, bits, require, inspect, MAX_IMAGE

LK_SHA = "431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a"
ATF_SHA = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"
MAX_LK = 8 * 1024 * 1024


def signed_lk(raw):
    require(0 < len(raw) <= MAX_LK, "invalid LK size")
    parts, offset = [], 0
    for name in ("lk", "cert1", "cert2"):
        require(offset + 512 <= len(raw), "truncated LK member")
        header = raw[offset:offset + 512]
        magic, size = struct.unpack_from("<II", header)
        require(magic == 0x58881688 and
                header[8:40] == name.encode().ljust(32, b"\0") and
                struct.unpack_from("<II", header, 48) == (0x58891689, 512),
                "unsupported LK member")
        require(0 < size <= len(raw) - offset - 512, "invalid LK member size")
        parts.append((header, raw[offset + 512:offset + 512 + size]))
        offset = (offset + 512 + size + 15) & ~15
    code = parts[0][1]
    require(hashlib.sha256(code).hexdigest() == LK_SHA, "not pinned B4.1 LK")
    root, root_fields = certificate(parts[1][1])
    leaf, leaf_fields = certificate(parts[2][1])
    require(hashlib.sha256(root).hexdigest() == ROOT_PIN and
            metadata(root_fields, 1, 2).encoded == leaf, "LK delegation mismatch")
    require(bits(metadata(leaf_fields, 2, 1), 32) == hashlib.sha256(code).digest() and
            bits(metadata(leaf_fields, 2, 4), 32) == hashlib.sha256(parts[0][0]).digest(),
            "LK signed digests mismatch")
    return code


def pinned_atf(raw):
    require(len(raw) == 900752 and
            struct.unpack_from("<II", raw) == (0x58881688, 900240),
            "invalid ATF container")
    code = raw[512:]
    require(hashlib.sha256(code).hexdigest() == ATF_SHA, "not pinned B4.1 ATF")
    return code


def trace(lk, atf):
    require(hashlib.sha256(lk).hexdigest() == LK_SHA and
            hashlib.sha256(atf).hexdigest() == ATF_SHA, "binary identity mismatch")
    for offset, text in ((0xc9257, b"tinysys-gpueb-RV33_A"), (0xbd028, b"gpueb"),
                         (0xb80f5, b"pvmfw"), (0xc9ecb, b"atf"), (0xb0829, b"tee")):
        require(lk[offset:].split(b"\0", 1)[0] == text, "caller name mismatch")
    require(lk[0xd8df8 + 15 * 64:].split(b"\0", 1)[0] == b"2.16.886.2454.2.9",
            "signed-word OID table mismatch")
    for index, oid in ((17, b"2.16.886.2454.2.8"), (18, b"2.16.886.2454.4.2")):
        require(lk[0xd8df8 + index * 64:].split(b"\0", 1)[0] == oid,
                "transform metadata table mismatch")
    # Both pointers resolve to the same signed metadata globals as the reference,
    # but the parser and transform entry offsets are different in B4.1.
    require(struct.unpack_from("<QQ", lk, 0x19a680) ==
            (LK_BASE + 0x251a94, LK_BASE + 0x251a98), "selector globals mismatch")
    for check in (
        (0x1ed84, "add", "x1, x1, #0x257"),
        (0x1ed94, "bl", "#0x74da0"),
        (0x75180, "ldr", "w25, [x19, #4]"),
        (0x7518c, "add", "x24, x27, #0x200"),
        (0x75024, "mov", "x1, x21"),
        (0x7502c, "mov", "x3, x25"),
        (0x75030, "bl", "#0x67edc"),
        (0x74f04, "cbz", "w26, #0x75004"),
        (0x75004, "bl", "#0x7e338"),
        (0x7e338, "b", "#0x92b5c"),
        (0x75088, "bl", "#0x7e344"),
        (0x7e344, "b", "#0x93068"),
        (0x750c4, "bl", "#0x7e348"),
        (0x7e348, "b", "#0x91f9c"),
        (0x94c38, "mov", "w0, #0xf"),
        (0x938d4, "adr", "x9, #0xd8df8"),
        (0x938f4, "add", "x1, x9, x8, lsl #6"),
        (0x94ea4, "ubfx", "w10, w9, #0x10, #4"),
        (0x94ea8, "ubfx", "w9, w9, #0x14, #4"),
        (0x91ff0, "mov", "w8, #0x20"),
        (0x92000, "strb", "w8, [sp, #0x14]"),
        (0x92028, "str", "w19, [sp, #0x10]"),
        (0x92058, "ldr", "w8, [x8, #0xa98]"),
        (0x9205c, "cmp", "w8, #1"),
        (0x92060, "cinc", "w9, w9, eq"),
        (0x92064, "cmp", "w8, #2"),
        (0x9206c, "csel", "w22, w8, w9, eq"),
        (0x92078, "ldr", "w2, [x23, #0xa94]"),
        (0x92084, "bl", "#0x88078"),
        (0x8808c, "mov", "w1, w2"),
        (0x88090, "bl", "#0x8203c"),
        (0x82088, "b", "#0x820a0"),
        (0x820f0, "str", "x0, [x23, #0x40]"),
        (0x820f8, "str", "w8, [x23, #0x48]"),
        (0x82100, "str", "x0, [x23, #0x50]"),
        (0x82118, "str", "w8, [x23, #0x58]"),
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
        (0x920bc, "add", "x24, x24, #0x90"),
        (0x9213c, "bl", "#0x87fc4"),
        (0x921a4, "cbz", "x8, #0x92290"),
        (0x92248, "mov", "w23, #0xc007"),
        (0x750c8, "cbnz", "w0, #0x75220"),
        (0x750f8, "bl", "#0x7db00"),
        (0x7db48, "bl", "#0x6ab24"),
        (0x7db4c, "cbnz", "w0, #0x7dbbc"),
        (0x7dbc8, "bl", "#0x6ab24"),
        (0x7dbcc, "cbnz", "w0, #0x7dc3c"),
        (0x7dc48, "bl", "#0x6ab24"),
        (0x7dc4c, "cbnz", "w0, #0x7dcbc"),
        (0x7dce4, "ret", ""),
        (0x1ede8, "mov", "w2, #0x40000"),
        (0x1edf8, "str", "wzr, [x22]"),
        (0x1ee00, "mov", "w8, #0xf2bc"),
        (0x1ee04, "movk", "w8, #3, lsl #16"),
        (0x1ee08, "ldr", "w9, [x23], #4"),
        (0x1ee0c, "sub", "w8, w8, #4"),
        (0x1ee10, "cmp", "w8, #4"),
        (0x1ee18, "b.hi", "#0x1ee08"),
    ):
        expect(lk, *check)
    # ATF service record: handler precedes the two SMC IDs, not follows the name.
    require(struct.unpack_from("<QIIQ", atf, 0x59440) ==
            (0x4880afcc, 0x82000133, 0xc2000133, 0x488544ee), "ATF service mismatch")
    require(atf[0x544ee:].split(b"\0", 1)[0] == b"MTK_SIP_LK_AES256_CBC_DEC_FW",
            "ATF service label mismatch")
    for check in (
        (0xafd4, "mov", "x1, x0"),
        (0xb018, "mov", "x0, sp"),
        (0xb06c, "bl", "#0x2bff4"),
        (0x2c018, "mov", "w0, #1"),
        (0x2c020, "bl", "#0xde4c"),
        (0xde60, "add", "x10, x9, #0x40"),
        (0x2c028, "bl", "#0xde80"),
        (0x2c030, "cbnz", "w0, #0x2c0f8"),
        (0x2c058, "ldr", "x25, [x19]"),
        (0x2c05c, "ldr", "w26, [x19, #8]"),
        (0x2c09c, "bl", "#0x3c51c"),
        (0x3c534, "and", "w8, w2, #0xff"),
        (0x3c53c, "cmp", "w8, #1"),
        (0x3c55c, "mov", "w0, #3"),
        (0x3c564, "bl", "#0x2c33c"),
        (0x2c0ac, "mov", "x0, x25"),
        (0x2c0b0, "mov", "w1, w26"),
        (0x2c0b8, "mov", "x4, x25"),
        (0x2c0bc, "mov", "w5, wzr"),
        (0x2c0c0, "bl", "#0x5a04"),
        (0x5aa4, "br", "x6"),
    ):
        expect(atf, *check)
    return {
        "lk_sha256": LK_SHA, "atf_sha256": ATF_SHA,
        "signed_word": "0x10000", "selector": 1, "mode": 0,
        "smc": "0xc2000133", "service_page_pa": "0x48401000",
        "smc_arguments": {"x1": 1, "x2_x3_x4_x5_x6_x7": 0},
        "descriptor": {"image_pa": "+0x40/u64", "image_bytes": "+0x48/u32",
                       "wrapped_pa": "+0x50/u64", "wrapped_bytes": "+0x58/u32"},
        "transform": "in-place; same descriptor byte count; no expansion-size ABI",
        "postdigest": "LK 0x252090 comparison; error 0x10c007 on mismatch",
        "post_load_callback": {"entry": "0x7db00", "names": ["pvmfw", "atf", "tee"],
                               "rv33_selected": False},
        "rv33_decompression": "none in audited post-load callback; do not infer expansion",
        "stock_copy_bytes": 0x3f2b8, "stock_clear_bytes": 0x40000,
        "execution_permitted": False,
    }


def read_bounded(path, limit):
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lk", type=Path, required=True)
    parser.add_argument("--atf", type=Path, required=True)
    parser.add_argument("--gpueb", type=Path)
    args = parser.parse_args()
    try:
        report = trace(signed_lk(read_bounded(args.lk, MAX_LK)),
                       pinned_atf(read_bounded(args.atf, 900752)))
        if args.gpueb:
            firmware = inspect(read_bounded(args.gpueb, MAX_IMAGE), ROOT_PIN)
            primary = firmware["components"][0]
            report["firmware"] = {
                "container_sha256": firmware["container_sha256"],
                "ciphertext_bytes": primary["payload_size"],
                "authentication": "verified root/delegation/signatures/header/ciphertext",
                "copy_size_matches_ciphertext": primary["payload_size"] == report["stock_copy_bytes"],
                "plaintext_layout": "unobserved; transform-only review first",
            }
    except Exception as error:
        parser.exit(1, f"B4.1 GPUEB audit failed ({type(error).__name__})\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
