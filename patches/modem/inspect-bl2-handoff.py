#!/usr/bin/env python3
"""Inspect pinned container code offline; addresses printed are file offsets."""
import argparse
import hashlib
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

SHA = "170583094d4e4388d8e269cbcc8b14c17df0d4e248dcef57f1d112fba84c004b"
ATF_SHA = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"


def extract(image, component="bl2_ext"):
    offset = 0
    while offset + 512 <= len(image):
        magic, size = struct.unpack_from("<II", image, offset)
        if magic != 0x58881688 or not size or offset + 512 + size > len(image):
            raise ValueError("invalid container boundary")
        name = image[offset + 8:offset + 40].split(b"\0")[0]
        data = image[offset + 512:offset + 512 + size]
        if name == component.encode("ascii"):
            expected = SHA if component == "bl2_ext" else ATF_SHA
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("unrecognized component; re-audit provenance")
            return data
        offset = (offset + 512 + size + 15) & ~15
    raise ValueError("missing bl2_ext")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--component", choices=("bl2_ext", "atf"), default="bl2_ext")
    parser.add_argument("--start", type=lambda s: int(s, 0))
    parser.add_argument("--end", type=lambda s: int(s, 0))
    args = parser.parse_args()
    data = extract(args.image.read_bytes(), args.component)
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.skipdata = True
    if args.start is not None:
        if args.end is None or not 0 <= args.start < args.end <= len(data):
            raise ValueError("invalid bounded disassembly range")
        if args.end - args.start > 8192:
            raise ValueError("range exceeds 8 KiB")
        for address, size, name, operands in md.disasm_lite(
                data[args.start:args.end], args.start):
            print(f"{address:08x}: {name:8s} {operands}")
        return
    needles = (b"app_load_bl33() == NO_ERROR", b"load bl33",
               b"bl33 addr:%llx", b"boot_arg(PL2LK)", b"main_dtb_addr")
    if args.component == "atf":
        needles = (b"p_mtk_bl_param is NULL!", b"BL31: %s", b"BL33_SECOS")
    targets = {}
    for needle in needles:
        at = data.find(needle)
        if at < 0:
            raise ValueError(f"missing expected string {needle!r}")
        start = data.rfind(b"\0", 0, at) + 1
        targets[start] = needle.decode()
    print("String offsets:", {hex(k): v for k, v in targets.items()})
    previous = []
    for address, size, name, operands in md.disasm_lite(data, 0):
        fields = operands.split(", ")
        target = None
        if name == "adr" and len(fields) == 2:
            target = int(fields[1].lstrip("#"), 0)
        elif name == "add" and len(fields) == 3 and fields[2].startswith("#"):
            for pa, pn, pf in reversed(previous[-4:]):
                if pn == "adrp" and pf[0] == fields[1]:
                    target = int(pf[1].lstrip("#"), 0) + int(fields[2][1:], 0)
                    break
        if target in targets:
            print(f"candidate xref {address:#x}: {name} {operands}: {targets[target]}")
        previous.append((address, name, fields))
        previous = previous[-4:]
    print("Candidate xrefs require manual control-flow/clobber validation; no code executed")


if __name__ == "__main__":
    main()
