#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Read-only GPUEB RV33 container/authentication gate; never decrypt or boot.

MTK partition headers and custom certificate semantics match the audited
tetris_scp_handoff.c/tetris_scp_security.c implementations, not X.509 CA
semantics. The xfile payload digest coverage and physical boot procedure are
not established: even a valid report is NOT permission to start GPUEB.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

MAX_IMAGE = 2 * 1024 * 1024
MAX_CERT = 16384
NAMES = ("tinysys-gpueb-RV33_A", "cert1", "cert2",
         "tinysys-gpueb-RV33_A_xfile", "cert1", "cert2")
OID_PREFIX = bytes.fromhex("6086769316")
PSS = bytes.fromhex(
    "304106092a864886f70d01010a3034a00f300d06096086480165030402010500"
    "a11c301a06092a864886f70d010108300d06096086480165030402010500"
    "a203020120")
_explicit = bytearray(PSS)
_explicit[1] += 5
_explicit[14] += 5
PSS_EXPLICIT = bytes(_explicit) + bytes.fromhex("a303020101")
LEGACY_LABEL = bytes.fromhex("300d06092a864886f70d01010b0500")


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Field:
    tag: int
    value: bytes
    encoded: bytes


def _field(data, offset=0):
    # Same bounded, minimal DER framing as the existing U-Boot verifier.
    require(offset + 2 <= len(data), "truncated DER")
    tag, length = data[offset:offset + 2]
    require(tag & 31 != 31, "unsupported DER tag")
    header = 2
    if length & 128:
        count = length & 127
        require(0 < count <= 2 and offset + 2 + count <= len(data),
                "invalid DER length")
        require(data[offset + 2] != 0, "nonminimal DER length")
        length = int.from_bytes(data[offset + 2:offset + 2 + count], "big")
        require(length >= (128 if count == 1 else 256), "nonminimal DER length")
        header += count
    end = offset + header + length
    require(end <= len(data), "truncated DER value")
    return Field(tag, data[offset + header:end], data[offset:end]), end


def sequence(data):
    require(len(data) <= MAX_CERT, "oversized DER")
    outer, end = _field(data)
    require(outer.tag == 0x30 and end == len(data), "invalid DER sequence")
    fields, offset = [], 0
    while offset < len(outer.value):
        field, offset = _field(outer.value, offset)
        fields.append(field)
        require(len(fields) <= 48, "too many DER fields")
    return fields


def bits(field, size):
    require(field.tag == 3 and len(field.value) == size + 1 and
            field.value[0] == 0, "invalid metadata bits")
    return field.value[1:]


def certificate(data):
    envelope = sequence(data)
    require(len(envelope) == 3 and envelope[1].encoded in (PSS, PSS_EXPLICIT),
            "unsupported RSA-PSS parameters")
    signature = bits(envelope[2], 256)
    body = sequence(envelope[0].encoded)
    require(len(body) >= 7 and (len(body) - 7) % 2 == 0,
            "invalid MediaTek certificate")
    require(body[2].encoded in (envelope[1].encoded, LEGACY_LABEL),
            "unsupported inner signature label")
    key = serialization.load_der_public_key(body[6].encoded)
    require(isinstance(key, rsa.RSAPublicKey) and key.key_size == 2048 and
            key.public_numbers().e == 65537, "unsupported signing key")
    metadata = {}
    for i in range(7, len(body), 2):
        oid = body[i]
        require(oid.tag == 6 and oid.value not in metadata,
                "invalid or duplicate metadata OID")
        metadata[oid.value] = body[i + 1]
    key.verify(signature, envelope[0].encoded,
               padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
               hashes.SHA256())
    return body[6].encoded, metadata


@dataclass(frozen=True)
class Section:
    name: str
    offset: int
    header: bytes
    payload: bytes


