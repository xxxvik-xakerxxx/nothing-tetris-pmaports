#!/usr/bin/env python3
"""Check exact vendor register provenance and generate the isolated backend patch."""
import argparse
import difflib
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
DEVICE = "ee2be53cb75670b548948636a0db1d1ff112bf12"
VENDOR = "mtkcam/camsys/isp7sp/cam/mtk_csi_phy_3_1/"
OUTPUT = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0115-media-platform-mediatek-mt6878-seninf-transaction-backend.patch"


def show(repo, commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"],
                                   cwd=repo, text=True)


def check(modules, device):
    phy = show(modules, MODULES, VENDOR + "mtk_cam-seninf-hw_phy_3_1.c")
    analog = show(modules, MODULES, VENDOR + "mtk_cam-seninf-mipi-rx-ana-cdphy-csi0a.h")
    mux = show(modules, MODULES, VENDOR + "mtk_cam-seninf-seninf1-mux.h")
    top = show(modules, MODULES, VENDOR + "mtk_cam-seninf-top-ctrl.h")
    csi = show(modules, MODULES, VENDOR + "mtk_cam-seninf-seninf1-csi2.h")
    defs = show(modules, MODULES, "mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-def.h")
    route = show(modules, MODULES, "mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-route.c")
    dts = show(device, DEVICE, "arch/arm64/boot/dts/mediatek/mt6878.dts")
    for source, name, value in ((analog, "CDPHY_RX_ANA_0", "0x0000"),
                                 (analog, "CDPHY_RX_ANA_8", "0x0020"),
                                 (mux, "SENINF_MUX_CTRL_0", "0x0000"),
                                 (mux, "SENINF_MUX_CTRL_1", "0x0004"),
                                 (mux, "SENINF_MUX_OPT", "0x0008"),
                                 (csi, "SENINF_CSI2_EN", "0x0000")):
        assert re.search(r"#define\s+" + name + r"\s+" + value + r"\b", source)
    fields = ("RG_CSI0_L0_T0AB_EQ_OS_CAL_EN", "RG_CSI0_L1_T1AB_EQ_OS_CAL_EN",
              "RG_CSI0_L2_T1BC_EQ_OS_CAL_EN", "RG_CSI0_XX_T0BC_EQ_OS_CAL_EN",
              "RG_CSI0_XX_T0CA_EQ_OS_CAL_EN", "RG_CSI0_XX_T1CA_EQ_OS_CAL_EN")
    for bit, field in enumerate(fields, 16):
        assert f"#define {field}_SHIFT {bit}" in analog
        assert f"#define {field}_MASK (0x1 << {bit})" in analog
    for field, bit in (("RG_CSI0_BG_CORE_EN", 0), ("RG_CSI0_BG_LPF_EN", 1)):
        assert f"#define {field}_SHIFT {bit}" in analog
    for field, mask, bit in (("RG_SENINF_MUX_SRC_SEL", "0xf", 0),
                              ("RG_SENINF_MUX_PIX_MODE_SEL", "0x7", 8),
                              ("RG_SENINF_MUX_VS_SPLIT_EN", "0x1", 3),
                              ("RG_SENINF_MUX_HSYNC_POL", "0x1", 16),
                              ("RG_SENINF_MUX_VSYNC_POL", "0x1", 17)):
        assert f"#define {field}_MASK ({mask} << {bit})" in mux
    for index in range(13):
        assert f"#define RG_SENINF_MUX{index + 1}_SRC_SEL_MASK (0x1f << {(index % 4) * 8})" in top
    for index in range(4):
        assert f"#define SENINF_TOP_MUX_CTRL_{index} 0x{0x10 + index * 4:04x}" in top
    assert "if_base + 0x0d00 + (0x1000 * j)" in phy
    assert "if_base + 0x0a00 + (0x1000 * i)" in phy
    assert "ana_base + 0x8000" in phy and "ana_base + 0x9000" in phy
    body = phy.split("static int csirx_phyA_power_on", 1)[1].split("#ifdef CSI_EFUSE_SET", 1)[0]
    assert [int(v) for v in re.findall(r"udelay\((\d+)\)", body)] == [200, 30, 1, 1]
    assert body.index("RG_CSI0_BG_LPF_EN, 0") < body.index("RG_CSI0_BG_CORE_EN, 0")
    assert "temp | 0x6" in phy and "temp & 0xFFFFFFF9" in phy
    assert "group_src + MIPI_SENSOR" in route and "MIPI_SENSOR = 0x8" in defs
    assert "VC_CH_GROUP_3" in defs
    assert "mux-num = <13>" in dts and "seninf-num = <12>" in dts
    header = (HERE / "mt6878-seninf-mux.h").read_text()
    assert not re.search(r"\b(?:readl|writel|ioremap|pm_runtime_get_sync)\s*\(", header)
    assert "tx->plan.port != plan->port" in header
    assert "tx->first_error = ret" in header
    assert "tx->off_attempted" in header


def patch_text():
    path = "drivers/media/platform/mediatek/seninf/mt6878-seninf-mux.h"
    source = (HERE / "mt6878-seninf-mux.h").read_text()
    result = "From: Codex <codex@openai.com>\n"
    result += "Subject: [PATCH] media: mediatek: add checked SENINF analog/mux transactions\n\n"
    result += "No runtime adapter or graph activation. Exact vendor partial sequences\n"
    result += "require caller-proven power/calibration/route ownership; no guessed\n"
    result += "ready polling or claims of complete PHY/DMA bring-up. First errors\n"
    result += "and immutable allocation plans survive explicit one-shot shutdown.\n\n"
    result += f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
    result += "".join(difflib.unified_diff([], source.splitlines(keepends=True),
                                        fromfile="/dev/null", tofile="b/" + path))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--device-repo", type=Path, required=True)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    check(args.modules_repo, args.device_repo)
    text = patch_text()
    if args.generate:
        OUTPUT.write_text(text)
    else:
        assert OUTPUT.read_text() == text, "generated backend patch is stale"
    with tempfile.TemporaryDirectory(prefix="seninf-backend-apply-") as temporary:
        subprocess.run(["patch", "--batch", "-p1", "-i", str(OUTPUT)],
                       cwd=temporary, check=True)
        installed = Path(temporary) / "drivers/media/platform/mediatek/seninf/mt6878-seninf-mux.h"
        assert installed.read_text() == (HERE / "mt6878-seninf-mux.h").read_text()
    print("PASS: exact analog/mux/CSI register fields, offsets, counts and delay order")
    print("PASS: pinned source and immutable-plan/first-error/no-live-adapter guards")
    print("Native fault-injection tests are prepared for CI; not compiled locally")
