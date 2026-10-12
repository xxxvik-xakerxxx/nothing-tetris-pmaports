#!/usr/bin/env python3
"""Decode pinned source/ATF metadata offline; no SMC, MMIO or emulation."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
UBOOT = "8d2ccc12e7861c5726e9c37a07f62c4ae18db7b5"
ATF_SHA = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"
UPSTREAM = Path(__file__).resolve().parents[3].parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=UPSTREAM / "android_kernel_device_modules_6.1_nothing_mt6878")
    parser.add_argument("--uboot", type=Path, default=UPSTREAM / "u-boot-mt6878")
    parser.add_argument("--atf", type=Path, required=True, help="exact declared ATF MTK container; read only")
    args = parser.parse_args()
    sources, anchors = {}, []

    def read(label, root, revision, path):
        raw = subprocess.run(["git", "-C", str(root), "show", revision + ":" + path],
                             check=True, capture_output=True).stdout
        sources[label] = {"revision": revision, "path": path,
                          "sha256": hashlib.sha256(raw).hexdigest()}
        return raw.decode("utf-8")

    def anchor(label, text, needle):
        if text.count(needle) != 1:
            raise ValueError("source anchor changed: " + needle)
        anchors.append({"source": label, "line": text[:text.index(needle)].count("\n") + 1,
                        "anchor": needle})

    header = read("emi-header", args.vendor, VENDOR, "include/soc/mediatek/emi.h")
    v2 = read("v2-decoder", args.vendor, VENDOR, "drivers/memory/mediatek/emi-mpu-test-v2.c")
    smpu = read("cpu-aid", args.vendor, VENDOR, "drivers/memory/mediatek/smpu.c")
    dt = read("smpu-dt", args.vendor, VENDOR, "arch/arm64/boot/dts/mediatek/mt6878.dts")
    board = "board/mediatek/mt6878/"
    policy = read("boot-policy", args.uboot, UBOOT, board + "tetris_modem_emi.c")
    evidence = read("boot-evidence", args.uboot, UBOOT, board + "tetris_modem_smem_evidence.c")
    brom = read("boot-admission", args.uboot, UBOOT, board + "tetris_modem_brom_board.c")
    anchor("emi-header", header, "#define MTK_EMIMPU_NO_PROTECTION\t0")
    anchor("emi-header", header, "#define MTK_EMIMPU_READ_APC\t\t2")
    anchor("emi-header", header, "#define MTK_EMIMPU_READ_AID\t\t4")
    anchor("v2-decoder", v2, "static const char *aid_permission[4] = {")
    labels = re.findall(r'"([^\"]+)"', v2.split("aid_permission[4] = {", 1)[1].split("};", 1)[0])
    if labels != ["No", "WO", "RO", "RW"]:
        raise ValueError("v2 permission labels changed")
    anchor("cpu-aid", smpu, "int ns_cpu_aid = 241;")
    anchor("cpu-aid", smpu, "int sec_cpu_aid = 240;")
    anchor("cpu-aid", smpu, "int hyp_cpu_aid = 243;")
    anchor("smpu-dt", dt, "nsmpu: nsmpu@10351000 {")
    anchor("boot-policy", policy, "/* AID order: 35, 47, 93. Values are No / WO / RO / RW (0..3). */")
    table = policy.split("shared_aids[3][9] = {", 1)[1].split("};", 1)[0]
    rows = [[int(n) for n in re.findall(r"\d+", row)] for row in re.findall(r"\{([^}]+)\}", table)]
    if rows != [[35, 37, 47, 241], [35, 38, 39, 42, 43, 44, 45, 47, 241], [35, 40, 47, 241]]:
        raise ValueError("installed normal boot policy changed")
    anchor("boot-evidence", evidence, "encode64(record + 56, transaction->reply[12]);")
    anchor("boot-evidence", evidence, "encode64(record + 64 + group * 8, transaction->reply[13 + group]);")
    anchor("boot-admission", brom, 'ret = disabled(final, "mediatek,mt6878-modem-power-controller");')

    raw = args.atf.read_bytes()
    if len(raw) != 900752 or struct.unpack_from("<II", raw) != (0x58881688, 900240):
        raise ValueError("not the declared ATF container")
    payload = raw[512:]
    if hashlib.sha256(payload).hexdigest() != ATF_SHA:
        raise ValueError("unknown ATF; offsets must be re-audited")
    handler, fid32, fid64, _, _ = struct.unpack_from("<QIIQQ", payload, 0x58e80)
    if (handler, fid32, fid64) != (0x4882f750, 0x82000415, 0xc2000415):
        raise ValueError("ATF BL_EMIMPU descriptor changed")
    query_targets = {str(q): hex(0x2f530 + 4 * payload[0x50435 + q]) for q in range(10)}
    if query_targets["2"] != "0x2f548" or query_targets["4"] != "0x2f558":
        raise ValueError("ATF read dispatch changed")
    # Only decode instructions. Never import an emulator or run the payload.
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    slices = {}
    for name, start, end in (("unused-query2", 0x2f548, 0x2f550),
                             ("aid-reader", 0x2f464, 0x2f510),
                             ("enable-reader", 0x2f57c, 0x2f5c4),
                             ("range-writer", 0x2d61c, 0x2d670),
                             ("range-admission", 0x2f618, 0x2f69c),
                             ("one-shot-guard", 0x10380, 0x103d0)):
        slices[name] = [{"offset": hex(i.address), "instruction": i.mnemonic + " " + i.op_str}
                        for i in decoder.disasm(payload[start:end], start)]
    if [i["instruction"].strip() for i in slices["unused-query2"]] != ["mov x0, xzr", "ret"]:
        raise ValueError("query2 no longer returns literal zero")

    slots = []
    for slot in (42, 43):
        aids = rows[slot - 41]
        words = [sum(3 << (2 * (aid % 32)) for aid in aids if aid // 32 == group)
                 for group in range(8)]
        ns_cpu = (words[7] >> 34) & 3
        if ns_cpu != 3:
            raise ValueError("NS CPU permission changed")
        slots.append({
            "slot": slot, "aid_rw": aids, "policy_words": [hex(w) for w in words],
            "ns_cpu_aid": 241, "ns_cpu_group": 7, "ns_cpu_shift": 34,
            "ns_cpu_value": ns_cpu, "ns_cpu_permission": labels[ns_cpu],
            "aid0_value": words[0] & 3, "aid0_permission": labels[words[0] & 3],
            "wire_bank": slot - 42, "wire_policy_group7_offset": 80 + (slot - 42) * 128 + 64 + 7 * 8,
            "wire_enable_offset": 80 + (slot - 42) * 128 + 56,
            "start_register": hex(0x10351000 + (slot - 1) * 8),
            "end_register": hex(0x10351004 + (slot - 1) * 8),
            "enable_register": hex(0x103512a4 + ((slot - 1) // 32) * 4),
            "enable_bit": (slot - 1) % 32,
            "selected_aid241_read_register": hex(0x103519e4 + ((slot - 1) // 16) * 4),
            "selected_aid241_read_shift": 2 * ((slot - 1) % 16),
        })
    print(json.dumps({
        "method": "pinned source parsing and static ATF disassembly; no target execution",
        "trust_model": "ordinary trusted bootloader handing its successful transaction to Linux; no new NS certificate",
        "classic_apc_zero": "NO_PROTECTION in legacy header; not this v2 permission field",
        "actual_query2_zero": "constant return from unused/default query; no AP permission register was read",
        "v2_aid_zero": "No; AID0 is not the pinned NS CPU AID",
        "initial_ns_cpu_rights": "RW in both enabled slots42/43 through AID241=3",
        "lifetime": "boot snapshot, not immutable hardware policy or exclusive memory ownership",
        "scope": "reported programmed service ranges; not entire reservation tails or MMIO/IRQ/DMA authority",
        "sources": sources, "anchors": anchors, "slots": slots,
        "atf": {"payload_sha256": ATF_SHA, "query_targets": query_targets, "disassembly": slices},
        "remaining": ["current effective overlapping-region/NSR/KP policy", "actual execution EL/master identity",
                      "secure policy writers and power-cycle lifetime", "first MD shutdown and inhibited restart",
                      "installed BROM hook requires native MD provider disabled on entry"],
    }, indent=2))


if __name__ == "__main__":
    main()
