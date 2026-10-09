#!/usr/bin/env python3
"""Offline B4.1 signed-byte oracle, NOT a kernel AUTH/EMI/NS-access provider.

Inputs are immutable snapshots, never physical addresses or /dev/mem. The CLI
uses the audited LK SPKI pin only. No untrusted chosen digest is an authority.
"""
from dataclasses import dataclass
import hashlib
import hmac
import struct

ROOT_PIN = bytes.fromhex("e1b5235d9411473a358c754f84843801b91f05b8fb9dc4863393e378e41a115e")
MAX_CONTAINER = 256 * 1024 * 1024
MAX_PAYLOAD = 64 * 1024 * 1024
MAX_CERT = 16384
PSS = bytes.fromhex(
    "304106092a864886f70d01010a3034a00f300d06096086480165030402010500"
    "a11c301a06092a864886f70d010108300d06096086480165030402010500a203020120")
LEGACY = bytes.fromhex("300d06092a864886f70d01010b0500")
RSA_ALGORITHM = bytes.fromhex("300d06092a864886f70d0101010500")
OID_PREFIX = bytes.fromhex("06076086769316")


class Rejected(ValueError):
    pass


def require(condition, stage):
    if not condition:
        raise Rejected(stage)


def digest(data):
    return hashlib.sha256(data).digest()


@dataclass(frozen=True)
class Field:
    raw: bytes
    tag: int
    value: bytes


def field(data, offset=0):
    require(len(data) - offset >= 2, "DER header")
    tag, length = data[offset:offset + 2]
    require(tag & 31 != 31, "DER high tag")
    header = 2
    if length & 128:
        count = length & 127
        require(1 <= count <= 2 and len(data) - offset >= 2 + count, "DER length")
        encoded = data[offset + 2:offset + 2 + count]
        length = int.from_bytes(encoded, "big")
        require(encoded[0] and length >= 128 and (count != 2 or length >= 256),
                "DER minimal length")
        header += count
    end = offset + header + length
    require(end <= len(data), "DER bound")
    return Field(data[offset:end], tag, data[offset + header:end]), end


def sequence(data):
    require(0 < len(data) <= MAX_CERT, "DER certificate bound")
    outer, end = field(data)
    require(outer.tag == 0x30 and end == len(data), "DER exact sequence")
    items, offset = [], 0
    while offset < len(outer.value):
        require(len(items) < 48, "DER field count")
        item, offset = field(outer.value, offset)
        items.append(item)
    return items


def bit_string(item, size):
    require(item.tag == 3 and len(item.value) == size + 1 and item.value[0] == 0,
            "BIT STRING extent")
    return item.value[1:]


@dataclass(frozen=True)
class Certificate:
    tbs: bytes
    spki: bytes
    signature: bytes
    metadata: tuple

    def get(self, group, item):
        oid = OID_PREFIX + bytes((group, item))
        found = [value for key, value in self.metadata if key == oid]
        require(len(found) == 1, f"metadata {group}/{item}")
        return found[0]


def parse_certificate(data):
    envelope = sequence(data)
    require(len(envelope) == 3, "certificate envelope")
    explicit = bytearray(PSS)
    explicit[1] += 5
    explicit[14] += 5
    explicit += bytes.fromhex("a303020101")
    require(envelope[1].raw in (PSS, bytes(explicit)), "PSS SHA256/MGF1/salt32")
    body = sequence(envelope[0].raw)
    require(len(body) >= 7 and (len(body) - 7) % 2 == 0, "TBS shape")
    require(body[2].raw in (envelope[1].raw, LEGACY), "TBS algorithm label")
    spki = sequence(body[6].raw)
    require(len(spki) == 2 and spki[0].raw == RSA_ALGORITHM, "RSA SPKI")
    require(spki[1].tag == 3 and len(spki[1].value) > 1, "RSA key bits")
    key = sequence(bit_string(spki[1], len(spki[1].value) - 1))
    require(len(key) == 2 and key[0].tag == 2 and len(key[0].value) == 257 and
            key[0].value[0] == 0 and key[0].value[1] & 128 and key[0].value[-1] & 1 and
            key[1].raw == bytes.fromhex("0203010001"), "RSA2048 exponent65537")
    metadata, seen = [], set()
    for index in range(7, len(body), 2):
        oid = body[index]
        require(oid.tag == 6 and oid.raw not in seen, "unique metadata OIDs")
        seen.add(oid.raw)
        metadata.append((oid.raw, body[index + 1]))
    return Certificate(envelope[0].raw, body[6].raw,
                       bit_string(envelope[2], 256), tuple(metadata))


def verify_member(cert1, cert2, header, payload, trusted_pin):
    # Crypto is provided by the established OpenSSL-backed cryptography API.
    # Do not substitute generic X.509 chain verification: MTK has custom TBS.
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.exceptions import InvalidSignature

    require(len(trusted_pin) == 32, "independent root pin")
    root, leaf = parse_certificate(cert1), parse_certificate(cert2)
    require(hmac.compare_digest(digest(root.spki), trusted_pin), "root SPKI pin")
    require(root.get(1, 2).raw == leaf.spki, "root delegation to leaf")
    scheme = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
    try:
        for cert in (root, leaf):
            public = serialization.load_der_public_key(cert.spki)
            public.verify(cert.signature, cert.tbs, scheme, hashes.SHA256())
    except InvalidSignature as error:
        raise Rejected("certificate signature") from error
    for group, item in ((2, 6), (2, 8), (4, 2)):
        require(leaf.get(group, item).raw == bytes.fromhex("03020000"),
                "B4.1 non-transform profile")
    require(hmac.compare_digest(digest(header), bit_string(leaf.get(2, 4), 32)),
            "signed 512-byte member header")
    require(hmac.compare_digest(digest(payload), bit_string(leaf.get(2, 1), 32)),
            "signed non-transformed payload")


