#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Offline B4.1 RV33 loader/ATF audit. Never transform, upload, or execute."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

from audit_gpueb_lk import ROOT_PIN, LK_BASE, expect
from gpueb_firmware import certificate, metadata, bits, require, inspect, sections, MAX_IMAGE

LK_SHA = "431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a"
ATF_SHA = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"
MAX_LK = 8 * 1024 * 1024
PRIMARY_BYTES = 156064
LK_COPY_BYTES = 258744
RETAINED_SOURCES = {
    "tetris_gpueb_flat.c": "9a425bfa1a824459a6e0fd4c7fa31397a798aa91fdc7bcdff17907437b256d7f",
    "tetris_gpueb_flat_publish.c": "6cb04f7b33b86c9b5937624dc7221cad4ad6d9b87f436d9d662ea9cc22d2f34b",
    "gpueb-flat-analysis.c": "90659a3481c240f58673cd769d44245fb2814dcb61ac8ffce371311c5359ea86",
}


def primary_extent(lk, header):
    """Selected signed member's producer extent, not every possible RAM writer.

    The ordinary MTK header takes the no-inner-header path. The loader passes
    its declared count to authentication/transform and returns the reader's
    count, not an expanded size. The GPUEB caller checks only the error sign.
    Full payload identity is still established by inspect(), not this helper.
    """
    require(hashlib.sha256(lk).hexdigest() == LK_SHA, "not pinned B4.1 LK")
    require(len(header) == 512 and struct.unpack_from("<II", header) ==
            (0x58881688, PRIMARY_BYTES) and
            header[8:40] == b"tinysys-gpueb-RV33_A".ljust(32, b"\0"),
            "not the reviewed primary header")
    for check in (
        (0x1ed74, "ldr", "x8, [sp, #8]"),
        (0x1ed8c, "add", "x23, x8, #0x18"),
        (0x1ed90, "mov", "x2, x23"), (0x1ed94, "bl", "#0x74da0"),
        (0x1ed98, "tbnz", "w0, #0x1f, #0x1ee84"),
        (0x74dc8, "mov", "x21, x2"),
        (0x75180, "ldr", "w25, [x19, #4]"),
        (0x7518c, "add", "x24, x27, #0x200"),
        (0x75024, "mov", "x1, x21"), (0x75028, "mov", "x2, x24"),
        (0x7502c, "mov", "x3, x25"), (0x75030, "bl", "#0x67edc"),
        (0x75038, "mov", "x24, x0"), (0x7503c, "cmp", "x25, w24, sxtw"),
        (0x75040, "b.le", "#0x7505c"),
        (0x75060, "ldr", "w8, [x19]"),
        (0x75064, "mov", "w9, #0xab1e"),
        (0x75068, "movk", "w9, #0xd7b7, lsl #16"),
        (0x7506c, "rev", "w8, w8"), (0x75070, "cmp", "w8, w9"),
        (0x75074, "csel", "w8, w28, wzr, eq"),
        (0x75078, "add", "x21, x21, x8"), (0x7507c, "sub", "x25, x25, x8"),
        (0x75080, "mov", "x0, x21"), (0x75084, "mov", "w1, w25"),
        (0x75088, "bl", "#0x7e344"), (0x7508c, "cbz", "w0, #0x750cc"),
        (0x750f0, "mov", "x1, x21"), (0x750f4, "mov", "x2, x25"),
        (0x750f8, "bl", "#0x7db00"),
        (0x750fc, "mov", "w22, wzr"), (0x75100, "mov", "w21, wzr"),
        (0x75104, "b", "#0x7511c"),
        (0x7512c, "cbz", "w22, #0x75134"), (0x75130, "mov", "w24, w21"),
        (0x7514c, "mov", "w0, w24"), (0x7516c, "ret", ""),
        (0x1ee00, "mov", "w8, #0xf2bc"), (0x1ee04, "movk", "w8, #3, lsl #16"),
        (0x1ee08, "ldr", "w9, [x23], #4"), (0x1ee0c, "sub", "w8, w8, #4"),
        (0x1ee10, "cmp", "w8, #4"), (0x1ee14, "str", "w9, [x26], #4"),
        (0x1ee18, "b.hi", "#0x1ee08"),
    ):
        expect(lk, *check)
    # REV(MTK magic) cannot match the special internal-header selector.
    require(int.from_bytes(header[:4], "big") != 0xd7b7ab1e,
            "inner header would change the authenticated pointer/count")
    return {
        "member_payload_bytes": PRIMARY_BYTES,
        "member_payload_offset_from_header": 512,
        "lk_destination_offset_from_reservation": 24,
        "authentication_pointer_adjustment": 0,
        "authentication_and_transform_bytes": PRIMARY_BYTES,
        "loader_success_return": "byte-reader count; at least member size, not expanded size",
        "caller_return_check": "negative/error sign only; no upload-span comparison",
        "stock_copy_bytes": LK_COPY_BYTES,
        "uncovered_copy_interval": [PRIMARY_BYTES, LK_COPY_BYTES],
        "uncovered_copy_bytes": LK_COPY_BYTES - PRIMARY_BYTES,
        "tail_producer": "not established by the selected member's producer contract",
    }


