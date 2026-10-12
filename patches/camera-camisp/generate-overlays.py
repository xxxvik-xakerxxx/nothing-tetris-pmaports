#!/usr/bin/env python3
"""Generate isolated camera supplier overlays from the pinned Linux sources."""
import argparse
import difflib
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMIT = "d84b264a54a37611f2f46bc19363cb9b41606205"
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"


def replace(code, old, new):
    if code.count(old) != 1:
        raise ValueError("absent/ambiguous source context: " + old)
    return code.replace(old, new, 1)


def diff(name, old, new):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                      fromfile="a/" + name, tofile="b/" + name))


def provider_overlays(smi, iommu):
    original = smi
    smi = replace(smi, "clks[MTK_SMI_CLK_NR_MAX];", "clks[7]; /* B4.1 camera subcommon clock list. */")
    smi = replace(smi, "static int\nmtk_smi_larb_bind(",
                  '#include "mt6878-camisp-smi.inc"\n\nstatic int\nmtk_smi_larb_bind(')
    smi = replace(smi, "\t\tif (dev == larb_mmu[i].dev) {\n",
                  "\t\tif (dev == larb_mmu[i].dev) {\n"
                  "\t\t\tif (camisp_larb_id(dev) >= 0 && (unsigned int)camisp_larb_id(dev) != i)\n"
                  "\t\t\t\treturn -EINVAL;\n")
    smi = replace(smi,
        "\tret = mtk_smi_dts_clk_init(dev, &larb->smi, mtk_smi_larb_clks,\n"
        "\t\t\t\t   MTK_SMI_LARB_REQ_CLK_NR, MTK_SMI_LARB_OPT_CLK_NR);",
        "\tret = camisp_larb_prepare(pdev, larb);\n\tif (!ret)\n"
        "\t\tret = mtk_smi_dts_clk_init(dev, &larb->smi, mtk_smi_larb_clks,\n"
        "\t\t\t\t   MTK_SMI_LARB_REQ_CLK_NR, MTK_SMI_LARB_OPT_CLK_NR);\n"
        "\telse if (ret > 0)\n\t\tret = 0;")
    smi = replace(smi, "\tret = mtk_smi_device_link_common(dev, &larb->smi_common_dev);",
                  "\tif (camisp_larb_id(dev) >= 0)\n"
                  "\t\tret = camisp_larb_link_common(dev, &larb->smi_common_dev);\n"
                  "\telse\n\t\tret = mtk_smi_device_link_common(dev, &larb->smi_common_dev);")
    smi = replace(smi, "\tdevice_link_remove(dev, larb->smi_common_dev);\n\treturn ret;",
                  "\tif (camisp_larb_id(dev) >= 0)\n\t\tput_device(larb->smi_common_dev);\n"
                  "\telse\n\t\tdevice_link_remove(dev, larb->smi_common_dev);\n\treturn ret;")
    smi = replace(smi, "\tdevice_link_remove(&pdev->dev, larb->smi_common_dev);",
                  "\tif (camisp_larb_id(&pdev->dev) < 0)\n"
                  "\t\tdevice_link_remove(&pdev->dev, larb->smi_common_dev);")
    smi = replace(smi, "\tcomponent_del(&pdev->dev, &mtk_smi_larb_component_ops);\n}",
                  "\tcomponent_del(&pdev->dev, &mtk_smi_larb_component_ops);\n"
                  "\tif (camisp_larb_id(&pdev->dev) >= 0)\n\t\tput_device(larb->smi_common_dev);\n}")
    smi = replace(smi, "\t/* Configure the basic setting for this larb */\n\treturn larb_gen->config_port(dev);",
                  "\tif (camisp_larb_id(dev) >= 0) {\n"
                  "\t\tret = camisp_larb_resume(larb);\n"
                  "\t\tif (ret)\n\t\t\tclk_bulk_disable_unprepare(larb->smi.clk_num, larb->smi.clks);\n"
                  "\t\treturn ret;\n\t}\n"
                  "\t/* Configure the basic setting for this larb */\n\treturn larb_gen->config_port(dev);")
    anchor = "\tif (MTK_SMI_CAPS(larb->larb_gen->flags_general, MTK_SMI_FLAG_SLEEP_CTL)) {"
    smi = replace(smi, anchor,
                  "\tif (camisp_larb_id(dev) >= 0) {\n"
                  "\t\tret = camisp_larb_idle(larb);\n\t\tif (ret)\n\t\t\treturn ret;\n\t}\n\n" + anchor)
    anchor = "\tret = mtk_smi_dts_clk_init(dev, common, mtk_smi_common_clks, clk_required, 0);"
    smi = replace(smi, anchor,
                  "\tret = camisp_common_prepare(pdev, common);\n\tif (!ret)\n\t" + anchor +
                  "\n\telse if (ret > 0)\n\t\tret = 0;")
    anchor = "\tif (common->plat->type != MTK_SMI_GEN2)\n\t\treturn 0;"
    smi = replace(smi, anchor,
                  "\tif (camisp_common_id(dev) >= 0) {\n"
                  "\t\tcamisp_common_resume(common);\n\t\treturn 0;\n\t}\n\n" + anchor)
    # Both real SMI PM tables use this pair; keep all non-camera behavior.
    if smi.count("SET_LATE_SYSTEM_SLEEP_PM_OPS(pm_runtime_force_suspend,") != 2:
        raise ValueError("unexpected SMI sleep tables")
    smi = smi.replace("SET_LATE_SYSTEM_SLEEP_PM_OPS(pm_runtime_force_suspend,",
                      "SET_LATE_SYSTEM_SLEEP_PM_OPS(camisp_system_suspend,")

    old_iommu = iommu
    anchor = "static int mtk_iommu_mm_dts_parse("
    iommu = replace(iommu, anchor, '#include "mt6878-camisp-iommu.inc"\n\n' + anchor)
    start = iommu.index("\t\t/* Get smi-(sub)-common dev from the last larb. */")
    end = iommu.index("\n\t\t/*\n\t\t * All the larbs", start)
    old = iommu[start:end]
    iommu = iommu[:start] + """\t\tif (data->plat_data->m4u_plat == M4U_MT6878) {
\t\t\tsmicomm_node = camisp_iommu_root(plarbdev->dev.of_node);
\t\t\tif (IS_ERR(smicomm_node)) {
\t\t\t\tret = PTR_ERR(smicomm_node);
\t\t\t\tgoto err_larbdev_put;
\t\t\t}
\t\t} else {
""" + "".join(("\t" + line if line else "") + "\n" for line in old.splitlines()) + "\t\t}\n" + iommu[end:]
    return diff("drivers/memory/mtk-smi.c", original, smi) + diff(
        "drivers/iommu/mtk_iommu.c", old_iommu, iommu)


