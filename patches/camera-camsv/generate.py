#!/usr/bin/env python3
"""Pinned CAMSV CQ/buffer bridge. No Kconfig/Makefile/DT activation."""
import argparse
import difflib
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
DEVICE = "ee2be53cb75670b548948636a0db1d1ff112bf12"
PREFIX = "mtkcam/camsys/isp7sp/cam/"
OUTPUT = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0117-media-platform-mediatek-mt6878-camsv-buffer-cq.patch"


def show(repo, commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=repo, text=True)


def bits(text, union, field):
    body = text.split("union " + union + " {", 1)[1].split("} Bits", 1)[0]
    shift = 0
    for name, width in re.findall(r"unsigned int\s+(\w+)\s*:\s*(\d+)", body):
        width = int(width)
        if name == field:
            return shift, width
        shift += width
    raise AssertionError(field)


def registers(modules, device):
    regs = show(modules, MODULES, PREFIX + "mtk_cam-sv-regs.h")
    fmt = show(modules, MODULES, "mtkcam/camsys/common/mtk_cam-fmt.h")
    utils = show(modules, MODULES, PREFIX + "mtk_cam-fmt_utils.c")
    assert "ALIGN(bpp, 16) << pixel_mode_shift" in utils
    assert "return bus_size / 8" in utils and "return ALIGN(bytes, bus_size)" in utils
    sv = show(modules, MODULES, PREFIX + "mtk_cam-sv.c")
    camera = show(modules, MODULES, PREFIX + "mtk_cam.c")
    assert "alloc_dev = cam_dev->smmu_dev ? : dev" in camera
    assert "dma_set_mask_and_coherent(alloc_dev, DMA_BIT_MASK(34))" in camera
    plat = show(modules, MODULES, PREFIX + "mtk_cam-plat-mt6878.c")
    dt = show(device, DEVICE, "arch/arm64/boot/dts/mediatek/mt6878.dts")
    cammux = show(modules, MODULES, PREFIX + "mtk_csi_phy_3_1/mtk_cam-seninf-cammux-pcsr.h")
    top = show(modules, MODULES, PREFIX + "mtk_csi_phy_3_1/mtk_cam-seninf-hw_phy_3_1.c")
    assert "*smi_common_id = 31" in plat and "*reset_enable = true" in plat
    assert "dma_sw_ctl & 0x2" in sv and "cq_dma_sw_ctl & 0x2" in sv
    assert "100000 /* timeout, us */" in sv
    assert "if_base + 0x17000 + (0x0040 * k)" in top
    assert "cammux_id = sv_dev->cammux_id + tag_idx" in sv
    for number, base in ((1, 0), (2, 8)):
        node = dt.split(f"camsv{number}@", 1)[1].split("\n\t\t};", 1)[0]
        assert f"mediatek,cammux-id = <{base}>" in node
        assert '"base_DMA", "base_SCQ", "inner_base"' in node
        assert "dma-ranges = <0x0 0x0 0x0 0x0 0x4 0x0>" in node
    assert "<\u0026disp_iommu M4U_L14_P1_CAMSV_A0_WDMA>" in dt
    assert "<\u0026disp_iommu M4U_L13_P1_CAMSV_B0_WDMA>" in dt
    ports = show(device, DEVICE, "include/dt-bindings/memory/mt6878-larb-port.h")
    memory = show(device, DEVICE, "include/dt-bindings/memory/mtk-memory-port.h")
    assert "((larb & 0x3f) << 5) | (port & 0x1f)" in memory
    for larb in (13, 14):
        for port in (0, 1):
            assert f"MTK_M4U_PORT_ID(MM_TAB, NORMAL_DOM, {larb}, {port})" in ports
    assert bits(regs, "CAMSVCQ_CQ_EN", "CAMSVCQ_SCQ_STAGGER_MODE") == (12, 1)
    assert bits(regs, "CAMSVCQ_CQ_EN", "CAMSVCQ_CQ_RESET") == (16, 1)
    assert bits(regs, "CAMSVCQ_CQ_SUB_EN", "CAMSVCQ_CQ_SUB_RESET") == (16, 1)
    assert bits(regs, "CAMSVCQ_CQ_SUB_THR0_DESC_SIZE_2", "CAMSVCQ_CQ_SUB_THR0_DESC_SIZE_2") == (0, 16)
    names = {
        "SV_CQ_SIZE": "REG_CAMSVCQ_CQ_SUB_THR0_DESC_SIZE_2",
        "SV_CQ_MSB": "REG_CAMSVCQ_CQ_SUB_THR0_BASEADDR_2_MSB",
        "SV_CQ_LSB": "REG_CAMSVCQ_CQ_SUB_THR0_BASEADDR_2",
        "SV_CQ_START": "REG_CAMSVCQTOP_THR_START", "SV_CQ_EN": "REG_CAMSVCQ_CQ_EN",
        "SV_CQ_SUB_EN": "REG_CAMSVCQ_CQ_SUB_EN", "SV_DMA_RESET": "REG_CAMSVDMATOP_SW_RST_CTL",
        "SV_CQ_RESET": "REG_CAMSVCQTOP_SW_RST_CTL", "SV_DCM_DIS": "REG_CAMSVCENTRAL_DCM_DIS",
        "SV_SW_CTL": "REG_CAMSVCENTRAL_SW_CTL",
    }
    out = "/* SPDX-License-Identifier: GPL-2.0-only */\n"
    out += "/* Generated vendor register definitions, Copyright (c) 2020 MediaTek Inc. */\n"
    for name in ("BAYER8", "BAYER10", "BAYER10_MIPI"):
        value = re.search(r"MTKCAM_IPI_IMG_FMT_" + name + r"\s*=\s*(\d+)", fmt)[1]
        out += f"#define SV_DMA_FMT_{name} {value}\n"
    for local, vendor in names.items():
        value = re.search(r"^#define[ \t]+" + vendor + r"[ \t]+(0x[\da-fA-F]+)\b", regs, re.M)[1]
        out += f"#define {local} {value}\n"
    out += "#define SV_CAMMUX_OPT 0x0004\n#define SV_VC_MASK 0x1f\n#define SV_DT_MASK 0x3f00\n#define SV_DT_SHIFT 8\n#define SV_VC_EN_MASK 0x80\n#define SV_DT_EN_MASK 0x8000\n"
    for name, mask, shift in (("VC_SEL", "0x1f", 0), ("DT_SEL", "0x3f", 8), ("VC_SEL_EN", "0x1", 7), ("DT_SEL_EN", "0x1", 15)):
        assert f"#define RG_SENINF_CAM_MUX_PCSR_{name}_MASK ({mask} << {shift})" in cammux
    assert "#define SENINF_CAM_MUX_PCSR_OPT 0x0004" in cammux
    for i in range(4):
        assert re.search(r"#define CAMSVCENTRAL_SW_GP_PASS1_DONE_" + str(i) + r"_ST\s+BIT\(" + str(16 + i) + r"\)", regs)
        assert f"irq_info.done_tags |= sv_dev->active_group_info[{i}]" in sv
    return out


