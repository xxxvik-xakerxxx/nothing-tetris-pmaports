#!/usr/bin/env python3
"""Read exact vendor Git objects; check camera resource/register provenance."""
import argparse
from pathlib import Path
import re
import subprocess

DEVICE = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
HERE = Path(__file__).resolve().parent


def source(repo, commit, path):
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=repo, text=True)


def node(dts, label):
    match = re.search(r"\b" + re.escape(label) + r":\s*[^{}]+\{([^{}]*)\};", dts, re.S)
    if not match:
        raise ValueError("missing DT resource: " + label)
    return match[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-repo", type=Path, required=True)
    parser.add_argument("--modules-repo", type=Path, required=True)
    args = parser.parse_args()
    dts = source(args.device_repo, DEVICE, "arch/arm64/boot/dts/mediatek/mt6878.dts")
    smi = source(args.device_repo, DEVICE, "drivers/memory/mtk-smi.c")
    power = source(args.device_repo, DEVICE, "drivers/soc/mediatek/mtk-scpsys-mt6878.c")
    logical = source(args.modules_repo, MODULES, "mtkcam/camsys/isp7sp/cam/mtk_cam-larb.c")
    for larb, common in ((13, 0), (14, 1)):
        physical = node(dts, "smi_larb" + str(larb))
        assert f"mediatek,larb-id = <{larb}>" in physical
        assert f"<&smi_cam_4x1_sub_comm{common} 0>" in physical
        assert 'clock-names = "apb"' in physical
        assert "MT6878_POWER_DOMAIN_CAM_MAIN" in physical
    for label, commonid in (("smi_cam_4x1_sub_comm0", 16), ("smi_cam_4x1_sub_comm1", 19)):
        common = node(dts, label)
        assert f"mediatek,common-id = <{commonid}>" in common
        assert "<&smi_cam_vcore_2x1_sub_comm0 0>" in common
        assert '"apb", "smi", "gals0", "gals1", "gals2", "gals3", "gals4"' in common
        assert "CLK_CAM_MR_GALS" in common and "CLK_CAM_MR_LARBX" in common
    common = node(dts, "smi_cam_vcore_2x1_sub_comm0")
    assert "MT6878_POWER_DOMAIN_CAM_VCORE" in common and "CLK_CAM_VCORE_MM0_DCM_DIS" in common
    assert "<&smi_disp_common 0>" in common
    assert "{MT6878_POWER_DOMAIN_CAM_VCORE, MT6878_POWER_DOMAIN_CAM_MAIN}" in power
    assert "{MT6878_POWER_DOMAIN_MM_INFRA, MT6878_POWER_DOMAIN_CAM_VCORE}" in power
    assert "dma_set_mask_and_coherent(dev, DMA_BIT_MASK(34))" in logical
    bwl = smi.split("mtk_smi_larb_mt6878_bwl[", 1)[1].split("};", 1)[0]
    own = (HERE / "mt6878-camisp-smi.inc").read_text()
    for id in (13, 14):
        row = re.search(r"\{([^{}]+)\},\s*/\* LARB" + str(id) + r" \*/", bwl)[1]
        values = [int(item.strip(), 0) for item in row.split(",") if item.strip()]
        actual = re.search(r"camisp_larb" + str(id) + r"_bwl\[\] = \{([^{}]+)\}", own)[1]
        assert values == [int(item.strip(), 0) for item in actual.split(",")]
    for item in ("SMI_LARB_NONSEC_CON(id)\t(0x380", "#define F_MMU_EN\t\tBIT(0)",
                 "#define INT_SMI_LARB_STAT\t\t(0x500)"):
        assert item in smi, item
    for item in ("0x370256", "0x2146", "0x2105"):
        assert item in smi and item in own
    print(f"Pinned B4.1 CAMISP topology/register trace PASS: device={DEVICE}, modules={MODULES}")


if __name__ == "__main__":
    main()