def word(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def members(container):
    require(isinstance(container, bytes) and 0 < len(container) <= MAX_CONTAINER,
            "immutable bounded container")
    offset = 0
    for _ in range(128):
        require(len(container) - offset >= 512, "member header bound")
        header = container[offset:offset + 512]
        require(word(header, 0) == 0x58881688 and word(header, 48) == 0x58891689 and
                word(header, 52) == 512 and word(header, 68) == 16, "member profile")
        name_field = header[8:40]
        require(b"\0" in name_field, "member name termination")
        name = name_field.split(b"\0", 1)[0]
        require(all(c < 128 for c in name), "ASCII member name")
        size = word(header, 4)
        require(0 < size <= len(container) - offset - 512, "member payload bound")
        end = offset + 512 + size
        payload = container[offset + 512:end]
        offset = (end + 15) & ~15
        require(offset <= len(container), "member alignment bound")
        yield name, header, payload
    raise Rejected("128 member limit")


@dataclass(frozen=True)
class SignedPlacement:
    rom_size: int
    rom_sha256: str
    dsp_offset: int
    dsp_size: int
    dsp_sha256: str
    memory_size: int
    logical_image_size: int


def verify_signed_placement(container, rom_snapshot, dsp_snapshot, reservation_size,
                            *, trusted_pin=ROOT_PIN):
    """Check signatures AND actual span bytes. Not an execution permission.

    trusted_pin override exists for synthetic CI fixtures only; CLI has none.
    Snapshot provenance/physical identity/write exclusion are external gates.
    """
    verified, pending, cert1 = {}, None, None
    for name, header, payload in members(container):
        if pending is None:
            if name not in (b"md1rom", b"md1drdi", b"md1dsp"):
                continue
            require(name not in verified, "duplicate firmware")
            require(len(payload) <= MAX_PAYLOAD and len(payload) % 16 == 0,
                    "firmware extent")
            pending = (name, header, payload)
        elif cert1 is None:
            expected = b"cert1md" if pending[0] == b"md1rom" else b"cert1"
            require(name == expected and len(payload) <= MAX_CERT, "cert1 ordering")
            cert1 = payload
        else:
            require(name == b"cert2" and len(payload) <= MAX_CERT, "cert2 ordering")
            verify_member(cert1, payload, pending[1], pending[2], trusted_pin)
            verified[pending[0]] = pending[2]
            pending, cert1 = None, None
            if len(verified) == 3:
                break
    require(len(verified) == 3, "ROM/DRDI/DSP completeness")
    rom, dsp = verified[b"md1rom"], verified[b"md1dsp"]
    require(len(rom) >= 512, "ROM CHECK_HEADER bound")
    header = rom[-512:]
    require(header[:12] == b"CHECK_HEADER" and word(header, 508) == 512,
            "ROM CHECK_HEADER")
    require(word(header, 12) == 6 and header[168] == 1 and word(header, 16) == 2 and
            word(header, 20) == 14 and word(header, 0x190) == 3, "B4.1 layout profile")
    memory, logical = word(header, 172), word(header, 176)
    offset, capacity, count = word(header, 184), word(header, 188), word(header, 192)
    require(0 < memory <= reservation_size and 0 < logical <= memory and
            len(rom) <= memory and len(rom) <= offset < memory and
            0 < capacity <= memory - offset and len(dsp) <= capacity and
            1 <= count <= 8, "signed layout bounds")
    ranges = []
    for index in range(count):
        start, size = word(header, 196 + index * 8), word(header, 200 + index * 8)
        require(0 <= start < memory and 0 < size <= memory - start and
                all(start + size <= a or a + n <= start for a, n in ranges),
                "signed region bounds/overlap")
        ranges.append((start, size))
    require(isinstance(rom_snapshot, bytes) and isinstance(dsp_snapshot, bytes),
            "immutable byte snapshots")
    require(len(rom_snapshot) == len(rom) and len(dsp_snapshot) == len(dsp),
            "actual installed signed span lengths")
    require(hmac.compare_digest(digest(rom_snapshot), digest(rom)), "installed ROM hash")
    require(hmac.compare_digest(digest(dsp_snapshot), digest(dsp)), "installed DSP hash")
    return SignedPlacement(len(rom), digest(rom).hex(), offset, len(dsp), digest(dsp).hex(),
                           memory, logical)


if __name__ == "__main__":
    import argparse
    from dataclasses import asdict
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True, type=Path)
    parser.add_argument("--rom-snapshot", required=True, type=Path)
    parser.add_argument("--dsp-snapshot", required=True, type=Path)
    parser.add_argument("--reservation-size", required=True, type=lambda n: int(n, 0))
    args = parser.parse_args()
    for path, limit in ((args.container, MAX_CONTAINER), (args.rom_snapshot, MAX_PAYLOAD),
                        (args.dsp_snapshot, MAX_PAYLOAD)):
        require(path.is_file() and 0 < path.stat().st_size <= limit, "input file bound")
    result = verify_signed_placement(args.container.read_bytes(), args.rom_snapshot.read_bytes(),
                                     args.dsp_snapshot.read_bytes(), args.reservation_size)
    print(json.dumps({"signed_bytes": asdict(result), "execution_permission": False}, indent=2))
