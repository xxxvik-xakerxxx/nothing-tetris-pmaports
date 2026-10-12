/* SPDX-License-Identifier: GPL-2.0-only */
#include "tetris_hif_resources.h"

static int tetris_modem_hw_resources(struct platform_device *pdev,
		struct ccci_dev_cfg *cfg, struct md_hw_info *hw)
{
	struct resource *mem, *claim;
	struct of_phandle_args *wdt;
	u32 generation, platform, hif;
	unsigned int i;
	int ret;

	ret = tetris_passive_node(pdev->dev.of_node);
	if (ret)
		return ret;
	if (pdev->dev.pm_domain)
		return -EOPNOTSUPP;
	ret = of_property_read_u32(pdev->dev.of_node, "mediatek,md-generation", &generation);
	if (ret)
		return ret;
	ret = of_property_read_u32(pdev->dev.of_node, "mediatek,ap-plat-info", &platform);
	if (ret)
		return ret;
	ret = of_property_read_u32(pdev->dev.of_node, "mediatek,mdhif-type", &hif);
	if (ret)
		return ret;
	if (generation != 6299 || platform != 6878 ||
	    hif != (BIT(CCIF_HIF_ID) | BIT(DPMAIF_HIF_ID)))
		return -EOPNOTSUPP;
	memset(cfg, 0, sizeof(*cfg));
	ret = of_property_read_u32(pdev->dev.of_node, "mediatek,cldma-capability", &cfg->capability);
	if (ret)
		return ret;
	mem = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	ret = tetris_resource_claim(&pdev->dev, mem, &claim);
	if (ret)
		return ret;
	/* Sequencer is optional in the pinned MT6878 DT. Never use the vendor
	 * literal fallback or synthesize a DT resource when index 1 is absent. */
	mem = platform_get_resource(pdev, IORESOURCE_MEM, 1);
	if (mem) {
		ret = tetris_resource_claim(&pdev->dev, mem, &claim);
		if (ret)
			return ret;
	}
	wdt = devm_kzalloc(&pdev->dev, sizeof(*wdt), GFP_KERNEL);
	if (!wdt)
		return -ENOMEM;
	ret = tetris_irq_descriptor(&pdev->dev, 0, wdt);
	if (ret)
		return ret;
	/* md_wdt_irq_id remains zero: no Linux IRQ mapping/request exists here. */
	for (i = 0; i < ARRAY_SIZE(clk_table); i++) {
		clk_table[i].clk_ref = devm_clk_get(&pdev->dev, clk_table[i].clk_name);
		if (IS_ERR(clk_table[i].clk_ref))
			return PTR_ERR(clk_table[i].clk_ref);
	}
	ret = tetris_relation(&pdev->dev, "ccci-infracfg", NULL, false);
	if (ret)
		return ret;
	ret = tetris_relation(&pdev->dev, "ccci-topckgen", NULL, false);
	if (ret)
		return ret;
	/* Supply the actual vendor type needed by port-table selection. The physical
	 * platform callback table stays NULL; private init only logs in pinned B4.1. */
	md_cd_plat_val_ptr.md_gen = generation;
	hw->plat_val = &md_cd_plat_val_ptr;
	ap_plat_info = platform;
	return 0;
}