def retained_profile(lk, atf, container, snapshot, sources):
    """Link authentic input, actual retained producer and exact private image.

    This is a producer/extent contract, not an RV firmware call-tree proof.
    No additional certificate policy, decryption or hardware execution occurs.
    Neither the scratch contents nor any need for the excess copy is inferred.
    """
    inspect(container, ROOT_PIN)
    parts = sections(container)
    extent = primary_extent(lk, parts[0].header)
    producer = producer_bounds(lk, atf)
    _, fields = certificate(parts[2].payload)
    expected = bits(metadata(fields, 4, 2), 32)
    require(len(snapshot) == PRIMARY_BYTES and
            hashlib.sha256(snapshot).digest() == expected,
            "snapshot does not match this member's signed post-transform digest")
    require(struct.unpack_from("<I", snapshot)[0] == 0x0ac0006f,
            "not the observed flat reset vector")
    require(set(sources) == set(RETAINED_SOURCES), "retained source set changed")
    for name, digest in RETAINED_SOURCES.items():
        require(hashlib.sha256(sources[name]).hexdigest() == digest,
                "retained source changed; re-audit the producer")
    return {
        "container_sha256": hashlib.sha256(container).hexdigest(),
        "signed_plaintext_sha256": expected.hex(),
        "lk_payload_sha256": LK_SHA,
        "atf_payload_sha256": ATF_SHA,
        "retained_source_sha256": RETAINED_SOURCES,
        "selected_member_extent": extent,
        "retained_image": {
            "bytes": PRIMARY_BYTES, "source_offset": 0, "sram_offset": 0,
            "reset_fetch_offset": 0, "initial_jump_target": 0xac,
            "format": "observed stock flat RV33 primary; not ELF or xfile",
            "producer": "existing authenticated transform, digest check, then retained publication",
            "consumer": "claimed reserved ordinary DRAM; signed-length snapshot and hash check",
        },
        "transform_extent": producer["cipher_dma_extent"],
        "whole_rv_call_resolution_required_for_image_identity": False,
        "stock_copy_covered": False,
        "execution_permitted": False,
        "remaining_boundary": "no source for the excess 102680 bytes; no reset-release/IRQ-enable start API",
    }


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


