/* SPDX-License-Identifier: GPL-2.0-only */
/* Private extension of the real mtk-smi provider, after its larb structure. */
#include <linux/property.h>
#include <soc/mediatek/camisp-dma.h>

static struct platform_driver mtk_smi_larb_driver;

static int camisp_id(struct device *dev, const char *compatible, const char *property)
{
	u32 id;

	if (!of_device_is_compatible(dev->of_node, compatible) ||
	    device_property_read_u32(dev, property, &id))
		return -1;
	return id <= (u32)INT_MAX ? (int)id : -1;
}

static int camisp_larb_id(struct device *dev)
{
	int id = camisp_id(dev, "mediatek,mt6878-smi-larb", "mediatek,larb-id");

	return id == 13 || id == 14 ? id : -1;
}

static int camisp_common_id(struct device *dev)
{
	int id = camisp_id(dev, "mediatek,mt6878-smi-common", "mediatek,common-id");

	return id == 16 || id == 19 || id == 31 ? id : -1;
}

static bool camisp_display_root(struct device_node *node)
{
	const char *name;
	u32 id;

	if (!node || !of_device_is_compatible(node, "mediatek,mt6878-smi-common") ||
	    of_node_check_flag(node, OF_DYNAMIC) ||
	    of_find_property(node, "mediatek,smi", NULL) ||
	    of_find_property(node, "mediatek,smi-supply", NULL) ||
	    of_property_count_strings(node, "clock-names") != 2 ||
	    of_property_read_string_index(node, "clock-names", 0, &name) || strcmp(name, "apb") ||
	    of_property_read_string_index(node, "clock-names", 1, &name) || strcmp(name, "smi"))
		return false;
	/* Packaged 0071 root has no common-id; a present value must parse as zero. */
	if (!of_find_property(node, "mediatek,common-id", NULL))
		return true;
	return !of_property_read_u32(node, "mediatek,common-id", &id) && !id;
}

static int camisp_scope(struct device *dev, bool larb)
{
	const char *compatible = larb ? "mediatek,mt6878-smi-larb" : "mediatek,mt6878-smi-common";
	const char *property = larb ? "mediatek,larb-id" : "mediatek,common-id";
	u32 id;
	int ret;

	if (!of_device_is_compatible(dev->of_node, compatible))
		return 0;
	ret = device_property_read_u32(dev, property, &id);
	/* Packaged common0 has no common-id. Its explicit root/two-clock shape
	 * must not become a fallback for missing camera IDs or camera parents.
	 */
	if (!larb && !device_property_present(dev, property))
		id = 0;
	else if (ret)
		return -EINVAL;
	if (!id) {
		if (larb) {
			struct device_node *parent = of_parse_phandle(dev->of_node, "mediatek,smi", 0);
			bool display = camisp_display_root(parent);

			of_node_put(parent);
			return display ? 0 : -EINVAL;
		}
		return camisp_display_root(dev->of_node) ? 0 : -EINVAL;
	}
	if (of_node_check_flag(dev->of_node, OF_DYNAMIC))
		return -EOPNOTSUPP;
	return (larb ? id == 13 || id == 14 : id == 16 || id == 19 || id == 31) ?
		1 : -EOPNOTSUPP;
}

static int camisp_resource_check(struct platform_device *pdev,
	const char * const *names, unsigned int count)
{
	struct device *dev = &pdev->dev;
	struct resource *res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	const char *name;
	unsigned int i;

	if (!res || resource_size(res) != 0x1000 ||
	    platform_get_resource(pdev, IORESOURCE_MEM, 1) || !dev->pm_domain ||
	    of_count_phandle_with_args(dev->of_node, "power-domains", "#power-domain-cells") != 1 ||
	    of_count_phandle_with_args(dev->of_node, "clocks", "#clock-cells") != (int)count ||
	    device_property_string_array_count(dev, "clock-names") != (int)count)
		return -EINVAL;
	for (i = 0; i < count; i++) {
		if (of_property_read_string_index(dev->of_node, "clock-names", i, &name) ||
		    strcmp(name, names[i]))
			return -EINVAL;
	}
	/* This scope owns no sensor regulator, reset or boot-state override. */
	if (of_find_property(dev->of_node, "resets", NULL) ||
	    device_property_read_bool(dev, "skip-rpm-cb") ||
	    device_property_read_bool(dev, "skip-restore") ||
	    device_property_read_bool(dev, "skip-busy-check") ||
	    device_property_read_bool(dev, "init-power-on"))
		return -EOPNOTSUPP;
	return 0;
}