def patch_text(registers):
    text = "From: Codex <codex@openai.com>\nSubject: [PATCH] media: mediatek: prepare checked CAMSV buffer/CQ ownership\n\n"
    text += "Source-grounded CQ submission/reset, VC filters and paired vb2 completion.\nComposer/IRQ/resource owners must be supplied; no runtime activation.\n\n"
    for name in ("mt6878-camsv-capture.h", "mt6878-camsv-registers.h", "mt6878-camsv-vb2.h", "mt6878-camsv-vb2.c"):
        source = registers if name.endswith("registers.h") else (HERE / name).read_text()
        path = "drivers/media/platform/mediatek/seninf/" + name
        text += f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
        text += "".join(difflib.unified_diff([], source.splitlines(keepends=True), fromfile="/dev/null", tofile="b/" + path))
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--device-repo", type=Path, required=True)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    generated = registers(args.modules_repo, args.device_repo)
    patch = patch_text(generated)
    if args.generate:
        (HERE / "mt6878-camsv-registers.h").write_text(generated)
        OUTPUT.write_text(patch)
    else:
        assert (HERE / "mt6878-camsv-registers.h").read_text() == generated
        assert OUTPUT.read_text() == patch
    print("PASS: pinned CQ/reset/group/VC fields, CAMSV resource/DMA aperture and generation")
