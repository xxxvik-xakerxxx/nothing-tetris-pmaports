#!/usr/bin/env python3
"""Pinned-source and patch-application checks; no native compilation."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from generate import HERE, OUTPUT, new_files, patch_text

DEVICE = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"


def show(repo, commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"],
                                   cwd=repo, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-repo", type=Path, required=True)
    parser.add_argument("--modules-repo", type=Path, required=True)
    parser.add_argument("--kernel-tree", type=Path, required=True)
    args = parser.parse_args()
    assert OUTPUT.read_text() == patch_text(args.kernel_tree)
    dts = show(args.device_repo, DEVICE, "arch/arm64/boot/dts/mediatek/mt6878.dts")
    node = dts.split("seninf_top: seninf-top@", 1)[1].split("\n\t\t};", 1)[0]
    names = re.findall(r'"([^"]+)"', node.split("clock-names =", 1)[1].split(";", 1)[0])
    code = (HERE / "mt6878-seninf-graph.c").read_text()
    code_names = re.findall(r'"([^"]+)"', code.split("mt6878_seninf_clock_names[] = {", 1)[1].split("};", 1)[0])
    assert names == code_names and len(names) == 12
    assert 'reg-names = "base", "ana-rx"' in node
    assert "0x18000" in node and "0x30000" in node
    assert '"seninf-irq"' in node and '"tsrec-irq"' in node
    assert "MT6878_POWER_DOMAIN_CAM_MAIN" in node
    assert "MT6878_POWER_DOMAIN_CSI_RX" in node
    assert 'mtk-csi-phy-ver = "mtk-csi-phy-3-1"' in node
    assert "iommus" not in node
    vendor = show(args.modules_repo, MODULES,
                  "mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-drv.c")
    assert 'IORESOURCE_MEM, "base"' in vendor
    assert 'IORESOURCE_MEM, "ana-rx"' in vendor
    assert '"dvfsrc-vcore"' in vendor and 'nvmem_cell_get(ctx->dev, "rg_csi")' in vendor
    assert "dev_pm_domain_attach_by_id" in vendor
    # Forbidden activation paths must stay absent, not just guarded by a bool.
    for forbidden in (r"\bwritel\w*\s*\(", r"\breadl\w*\s*\(",
                      r"\bclk_prepare_enable\s*\(", r"\bregulator_set_voltage\s*\(",
                      r"\bregulator_enable\s*\(", r"\bdevm_request.*irq\s*\(",
                      r"\bpm_runtime_(?:get|resume_and_get)\w*\s*\(",
                      r"\bdma_alloc\w*\s*\(", r"\bnvmem_cell_read\s*\(" ):
        assert not re.search(forbidden, code), forbidden
    assert "dev_pm_domain_detach(data, false)" in code
    assert "device_property_present(dev, \"required-opps\")" in code
    assert "return enable ? -EOPNOTSUPP : 0" in code
    validate = code.split("static int mt6878_seninf_link_validate(", 1)[1].split("static int mt6878_seninf_bound", 1)[0]
    assert "v4l2_subdev_link_validate(" not in validate
    assert validate.index("mt6878_seninf_check_sensor") < validate.index("v4l2_subdev_lock_and_get_active_state")
    with tempfile.TemporaryDirectory(prefix="seninf-apply-") as tmp:
        tmp = Path(tmp)
        base = "drivers/media/platform/mediatek/"
        (tmp / base).mkdir(parents=True)
        for name in ("Kconfig", "Makefile"):
            shutil.copyfile(args.kernel_tree / base / name, tmp / base / name)
        subprocess.run(["patch", "--batch", "-p1", "-i", str(OUTPUT)],
                       cwd=tmp, check=True)
        for path, text in new_files().items():
            assert (tmp / path).read_text() == text
    print("PASS: pinned MT6878 ISP7SP/PHY3.1 resources, 12 named clocks and domains")
    print("PASS: no MMIO access/power/clock/IRQ/DMA activation, graph lock boundary")
    print("PASS: patch application; native/kernel builds remain CI-only")


if __name__ == "__main__":
    main()
