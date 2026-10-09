#!/usr/bin/env python3
"""Read-only matching ELF/pinned source gates for the native CAMSV recipe."""
import argparse
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import sys

from elftools.elf.elffile import ELFFile

PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
SHA256 = "6d859690d1662b3bfedf058b874e6e46b264e3a202f7d7c69c2c65d4ae5f1f6a"
WORDS = {
    0x32FD4: 0x1A9F17F7,  # metadata-off == 0 -> crop config 1
    0x33240: 0x72A00029,  # WDMA basic relative delta 0x101d0
    0x33244: 0x2A194108,  # stride << 16, low basic word 0x10
    0x33290: 0xB81EC3B9,  # first output buffer IOVA low
    0x3329C: 0xD360FF28,  # first output buffer IOVA high
    0x33420: 0x52900008,  # first crop FBC0 0x8000
    0x335B4: 0x52901008,  # output FBC0 0x8080
    0x337CC: 0xB81EC3A8,  # error ctl value stored (0x20)
    0x338CC: 0x52A001E8,  # DONE status enable 0xf0000, NOT ACK
    0x33948: 0x3200E3E8,  # channel ctl 0x11111111
    0x34888: 0xB81F43BB,  # group0 = first-order tags mask
    0x34918: 0xB81F43B5,  # last tag = selected lowest first-order bit
    0x3493C: 0xB81F43B3,  # first tag = same bit in simple branch
    0x395E4: 0x94008767,  # real session caller -> camsys_frame_process@plt
    0x39600: 0x52800962,  # real ACK size = 75
    0x3987C: 0x52800062,  # mmap64 PROT_READ|PROT_WRITE
    0x39880: 0x52800023,  # mmap64 MAP_SHARED
    0x39894: 0x29410404,  # load real fd and size from session buffer +8/+12
}
REGISTERS = {
    "REG_CAMSVCENTRAL_GRAB_PXL_TAG1": 0x548,
    "REG_CAMSVCENTRAL_GRAB_LIN_TAG1": 0x54C,
    "REG_CAMSVCENTRAL_FORMAT_TAG1": 0x554,
    "REG_CAMSVCENTRAL_CONFIG_TAG1": 0x55C,
    "REG_CAMSVCENTRAL_FBC0_TAG1": 0x540,
    "REG_CAMSVDMATOP_WDMA_BASE_ADDR_IMG1": 0x200,
    "REG_CAMSVDMATOP_WDMA_BASE_ADDR_MSB_IMG1": 0x204,
    "REG_CAMSVDMATOP_WDMA_BASIC_IMG1": 0x210,
    "REG_CAMSVCENTRAL_GROUP_TAG0": 0x1B8,
    "REG_CAMSVCENTRAL_LAST_TAG": 0x1C8,
    "REG_CAMSVCENTRAL_FIRST_TAG": 0x1CC,
    "REG_CAMSVCENTRAL_DONE_STATUS_EN": 0x344,
    "REG_CAMSVCENTRAL_ERR_STATUS_EN": 0x34C,
    "REG_CAMSVCENTRAL_SOF_STATUS_EN": 0x35C,
}


def at(elf, address, size):
    for section in elf.iter_sections():
        start = section["sh_addr"]
        if start <= address and address + size <= start + section["sh_size"]:
            return section.data()[address-start:address-start+size]
    raise AssertionError(f"Unmapped ELF address {address:#x}")


def source(repo, path):
    return subprocess.check_output(["git", "show", f"{PIN}:{path}"], cwd=repo, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("--modules-repo", required=True, type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    subprocess.run([sys.executable, str(here / "check.py"), str(args.assets),
                    "--modules-repo", str(args.modules_repo)], check=True)
    binary = args.assets / "vendor/lib64/mt6878/libccd.so"
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == SHA256
    with binary.open("rb") as stream:
        elf = ELFFile(stream)
        for address, word in WORDS.items():
            assert struct.unpack("<I", at(elf, address, 4))[0] == word, hex(address)
        # Exact format tables: Bayer8=0, Bayer10=1, Bayer10_MIPI=8.
        for value, destination in ((0, 0x34A34), (1, 0x349E4), (80, 0x349FC)):
            assert 0x349DC + at(elf, 0xF83C + value, 1)[0] * 4 == destination
            assert 0x34A6C + at(elf, 0xF88D + value, 1)[0] * 4 == 0x34A6C
        symbols = {s.name: s for s in elf.get_section_by_name(".dynsym").iter_symbols()}
        assert symbols["ipi_cam_handler"]["st_value"] == 0x39350
        assert symbols["camsys_frame_process"]["st_value"] == 0x352C0
    register_header = source(args.modules_repo, "mtkcam/camsys/isp7sp/cam/mtk_cam-sv-regs.h")
    for name, value in REGISTERS.items():
        definitions = re.findall(r"^#define\s+" + name + r"\s+(0x[0-9a-fA-F]+)\s*$",
                                 register_header, re.MULTILINE)
        assert definitions and all(int(d, 16) == value for d in definitions), name
    sv = source(args.modules_repo, "mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c")
    done = sv.split("irqreturn_t mtk_irq_camsv_done(", 1)[1].split("\nbool is_all_tag_setting", 1)[0]
    assert "writel" not in done and "REG_CAMSVCENTRAL_DONE_STATUS" in done
    assert done.count("readl_relaxed(") == 4
    ipi = source(args.modules_repo, "mtkcam/camsys/rpmsg/mtk_ccd_rpmsg_ipi.c")
    assert "wait_event_interruptible" in ipi and "write_obj->src" in ipi
    read = ipi.split("int ccd_worker_read(", 1)[1].split("EXPORT_SYMBOL_GPL(ccd_worker_read)", 1)[0]
    assert "TASK_UNINTERRUPTIBLE" in read and "msecs_to_jiffies(200)" in read
    assert "wait_event_interruptible" in read and "goto err_ret;" in read
    assert "err_ret:" in read and "return 0;" in read.split("err_ret:", 1)[1]
    assert "void ccd_worker_write(" in ipi
    ccd = source(args.modules_repo, "mtkcam/camsys/remoteproc/mtk_ccd.c")
    write_ioctl = ccd.split("case IOCTL_CCD_WORKER_WRITE:", 1)[1].split("default:", 1)[0]
    assert "ccd_worker_write(ccd, &work_obj);" in write_ioctl
    assert "ret = ccd_worker_write" not in write_ioctl
    recipe = (here / "mt6878-camera-camsv-recipe.h").read_text()
    assert "readl" not in recipe and "writel" not in recipe
    assert recipe.index("/* Validate every target") < recipe.index("ret = mt6878_ccd_cq_values")
    print("CAMSV recipe format/register/session caller evidence PASS (static only)")
    print("IRQ DONE source reads only; acknowledgment hardware semantics remain unproven")
    print("CCD READ unbounded/empty-after-interruption; WRITE acceptance is not delivery")


if __name__ == "__main__":
    main()