def sections(data):
    require(0 < len(data) <= MAX_IMAGE, "invalid image size")
    data = bytes(data)
    result, offset = [], 0
    for index, name in enumerate(NAMES):
        require(offset + 512 <= len(data), "truncated partition header")
        header = data[offset:offset + 512]
        magic, size = struct.unpack_from("<II", header)
        ext, hsize, version, role, _, alignment, highsize, marker = \
            struct.unpack_from("<8I", header, 48)
        require(magic == 0x58881688 and ext == 0x58891689,
                "invalid partition magic")
        require(hsize == 512 and version == 1 and alignment == 16 and highsize == 0,
                "unsupported partition layout")
        require(header[8:40] == name.encode().ljust(32, b"\0"),
                "unexpected section name/order")
        expected_role = (0, 0x02000000, 0x02000002)[index % 3]
        require(role == expected_role and marker == (0 if index % 3 == 0 else 0x22345678),
                "unexpected section role")
        require(0 < size <= len(data) - offset - 512, "invalid payload size")
        if index % 3:
            require(size <= MAX_CERT, "oversized certificate")
        end = offset + 512 + size
        aligned = (end + 15) & ~15
        require(aligned <= len(data) and not any(data[end:aligned]),
                "invalid alignment padding")
        result.append(Section(name, offset, header, data[offset + 512:end]))
        offset = aligned
    require(not any(data[offset:]), "nonzero partition tail")
    return result


def metadata(fields, group, item):
    oid = OID_PREFIX + bytes((group, item))
    require(oid in fields, "missing required metadata")
    return fields[oid]


def inspect(data, expected_root):
    require(isinstance(expected_root, str) and len(expected_root) == 64 and
            all(c in "0123456789abcdef" for c in expected_root),
            "independent root SPKI pin required")
    parts = sections(data)
    report = {"container_sha256": hashlib.sha256(data).hexdigest(),
              "trust": "caller-pinned-root", "boot_permitted": False,
              "components": []}
    for index in (0, 3):
        part = parts[index]
        root_spki, root_fields = certificate(parts[index + 1].payload)
        leaf_spki, leaf_fields = certificate(parts[index + 2].payload)
        require(hashlib.sha256(root_spki).hexdigest() == expected_root,
                "root SPKI pin mismatch")
        require(metadata(root_fields, 1, 2).encoded == leaf_spki,
                "signing key not delegated by root")
        require(bits(metadata(leaf_fields, 2, 4), 32) == hashlib.sha256(part.header).digest(),
                "signed partition header mismatch")
        payload_digest = bits(metadata(leaf_fields, 2, 1), 32)
        digest_matches = payload_digest == hashlib.sha256(part.payload).digest()
        if index == 0:
            require(digest_matches, "RV33 ciphertext digest mismatch")
            require(len(part.payload) % 16 == 0, "RV33 transform alignment")
            require(any(bits(metadata(leaf_fields, 2, 8), 32)) and
                    any(bits(metadata(leaf_fields, 4, 2), 32)),
                    "missing RV33 transform metadata")
            selector = metadata(leaf_fields, 2, 9)
            require(selector.tag == 2 and selector.value == b"\x01\x00\x00",
                    "unsupported RV33 signed transform profile")
            profile = "signed-transform-required; secure-selector-unproven"
        else:
            require(bits(metadata(leaf_fields, 2, 8), 1) == b"\0" and
                    bits(metadata(leaf_fields, 4, 2), 1) == b"\0" and
                    metadata(leaf_fields, 2, 9).encoded == b"\x02\x01\x00",
                    "unsupported xfile transform profile")
            profile = "auxiliary; payload-digest-coverage-unproven"
        report["components"].append({
            "name": part.name, "offset": part.offset, "payload_size": len(part.payload),
            "certificate_signatures": "verified", "header_digest": "verified",
            "whole_payload_digest": "verified" if digest_matches else "unproven",
            "profile": profile,
            "signed_transform_word": "0x10000" if index == 0 else "0x0",
            "secure_transform_selector": "unproven",
        })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--expected-root-sha256", required=True)
    args = parser.parse_args()
    try:
        with args.image.open("rb") as image:
            data = image.read(MAX_IMAGE + 1)
        report = inspect(data, args.expected_root_sha256)
    except Exception as error:
        # Decoding/crypto exceptions can contain material: only print the type.
        parser.exit(1, f"GPUEB validation failed ({type(error).__name__})\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
