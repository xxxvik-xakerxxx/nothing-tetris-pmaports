#!/usr/bin/env python3
"""Assert producer edges from pinned LK bytes and save bounded disassembly."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from audit import BASE, cstring, payload


def contracts(data):
    def word(off):
        return struct.unpack_from("<I", data, off)[0]

    def branch(off, expected):
        ins = word(off)
        if ins & 0x7c000000 != 0x14000000:
            raise ValueError(f"not a direct branch at {off:#x}")
        imm = ins & 0x3ffffff
        if imm & (1 << 25):
            imm -= 1 << 26
        if off + 4 * imm != expected:
            raise ValueError(f"changed branch at {off:#x}")

    # Actual non-null platform getter: ADRP x0; ADD x0,x0; RET.
    off = 0x817f8
    first, second = word(off), word(off + 4)
    if first & 0x9f00001f != 0x90000000 or second & 0xffc003ff != 0x91000000:
        raise ValueError("changed table getter")
    imm = ((first >> 29) & 3) | (((first >> 5) & 0x7ffff) << 2)
    if imm & (1 << 20):
        imm -= 1 << 21
    table = (off & ~4095) + (imm << 12) + ((second >> 10) & 4095)
    if word(off + 8) != 0xd65f03c0:
        raise ValueError("getter no longer returns directly")
    for zero_return in (0x23b20, 0x23b28):
        if word(zero_return) != 0xaa1f03e0 or word(zero_return + 4) != 0xd65f03c0:
            raise ValueError("an earlier image table provider is no longer null")
    if word(0x2534c) != 0xaa1f03e0 or word(0x25354) != 0xd65f03c0:
        raise ValueError("the first image table provider changed")
    records = []
    for offset in range(table, table + 96, 32):
        kind, partition, image, flags = struct.unpack_from("<4Q", data, offset)
        records.append(dict(offset=hex(offset), kind=kind,
            partition=cstring(data, partition - BASE), image=cstring(data, image - BASE),
            flags=flags))
    if [(r["kind"], r["partition"], r["image"], r["flags"]) for r in records] != [
        (1, "modem", "md1rom", 0), (2, "modem", "md1dsp", 0), (4, "modem", "md1drdi", 0)]:
        raise ValueError("unexpected active image descriptors")
    if data[table + 96:table + 128] != bytes(32):
        raise ValueError("missing descriptor terminator")
    edges = {
        0x255bc: 0x817f8,
        0x256c4: 0x74da0, 0x74e18: 0x2a3ac, 0x74e20: 0x67e50,
        0x2a400: 0x18cec, 0x2a4d8: 0x2a5b0,
        0x74ed4: 0x7e334, 0x7e334: 0x81dbc,
        0x74f0c: 0x7e33c, 0x7e33c: 0x92634,
        0x74f18: 0x7e2e0, 0x74f28: 0x7e340, 0x7e340: 0x92eac,
        0x75030: 0x67edc, 0x75088: 0x7e344, 0x7e344: 0x93068,
        0x75004: 0x7e338, 0x7e338: 0x92b5c,
        0x750c4: 0x7e348, 0x7e348: 0x91f9c, 0x750f8: 0x7db00,
    }
    for site, target in edges.items():
        branch(site, target)
    # CB[N]Z error/success edges around the enforced authentication path.
    for site, target, nonzero in ((0x74f10, 0x751cc, True),
                                  (0x74f1c, 0x751f8, True),
                                  (0x74f2c, 0x75020, False),
                                  (0x7508c, 0x750cc, False)):
        ins = word(site)
        imm = (ins >> 5) & 0x7ffff
        if imm & (1 << 18):
            imm -= 1 << 19
        if (ins & 0x7e00001f != 0x34000000 or bool(ins & (1 << 24)) != nonzero
                or site + imm * 4 != target):
            raise ValueError(f"changed authentication result edge {site:#x}")
    return dict(active_table=hex(table), records=records,
                direct_edges={hex(k): hex(v) for k, v in edges.items()},
                authentication_result_edges_checked=4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--container", default="mt6878-probe-build")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    checked = contracts(payload(args.image.read_bytes()))
    # Two small groups; no binary executes and no container file is written.
    groups = [
        ["0x23b20:0x10", "0x817f8:0xc", "0x25598:0x50", "0x2a3ac:0x200",
         "0x18cec:0x108", "0x67e50:0x8c", "0x7e14c:0xf8"],
        ["0x74e88:0x3c4", "0x7e334:0x18", "0x81dbc:0x220",
         "0x92634:0x78", "0x92eac:0x98", "0x93068:0x80"],
    ]
    checked["windows"] = []
    for group in groups:
        command = ["docker", "exec", args.container, "python3", "-c",
                   (folder / "audit.py").read_text(), "/tmp/tetris-stock-b41-lk.img"]
        for window in group:
            command += ["--window", window]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            raise SystemExit(result.stderr)
        decoded = json.loads(result.stdout)
        checked["container_sha256"] = decoded["container_sha256"]
        checked["payload_sha256"] = decoded["payload_sha256"]
        checked["windows"] += decoded["windows"]
    if any(len(w["instructions"]) * 4 != w["size"] for w in checked["windows"]):
        raise ValueError("incomplete instruction window")
    (folder / "producer-evidence.json").write_text(json.dumps(checked, indent=2) + "\n")
    print(f"PASS: active table {checked['active_table']}; {len(checked['direct_edges'])} "
          "direct edges; 4 authentication result edges; bounded disassembly")


if __name__ == "__main__":
    main()