def producer_bounds(lk, atf):
    """Resolve indirect byte-reader/cipher paths, without executing either."""
    require(hashlib.sha256(lk).hexdigest() == LK_SHA and
            hashlib.sha256(atf).hexdigest() == ATF_SHA, "binary identity mismatch")
    for check in (
        # Authentication success already transforms; do not infer a second call.
        (0x7508c, "cbz", "w0, #0x750cc"),
        (0x93090, "mov", "w19, w1"),
        (0x93094, "mov", "x20, x0"),
        (0x930c4, "bl", "#0x92354"),
        (0x930e0, "bl", "#0x918f4"),
        (0x930e4, "cbz", "w0, #0x931ac"),
        (0x93144, "bl", "#0x918f4"),
        (0x93148, "cbz", "w0, #0x931ac"),
        (0x931c8, "mov", "x0, x20"),
        (0x931cc, "mov", "w1, w19"),
        (0x931d0, "bl", "#0x91fa0"),
        (0x931d8, "mov", "w21, w0"),
        (0x93190, "mov", "w0, w21"),
        (0x91f9c, "b", "#0x91fa0"),
        (0x92008, "stp", "x20, x20, [sp]"),
        # Partition callback translates the source offset only.
        (0x67f04, "ldr", "x4, [x0, #0x70]"),
        (0x67f08, "br", "x4"),
        (0x68ab4, "adr", "x9, #0x68b34"),
        (0x68acc, "stp", "x9, x8, [x19, #0x70]"),
        (0x68b3c, "ldr", "x0, [x0, #0xa8]"),
        (0x68b40, "madd", "x2, x9, x8, x2"),
        (0x68b44, "b", "#0x67edc"),
        (0x6806c, "adr", "x8, #0x680c8"),
        (0x68088, "stp", "x8, x9, [x21, #0x70]"),
        (0x680ec, "mov", "x21, x1"),
        (0x680f4, "mov", "x20, x3"),
        # First/last partial blocks go through a separate one-block buffer.
        (0x680fc, "mov", "x1, x26"),
        (0x68100, "bl", "#0x69204"),
        (0x68194, "cmp", "x9, x20"),
        (0x68198, "csel", "x23, x9, x20, lo"),
        (0x6819c, "mov", "x2, x23"),
        (0x681a0, "bl", "#0x6a66c"),
        (0x681e0, "lsr", "w27, w20, w8"),
        (0x681f0, "csel", "w3, w8, w27, hi"),
        (0x6820c, "mov", "x1, x21"),
        (0x68214, "blr", "x8"),
        (0x68234, "sub", "x20, x20, x25"),
        (0x682a4, "mov", "x0, x21"),
        (0x682a8, "mov", "x1, x19"),
        (0x682ac, "bl", "#0x6a66c"),
        (0x682c4, "sub", "x20, x20, x2"),
        (0x68304, "mov", "x1, x19"),
        (0x68324, "mov", "x0, x21"),
        (0x68328, "mov", "x1, x19"),
        (0x6832c, "mov", "x2, x20"),
        (0x68330, "bl", "#0x6a66c"),
        # UFS read callback and READ(10) use the requested whole-block count.
        (0x3ad04, "mov", "w2, #0x1000"),
        (0x3ad24, "bl", "#0x68008"),
        (0x3ad2c, "adr", "x22, #0x3afd4"),
        (0x3ad4c, "str", "x22, [x21, #0x78]"),
        (0x3b028, "mov", "w3, w19"),
        (0x3b02c, "mov", "x4, x21"),
        (0x3b030, "bl", "#0x36114"),
        (0x3615c, "csel", "w24, w20, w25, lo"),
        (0x3616c, "mov", "w3, w24"),
        (0x36174, "blr", "x8"),
        (0x367c0, "adr", "x9, #0x36478"),
        (0x367d8, "stp", "x9, x10, [x8, #0x1e8]"),
        (0x364a0, "mov", "w21, w3"),
        (0x364e0, "lsl", "w8, w21, #0xc"),
        (0x364f0, "str", "w8, [sp, #0x28]"),
        (0x36528, "strb", "w8, [sp, #0x1c]"),
        (0x3652c, "strb", "w21, [sp, #0x1d]"),
        (0x36534, "str", "x20, [sp, #0x30]"),
        (0x36538, "bl", "#0x37ae8"),
    ):
        expect(lk, *check)
    # Initialization selects entry 2 of three 24-byte cipher records.
    require(struct.unpack_from("<Q", atf, 0x464c8 + 2 * 24)[0] == 0x48837fec,
            "ATF selected cipher callback mismatch")
    for check in (
        (0x24d14, "mov", "w0, #2"),
        (0x24d18, "bl", "#0x59d4"),
        (0x59e4, "mov", "w8, #0x18"),
        (0x59e8, "adrp", "x9, #0x46000"),
        (0x59ec, "add", "x9, x9, #0x4c8"),
        (0x59f0, "umaddl", "x8, w0, w8, x9"),
        (0x59fc, "str", "x8, [x9, #0x2d0]"),
        (0x5a5c, "ldr", "x8, [x8, #0x2d0]"),
        (0x5a7c, "mov", "w1, w23"),
        (0x5a9c, "ldr", "x6, [x8]"),
        (0x5aa4, "br", "x6"),
        (0x38000, "cbz", "w5, #0x38018"),
        (0x38018, "b", "#0x3801c"),
        (0x38054, "mov", "w23, w1"),
        (0x3806c, "mov", "w3, w23"),
        (0x38078, "mov", "x2, x22"),
        (0x38084, "mov", "x6, x19"),
        (0x3808c, "bl", "#0x129c"),
        (0x12ac, "tst", "x3, #0xf"),
        (0x1330, "mov", "x20, x3"),
        (0x1334, "mov", "x24, x2"),
        (0x1390, "bl", "#0x2ff4"),
        (0x1398, "mov", "x0, x19"),
        (0x139c, "bl", "#0x2ff4"),
        (0x13a0, "mov", "x25, x0"),
        # DMA command: input PA, unchanged count, output PA, output end - 1.
        (0x14ac, "add", "x27, x25, x20"),
        (0x14b0, "str", "w24, [x21, #0x104]"),
        (0x14b4, "sub", "w8, w27, #1"),
        (0x14b8, "str", "w20, [x21, #0x104]"),
        (0x14bc, "str", "w25, [x21, #0x104]"),
        (0x14c0, "str", "w8, [x21, #0x104]"),
        (0x1590, "mov", "x0, x19"),
        (0x1594, "mov", "x1, x20"),
        (0x1598, "bl", "#0x27fc"),
        (0x27f8, "b", "#0x95ec"),
        (0x27fc, "b", "#0xa1dc"),
        (0x960c, "dc", "cvac, x0"),
        (0xa1fc, "dc", "ivac, x0"),
    ):
        expect(atf, *check)
    return {
        "authenticated_success_transform": "0x93068 -> 0x931d0 -> 0x91fa0",
        "success_skips_fallback_transform": "0x7508c -> 0x750cc",
        "partition_byte_callback": "0x68b34 -> 0x67edc -> 0x680c8",
        "partial_block_destination": "separate block buffer; bounded memcpy into staging",
        "ufs_read_callback": "0x3afd4 -> 0x36114 -> 0x36478; READ(10) bytes = blocks << 12",
        "atf_cipher_callback": "entry 2 at 0x464f8 -> 0x37fec -> 0x3801c -> 0x129c",
        "cipher_dma_extent": "original count; output PA + original count - 1",
        "cipher_cache_operations": "clean/invalidate only; no RAM initialization",
        "tail_initialization_producer": "unresolved in pinned stock control path",
        "execution_permitted": False,
    }


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
        "producer_bounds": producer_bounds(lk, atf),
        "stock_copy_bytes": 0x3f2b8, "stock_clear_bytes": 0x40000,
        "execution_permitted": False,
    }


