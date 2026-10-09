#!/usr/bin/env python3
"""Static stock identity/instruction evidence; never execute or load an ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from elftools.elf.elffile import ELFFile

SHA256 = "6d859690d1662b3bfedf058b874e6e46b264e3a202f7d7c69c2c65d4ae5f1f6a"
RELATIVE = "vendor/lib64/mt6878/libccd.so"
# AArch64 words at exact virtual addresses in the pinned B4.1 libccd.
# These independently anchor the descriptor packing and matching CCD ioctl ABI.
WORDS = {
    0x37CA0: 0xF107FC7F,  # cmp count, 511
    0x37CE4: 0xF81F8102,  # store u64 value IOVA at descriptor + 4
    0x37CE8: 0x3305118D,  # insert register bits 16..20 at command bits 27..31
    0x37CDC: 0xEB0B0063,  # subtract current chunk from remaining count
    0x380C8: 0x52A0C00B,  # END = 0x06000000
    0x380CC: 0xF800415F,  # END value IOVA = 0
    0x38244: 0x52A34008,  # decoder register aperture = 0x1a000000
    0x38268: 0x12002108,  # count field mask = 511
    0x3826C: 0x11000500,  # decoded count = field + 1
    0x1816C: 0x528C60A1,  # worker WRITE low ioctl word = 0x6305
    0x18174: 0x72B88181,  # worker WRITE high ioctl word = 0xc40c
    0x18204: 0x528C6021,  # master INIT low ioctl word = 0x6301
    0x1820C: 0x72B80081,  # master INIT high ioctl word = 0xc004
    0x33D1C: 0x1114F129,  # central +0x40 then FH_SPARE +0x53c
    0x33D70: 0x11010361,  # second tag register +0x40
    0x33E10: 0x11050361,  # sixth tag register +0x140
    0x33E38: 0x11060361,  # seventh tag register +0x180
    0x33E60: 0x11070361,  # eighth tag register +0x1c0
}
SYMBOLS = {
    "cq_append_with_values": (0x37D30, 272),
    "cq_append_desc": (0x37CA0, 144),
    "cq_append_desc_end": (0x380B0, 48),
    "cq_desc_regaddr": (0x38240, 32),
    "camsys_sv_compose": (0x32CC0, 5256),
    "ccd_init": (0x181B0, 320),
    "ccd_ipi_send": (0x18100, 172),
}


def virtual_bytes(elf, address, size):
    for section in elf.iter_sections():
        start = section["sh_addr"]
        if start <= address and address + size <= start + section["sh_size"]:
            return section.data()[address - start:address - start + size]
    raise AssertionError(f"Unmapped ELF address {address:#x}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("--modules-repo", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.assets / "BUILD-MANIFEST.json").read_text())
    assert manifest["release"] == "Tetris_B4.1-260415-1709"
    entry = next(f for f in manifest["files"] if f["path"] == RELATIVE)
    binary = args.assets / RELATIVE
    assert entry["sha256"] == SHA256
    assert len(binary.read_bytes()) == entry["size"] == 409888
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == SHA256
    header = subprocess.check_output([
        "git", "show", "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835:"
        "mtkcam/camsys/isp7sp/cam/mtk_cam-sv-regs.h"],
        cwd=args.modules_repo, text=True)
    for name, value in (("REG_CAMSVCENTRAL_FH_SPARE_TAG_1", 0x57C),
                        ("CAMSVCENTRAL_FH_SPARE_SHIFT", 0x40)):
        definitions = [line.split() for line in header.splitlines()
                       if line.startswith("#define " + name + "\t")]
        assert len(definitions) == 1 and int(definitions[0][2], 0) == value
    with binary.open("rb") as stream:
        elf = ELFFile(stream)
        assert elf["e_machine"] == "EM_AARCH64" and elf.little_endian
        symbols = {s.name: s for s in elf.get_section_by_name(".dynsym").iter_symbols()}
        for name, (address, size) in SYMBOLS.items():
            assert symbols[name]["st_value"] == address, name
            assert symbols[name]["st_size"] == size, name
        for address, instruction in WORDS.items():
            assert struct.unpack("<I", virtual_bytes(elf, address, 4))[0] == instruction, hex(address)
        assert virtual_bytes(elf, 0xB851, 13) == b"/dev/mtk_ccd\0"
        needed = [t.needed for t in elf.get_section_by_name(".dynamic").iter_tags()
                  if t.entry.d_tag == "DT_NEEDED"]
        assert needed == ["libcutils.so", "liblog.so", "libutils.so",
                          "libmtkcam_perfctrl_wrapper.so", "libc++.so",
                          "libc.so", "libm.so", "libdl.so"]
    print("Matching B4.1 CCD identity, CQ encoding and ioctl evidence PASS (static only)")


if __name__ == "__main__":
    main()