def prepared_sources(kernel):
    with tempfile.TemporaryDirectory(prefix="camisp-provider-base-") as name:
        tree = Path(name)
        for file in ("drivers/memory/mtk-smi.c", "drivers/iommu/mtk_iommu.c"):
            target = tree / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((kernel / file).read_bytes())
        for patch in (PACKAGE / "0070-iommu-mediatek-add-MT6878-display-DMA-data.patch",
                      ROOT / "patches/camera-smi-owner/provider.patch"):
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)],
                                    cwd=tree, capture_output=True, text=True)
            if result.returncode:
                raise ValueError(result.stdout + result.stderr)
        return tuple((tree / file).read_text() for file in
                     ("drivers/memory/mtk-smi.c", "drivers/iommu/mtk_iommu.c"))


def overlays(kernel):
    provider = provider_overlays(*prepared_sources(kernel))
    source = ROOT / "patches/camera-camsv/mt6878-camsv-vb2.c"
    old = source.read_text()
    new = replace(old, "/* Managed supplier lifetime only; deliberately no runtime-PM link flag. */",
                  "/* CAMISP PM resumes the physical SMI larb/translation before CAMSV. */")
    new = replace(new, "device_link_add(dev, port_owner, DL_FLAG_AUTOREMOVE_CONSUMER)",
                  "device_link_add(dev, port_owner,\n"
                  "\t\tDL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER)")
    return {"provider.patch": provider,
            "consumer-pm.patch": diff(source.name, old, new)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-tree", type=Path, default=ROOT.parent / ("linux-" + COMMIT))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, contents in overlays(args.kernel_tree).items():
        path = HERE / name
        if args.check:
            if path.read_text() != contents:
                raise ValueError("overlay drift: " + name)
        else:
            path.write_text(contents)


if __name__ == "__main__":
    main()