def read_bounded(path, limit):
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def read_private_snapshot(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == PRIMARY_BYTES and
                before.st_mode & 0o077 == 0, "not a bounded private snapshot")
        data = stream.read(PRIMARY_BYTES + 1)
        after = os.fstat(stream.fileno())
        require(len(data) == before.st_size == after.st_size and
                before.st_mtime_ns == after.st_mtime_ns and
                before.st_ctime_ns == after.st_ctime_ns, "snapshot changed while reading")
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lk", type=Path, required=True)
    parser.add_argument("--atf", type=Path, required=True)
    parser.add_argument("--gpueb", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--require-stock-copy", action="store_true")
    args = parser.parse_args()
    if args.snapshot and not args.gpueb:
        parser.error("--snapshot requires its matching --gpueb container")
    if args.require_stock_copy and not args.snapshot:
        parser.error("--require-stock-copy requires --snapshot and --gpueb")
    try:
        lk = signed_lk(read_bounded(args.lk, MAX_LK))
        atf = pinned_atf(read_bounded(args.atf, 900752))
        report = trace(lk, atf)
        if args.gpueb:
            container = read_bounded(args.gpueb, MAX_IMAGE)
            firmware = inspect(container, ROOT_PIN)
            primary = firmware["components"][0]
            report["firmware"] = {
                "container_sha256": firmware["container_sha256"],
                "ciphertext_bytes": primary["payload_size"],
                "authentication": "verified root/delegation/signatures/header/ciphertext",
                "copy_size_matches_ciphertext": primary["payload_size"] == report["stock_copy_bytes"],
                "uncovered_copy_interval": [min(primary["payload_size"], report["stock_copy_bytes"]),
                                            report["stock_copy_bytes"]],
                "uncovered_copy_bytes": max(0, report["stock_copy_bytes"] - primary["payload_size"]),
                "plaintext_layout": "unobserved; transform-only review first",
            }
            report["firmware"]["selected_member_extent"] = primary_extent(lk, sections(container)[0].header)
            if args.snapshot:
                directory = Path(__file__).resolve().parent / "flat-handoff-draft"
                sources = {name: (directory / name).read_bytes() for name in RETAINED_SOURCES}
                report["retained_profile"] = retained_profile(
                    lk, atf, container, read_private_snapshot(args.snapshot), sources)
                report["firmware"]["plaintext_layout"] = report["retained_profile"]["retained_image"]["format"]
    except Exception as error:
        parser.exit(1, f"B4.1 GPUEB audit failed ({type(error).__name__})\n")
    print(json.dumps(report, indent=2))
    if args.require_stock_copy:
        parser.exit(2, "signed retained image does not cover the stock copy; no upload/start authorized\n")


if __name__ == "__main__":
    main()
