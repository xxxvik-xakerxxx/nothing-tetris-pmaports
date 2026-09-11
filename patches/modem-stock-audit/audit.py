#!/usr/bin/env python3
"""Read-only, hash-pinned LK inspection. Never executes input instructions."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

CONTAINER_SHA = "29669b7a19dcb75b410cd8e35376c98892c0629cefd9eff7a5b01022f5667a1f"
PAYLOAD_SHA = "431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a"
BASE = 0xffff000050700000
SIZE = 1681136


def payload(data):
    if hashlib.sha256(data).hexdigest() != CONTAINER_SHA:
        raise ValueError("wrong container SHA-256")
    if struct.unpack_from("<II", data) != (0x58881688, SIZE):
        raise ValueError("unexpected first image header")
    result = data[512:512 + SIZE]
    if hashlib.sha256(result).hexdigest() != PAYLOAD_SHA:
        raise ValueError("wrong first LK payload SHA-256")
    return result


def cstring(data, offset):
    if not 0 <= offset < len(data):
        raise ValueError("string pointer outside payload")
    end = data.find(b"\0", offset, min(offset + 256, len(data)))
    if end < 0:
        raise ValueError("unterminated string")
    return data[offset:end].decode("ascii")


def static_tables(data):
    descriptors = []
    for off in range(0xe15e0, 0xe1640, 32):
        kind, partition, image, flags = struct.unpack_from("<QQQQ", data, off)
        descriptors.append(dict(offset=hex(off), kind=kind,
            partition=cstring(data, partition - BASE),
            image=cstring(data, image - BASE), flags=flags))
    updates = []
    for off in (0x19a088, 0x19a098):
        function, name = struct.unpack_from("<QQ", data, off)
        updates.append(dict(offset=hex(off), function=hex(function - BASE),
                            name=cstring(data, name - BASE)))
    return dict(modem_fallback_descriptors=descriptors, dt_callback_pairs=updates)


def registry(data):
    # Anchor discovered from the boot_tag_emi_info string pointer, not a
    # running device address. Records are <u32 tag, u32 pad, u64 fn, u64 name>.
    def valid(off):
        if off < 0 or off + 24 > len(data):
            return False
        tag, pad, fn, name = struct.unpack_from("<IIQQ", data, off)
        return tag >> 16 == 0x8861 and pad == 0 and BASE <= fn < BASE + SIZE and BASE <= name < BASE + SIZE

    start = 0x199a48
    if not valid(start):
        raise ValueError("registry anchor invalid")
    while valid(start - 24):
        start -= 24
    rows = []
    off = start
    while valid(off):
        tag, _, fn, name = struct.unpack_from("<IIQQ", data, off)
        rows.append(dict(offset=hex(off), tag=hex(tag), function=hex(fn - BASE),
                         name=cstring(data, name - BASE)))
        off += 24
    ids = {int(row["tag"], 16) & 0xffff for row in rows}
    observed = 0x3b0c7fff | (0x0026ff3b << 32)
    return dict(start=hex(start), end=hex(off), count=len(rows),
                unique_ids=len(ids), entries=rows,
                user_reported_input_ids_without_callback=[hex(i) for i in range(64)
                    if observed & (1 << i) and i not in ids])


def address_candidates(data, target):
    # Bounded raw instruction-pattern search. Candidates need disassembly:
    # an intervening instruction may clobber the ADRP register.
    found = []
    for off in range(0, 0xa0000, 4):
        word, = struct.unpack_from("<I", data, off)
        if word & 0x9f000000 == 0x10000000:
            imm = ((word >> 29) & 3) | (((word >> 5) & 0x7ffff) << 2)
            if imm & (1 << 20):
                imm -= 1 << 21
            if off + imm == target:
                found.append(dict(adr=hex(off)))
        if word & 0x9f000000 != 0x90000000:
            continue
        imm = ((word >> 29) & 3) | (((word >> 5) & 0x7ffff) << 2)
        if imm & (1 << 20):
            imm -= 1 << 21
        page = ((BASE + off) & ~4095) + (imm << 12)
        reg = word & 31
        for nxt in range(off + 4, off + 36, 4):
            add, = struct.unpack_from("<I", data, nxt)
            if add & 0xffc00000 == 0xf9400000 and (add >> 5) & 31 == reg:
                if page + (((add >> 10) & 4095) * 8) == BASE + target:
                    found.append(dict(adrp=hex(off), ldr=hex(nxt)))
            if add & 0xff800000 != 0x91000000 or (add >> 5) & 31 != reg:
                continue
            value = page + (((add >> 10) & 4095) << (12 if add & (1 << 22) else 0))
            if value == BASE + target:
                found.append(dict(adrp=hex(off), add=hex(nxt)))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--xref", action="append", default=[])
    parser.add_argument("--address", action="append", default=[])
    parser.add_argument("--calls-to", action="append", default=[])
    parser.add_argument("--pointers-to", action="append", default=[])
    parser.add_argument("--window", action="append", default=[], help="payload offset:size, hex allowed")
    args = parser.parse_args()
    data = payload(args.image.read_bytes())
    result = {"container_sha256": CONTAINER_SHA, "payload_sha256": PAYLOAD_SHA,
              "payload_container_offset": 512, "linked_base": hex(BASE)}
    if not (args.window or args.xref or args.address or args.calls_to or args.pointers_to):
        result["registry"] = registry(data)
    for target in args.pointers_to:
        result["pointers_to_" + target] = [hex(off) for off in range(0, len(data) - 7, 8)
            if struct.unpack_from("<Q", data, off)[0] == BASE + int(target, 0)]
    for name in args.xref:
        target = data.find(name.encode() + b"\0")
        if target < 0:
            raise ValueError(f"string not found: {name}")
        result[name] = dict(string=hex(target), candidates=address_candidates(data, target))
    for target in args.address:
        result[target] = address_candidates(data, int(target, 0))
    for target in args.calls_to:
        dest = int(target, 0)
        calls = []
        for off in range(0, 0xa0000, 4):
            word, = struct.unpack_from("<I", data, off)
            if word & 0x7c000000 != 0x14000000:
                continue
            imm = word & 0x3ffffff
            if imm & (1 << 25):
                imm -= 1 << 26
            if off + imm * 4 == dest:
                calls.append(dict(offset=hex(off), kind="bl" if word >> 31 else "b"))
        result["branches_to_" + target] = calls
    windows = []
    if len(args.window) > 8:
        raise ValueError("at most eight bounded windows")
    for spec in args.window:
        off, size = (int(v, 0) for v in spec.split(":"))
        if off < 0 or off % 4 or size <= 0 or size > 4096 or off + size > len(data):
            raise ValueError("invalid disassembly bounds")
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        windows.append(dict(offset=hex(off), size=size, instructions=[
            f"{ins.address:#08x}: {ins.mnemonic} {ins.op_str}"
            for ins in decoder.disasm(data[off:off + size], off)]))
    if windows:
        result["windows"] = windows
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