static int camisp_parent_check(struct device *dev, u32 expected)
{
	struct device_node *parent;
	u32 id;
	int ret;

	if (of_count_phandle_with_args(dev->of_node, "mediatek,smi", NULL) != 1)
		return -EINVAL;
	parent = of_parse_phandle(dev->of_node, "mediatek,smi", 0);
	if (!parent)
		return -EINVAL;
	if (!expected)
		ret = of_device_is_available(parent) && camisp_display_root(parent) ? 0 : -EINVAL;
	else
		ret = of_device_is_available(parent) &&
			!of_node_check_flag(parent, OF_DYNAMIC) &&
			of_device_is_compatible(parent, "mediatek,mt6878-smi-common") &&
			!of_property_read_u32(parent, "mediatek,common-id", &id) &&
			id == expected ? 0 : -EINVAL;
	of_node_put(parent);
	return ret;
}

static int camisp_larb_prepare(struct platform_device *pdev, struct mtk_smi_larb *larb)
{
	static const char * const names[] = { "apb" };
	int id = camisp_larb_id(&pdev->dev), ret;

	ret = camisp_scope(&pdev->dev, true);
	if (ret <= 0)
		return ret;
	ret = camisp_resource_check(pdev, names, ARRAY_SIZE(names));
	if (!ret)
		ret = camisp_parent_check(&pdev->dev, id == 13 ? 16 : 19);
	if (ret)
		return ret;
	larb->smi.clks[0].id = names[0];
	ret = devm_clk_bulk_get(&pdev->dev, 1, larb->smi.clks);
	if (ret)
		return ret;
	larb->smi.clk_num = 1;
	larb->larbid = id;
	return 1;
}

static int camisp_larb_link_common(struct device *dev, struct device **result)
{
	struct device_node *parent = of_parse_phandle(dev->of_node, "mediatek,smi", 0);
	struct platform_device *supplier;
	int ret;

	if (!parent)
		return -EINVAL;
	supplier = of_find_device_by_node(parent);
	of_node_put(parent);
	if (!supplier)
		return -EPROBE_DEFER;
	ret = device_is_bound(&supplier->dev) && pm_runtime_enabled(&supplier->dev) ?
		0 : -EPROBE_DEFER;
	if (!ret && !device_link_add(dev, &supplier->dev,
		DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER))
		ret = -ENOMEM;
	if (ret)
		put_device(&supplier->dev);
	else
		*result = &supplier->dev;
	return ret;
}

static int camisp_common_prepare(struct platform_device *pdev, struct mtk_smi *common)
{
	static const char * const names[] = {
		"apb", "smi", "gals0", "gals1", "gals2", "gals3", "gals4"
	};
	int id = camisp_common_id(&pdev->dev), ret;
	unsigned int i, count = id == 31 ? 1 : ARRAY_SIZE(names);

	ret = camisp_scope(&pdev->dev, false);
	if (ret <= 0)
		return ret;
	ret = camisp_resource_check(pdev, names, count);
	if (ret)
		return ret;
	if (id == 31) {
		struct device_node *parent, *legacy;

		/* Existing reset owner links smi-supply; IOMMU discovery walks smi. */
		ret = camisp_parent_check(&pdev->dev, 0);
		if (ret)
			return ret;
		parent = of_parse_phandle(pdev->dev.of_node, "mediatek,smi", 0);
		legacy = of_parse_phandle(pdev->dev.of_node, "mediatek,smi-supply", 0);
		ret = parent == legacy ? 0 : -EINVAL;
		of_node_put(legacy);
		of_node_put(parent);
		if (ret)
			return ret;
	} else {
		struct device_node *parent;
		struct platform_device *supplier;

		ret = camisp_parent_check(&pdev->dev, 31);
		if (ret)
			return ret;
		parent = of_parse_phandle(pdev->dev.of_node, "mediatek,smi", 0);
		supplier = of_find_device_by_node(parent);
		of_node_put(parent);
		if (!supplier)
			return -EPROBE_DEFER;
		ret = device_is_bound(&supplier->dev) && pm_runtime_enabled(&supplier->dev) ?
			0 : -EPROBE_DEFER;
		if (!ret && !device_link_add(&pdev->dev, &supplier->dev,
			DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER))
			ret = -ENOMEM;
		put_device(&supplier->dev);
		if (ret)
			return ret;
	}
	for (i = 0; i < count; i++)
		common->clks[i].id = names[i];
	ret = devm_clk_bulk_get(&pdev->dev, count, common->clks);
	if (ret)
		return ret;
	common->clk_num = count;
	return 1;
}

