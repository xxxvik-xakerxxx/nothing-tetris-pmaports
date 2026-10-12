#!/usr/bin/env python3
"""Check actual supplier source and isolated overlays; never compile or activate."""
import argparse
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def function(source, name, following):
    return source.split(name + "(", 1)[1].split(following, 1)[0]


def contract(dma, smi, iommu):
    probe = function(dma, "camisp_dma_probe", "static void camisp_dma_remove")
    order = ["camisp_ports(dev", "camisp_physical_larb(iommu", "iommu_get_domain_for_dev(dev)",
             "iommu_is_dma_domain(domain)", "dma_set_mask_and_coherent(dev", "device_link_add(dev",
             "pm_runtime_enable(dev)"]
    indices = [probe.index(item) for item in order]
    assert indices == sorted(indices), "DMA attach/PM publication order"
    assert "dev->dma_parms != &pdev->dma_parms" in probe, "platform DMA parameters"
    assert "ret = dma_set_max_seg_size" not in dma, "Linux 6.18 void DMA setter"
    assert "dev->dma_parms =" not in dma, "do not replace platform-owned DMA parameters"
    assert "DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER" in probe
    for forbidden in ("iommu_domain_alloc(", "iommu_attach_device(", "ioremap", "writel(",
                      "pm_runtime_set_active(", "pm_runtime_no_callbacks("):
        assert forbidden not in dma, forbidden
    resume = function(dma, "camisp_dma_resume", "static int camisp_dma_suspend")
    assert "pm_runtime_active(dma->larb)" in resume
    assert "iommu_get_domain_for_dev(dev) != dma->domain" in resume
    suspend = function(dma, "camisp_dma_suspend", "static int camisp_dma_system_suspend")
    assert "mt6878_camisp_dma_idle(dma->larb)" in suspend
    assert "if (ret)\n\t\treturn ret;" in suspend
    translation = function(smi, "camisp_translation_check", "static int camisp_larb_resume")
    for item in ("!larb->mmu || !larb->bank", "READ_ONCE(*larb->mmu) != (BIT(0) | BIT(1))",
                 "READ_ONCE(larb->bank[i])"):
        assert item in translation, item
    restore = function(smi, "camisp_larb_resume", "static int camisp_larb_idle")
    assert restore.index("camisp_translation_check(larb)") < restore.index("readl(") < restore.index("writel(")
    assert restore.index("GENMASK(19, 16) | BANK_SEL(3)") < restore.index("writel(")
    assert "writel(0," not in restore, "implicit array padding must never write register zero"
    assert "readl(larb->base + 0x500)" in smi
    assert "atomic_read(&dev->power.usage_count)" in smi
    assert 'camisp_scope(&pdev->dev, true)' in smi and 'camisp_scope(&pdev->dev, false)' in smi
    assert 'else if (ret)\n\t\treturn -EINVAL;' in smi
    assert 'if (ret <= 0)\n\t\treturn ret;' in smi
    assert 'device_property_string_array_count(dev, "clock-names") != (int)count' in smi
    assert '"#clock-cells") != (int)count' in smi
    root = function(smi, "camisp_display_root", "static int camisp_scope")
    assert 'if (!of_find_property(node, "mediatek,common-id", NULL))\n\t\treturn true;' in root
    assert '!of_property_read_u32(node, "mediatek,common-id", &id) && !id' in root
    for item in ('"mediatek,smi"', '"mediatek,smi-supply"', 'strcmp(name, "apb")',
                 'strcmp(name, "smi")', 'of_property_count_strings(node, "clock-names") != 2'):
        assert item in root, item
    scope = function(smi, "camisp_scope", "static int camisp_resource_check")
    parent = function(smi, "camisp_parent_check", "static int camisp_larb_prepare")
    assert "camisp_display_root(dev->of_node)" in scope
    assert "if (!expected)" in parent and "camisp_display_root(parent)" in parent
    assert "OF_DYNAMIC" in smi and "OF_DYNAMIC" in iommu
    assert "count == ARRAY_SIZE(seen)" in iommu and "seen[i] == node" in iommu
    assert "of_node_put(seen[--count])" in iommu
    assert "result = of_node_get(node)" in iommu


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-tree", type=Path, help="dry-run overlays against staged research sources")
    parser.add_argument("--staged-tree", type=Path, help="inspect the overlaid production sources")
    args = parser.parse_args()
    plan = json.loads((HERE / "STAGING.json").read_text())
    dma = (HERE / "mt6878-camisp-dma.c").read_text()
    smi = (HERE / "mt6878-camisp-smi.inc").read_text()
    iommu = (HERE / "mt6878-camisp-iommu.inc").read_text()
    contract(dma, smi, iommu)
    for forbidden in ("kthread", "wait_for_completion", "camisp_pm_lease"):
        assert forbidden not in dma + smi + iommu, forbidden
    for source, destination in plan["sources"].items():
        for path in (source, destination):
            assert not Path(path).is_absolute() and ".." not in Path(path).parts
        assert (ROOT / source).is_file()
    assert len(set(plan["sources"].values())) == len(plan["sources"])
    for overlay in (plan["provider_overlay"], plan["consumer_overlay"]):
        subprocess.run(["git", "apply", "--numstat", str(ROOT / overlay)],
                       cwd=ROOT, check=True, capture_output=True)
    if args.kernel_tree:
        tree = args.kernel_tree.resolve()
        for overlay, destination in ((plan["provider_overlay"], tree),
                                     (plan["consumer_overlay"], tree / Path(plan["research_objects"][0]).parent)):
            result = subprocess.run(["patch", "--dry-run", "--batch", "--fuzz=0", "-p1"],
                                    cwd=destination, input=(ROOT / overlay).read_text(),
                                    capture_output=True, text=True)
            assert not result.returncode, result.stdout + result.stderr
    if args.staged_tree:
        tree = args.staged_tree
        for source, destination in plan["sources"].items():
            assert (tree / destination).read_bytes() == (ROOT / source).read_bytes(), destination
        physical = (tree / "drivers/memory/mtk-smi.c").read_text()
        larb_resume = function(physical, "mtk_smi_larb_resume", "static int __maybe_unused mtk_smi_larb_suspend")
        assert larb_resume.index("clk_bulk_prepare_enable(") < larb_resume.index("camisp_larb_resume(larb)")
        larb_suspend = function(physical, "mtk_smi_larb_suspend", "static const struct dev_pm_ops")
        assert larb_suspend.index("camisp_larb_idle(larb)") < larb_suspend.index("clk_bulk_disable_unprepare(")
        provider = (tree / "drivers/iommu/mtk_iommu.c").read_text()
        assert "camisp_iommu_root(plarbdev->dev.of_node)" in provider
        consumer = tree / plan["consumer_source"]
        assert "DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER" in consumer.read_text()
    print("CAMISP supplier/source/overlay guards PASS; no C compilation or hardware access")


if __name__ == "__main__":
    main()