/* B4.1 ee2be53: explicit larb13/14 bandwidth and nonzero misc entries.
 * Zero-filled C-array padding is not a register description.
 */
static const u8 camisp_larb13_bwl[] = { 0xc, 0x34, 0x20, 0x10, 0x1 };
static const u8 camisp_larb14_bwl[] = { 0xc, 0x34, 0x20, 0x1 };

static int camisp_translation_check(struct mtk_smi_larb *larb)
{
	unsigned int i;

	if (!larb->mmu || !larb->bank)
		return -ENODEV;
	/* Only CQI/WDMA ports 0/1 in NORMAL_DOM, bank0; no foreign owner. */
	if (READ_ONCE(*larb->mmu) != (BIT(0) | BIT(1)))
		return -EBUSY;
	for (i = 0; i < 2; i++)
		if (READ_ONCE(larb->bank[i]))
			return -EOPNOTSUPP;
	return 0;
}

static int camisp_larb_resume(struct mtk_smi_larb *larb)
{
	int id = camisp_larb_id(larb->smi.dev), ret;
	const u8 *bwl = id == 13 ? camisp_larb13_bwl : camisp_larb14_bwl;
	unsigned int count = id == 13 ? ARRAY_SIZE(camisp_larb13_bwl) : ARRAY_SIZE(camisp_larb14_bwl);
	u32 value;
	unsigned int i;

	ret = camisp_translation_check(larb);
	if (ret)
		return ret;
	for (i = 0; i < 2; i++) {
		value = readl(larb->base + SMI_LARB_NONSEC_CON(i));
		/* Do not inherit a SYSRAM route or a nonzero bank from vendor boot. */
		if (value & (GENMASK(19, 16) | BANK_SEL(3)))
			return -ESTALE;
	}
	for (i = 0; i < 2; i++) {
		value = readl(larb->base + SMI_LARB_NONSEC_CON(i));
		writel(value | F_MMU_EN, larb->base + SMI_LARB_NONSEC_CON(i));
	}
	for (i = 0; i < count; i++)
		writel(bwl[i], larb->base + SMI_LARB_OSTDL_PORTx(i));
	writel(0x370256, larb->base + SMI_LARB_CMD_THRT_CON);
	writel(1, larb->base + SMI_LARB_SW_FLAG);
	wmb();
	return 0;
}

static int camisp_larb_idle(struct mtk_smi_larb *larb)
{
	/* ee2 mtk_smi_larb_suspend tests both external/internal status banks. */
	return readl(larb->base) || readl(larb->base + 0x500) ? -EBUSY : 0;
}

int mt6878_camisp_dma_idle(struct device *dev)
{
	struct mtk_smi_larb *larb;
	int ret;

	if (!dev)
		return -EINVAL;
	/* Exclude remove only across these synchronous reads. Long-lived DMA
	 * teardown still requires the parent's cooperative supplier exclusion.
	 */
	if (!device_trylock(dev))
		return -EBUSY;
	if (dev->driver != &mtk_smi_larb_driver.driver ||
	    !device_is_bound(dev) || !pm_runtime_active(dev) || camisp_larb_id(dev) < 0)
		ret = -ENODEV;
	else {
		larb = dev_get_drvdata(dev);
		ret = !larb || IS_ERR_OR_NULL(larb->base) ? -EHOSTDOWN : camisp_larb_idle(larb);
	}
	device_unlock(dev);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_camisp_dma_idle);

static void camisp_common_resume(struct mtk_smi *common)
{
	int id = camisp_common_id(common->dev);
	unsigned int i;

	/* ee2 common16/19/31: eight explicit zero bandwidth entries, three misc. */
	for (i = 0; i < 8; i++)
		writel(0, common->base + 0x104 + i * 4);
	writel(0xa, common->base + 0x100);
	writel(id == 19 ? 0x2105 : 0x2146, common->base + 0x244);
	writel(1, common->base + 0x444);
	wmb();
}

static int camisp_system_suspend(struct device *dev)
{
	/* Force-suspend must not cut power to a held capture/DMA supplier. */
	if ((camisp_larb_id(dev) >= 0 || camisp_common_id(dev) >= 0) &&
	    atomic_read(&dev->power.usage_count))
		return -EBUSY;
	return pm_runtime_force_suspend(dev);
}

#if IS_ENABLED(CONFIG_KUNIT)
#include "camisp-smi-test.inc"
#endif
