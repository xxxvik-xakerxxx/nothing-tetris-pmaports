/* SPDX-License-Identifier: GPL-2.0-only */
#include "tetris_hif_resources.h"

static int tetris_hif_supplier_probe(struct platform_device *pdev, unsigned int id,
		const char *const *names, unsigned int nclk, unsigned int nirq)
{
	struct tetris_hif_resources *res;
	struct resource *mem;
	unsigned int i, j;
	int ret;

	ret = tetris_passive_node(pdev->dev.of_node);
	if (ret)
		return ret;
	if (pdev->dev.pm_domain || platform_get_drvdata(pdev))
		return -EOPNOTSUPP;
	res = devm_kzalloc(&pdev->dev, sizeof(*res), GFP_KERNEL);
	if (!res)
		return -ENOMEM;
	res->pdev = pdev;
	res->owner = THIS_MODULE;
	res->hif_id = id;
	res->nmem = id == CCIF_HIF_ID ? 2 : 4;
	res->nclk = nclk;
	res->nirq = nirq;
	if (nclk > ARRAY_SIZE(res->clk) || !nirq || nirq > ARRAY_SIZE(res->irq))
		return -EINVAL;
	for (i = 0; i < res->nmem; i++) {
		mem = platform_get_resource(pdev, IORESOURCE_MEM, i);
		ret = tetris_resource_range(mem);
		if (ret)
			return ret;
		/* Reject aliasing windows before acquiring a conflicting claim. */
		for (j = 0; j < i; j++) {
			if (mem->start <= res->mem[j].end && res->mem[j].start <= mem->end)
				return -EINVAL;
		}
		res->mem[i] = *mem;
		ret = tetris_resource_claim(&pdev->dev, mem, &res->claim[i]);
		if (ret)
			return ret;
	}
	for (i = 0; i < nirq; i++) {
		ret = tetris_irq_descriptor(&pdev->dev, i, &res->irq[i]);
		if (ret)
			return ret;
		for (j = 0; j < i; j++) {
			if (tetris_same_irq(&res->irq[i], &res->irq[j]))
				return -EINVAL;
		}
	}
	for (i = 0; i < nclk; i++) {
		res->clk[i] = devm_clk_get(&pdev->dev, names[i]);
		if (IS_ERR(res->clk[i]))
			return PTR_ERR(res->clk[i]);
	}
	/* B4.1's pericfg reset is only for <=6297; the consumer admits 6299.
	 * Do not demand a provider absent from the real MT6878 board description.
	 * A supplied relationship is still validated, never silently discarded.
	 */
	if (id != CCIF_HIF_ID ||
	    of_find_property(pdev->dev.of_node, "ccif-pericfg", NULL)) {
		ret = tetris_relation(&pdev->dev, id == CCIF_HIF_ID ?
			"ccif-pericfg" : "dpmaif-infracfg", NULL, false);
		if (ret)
			return ret;
	}
	/* The B4.1 reset implementation finds this compatible globally. Requiring
	 * exactly one retains that relationship without its of_iomap side effect. */
	ret = tetris_relation(&pdev->dev, NULL, "mediatek,infracfg", false);
	if (ret)
		return ret;
	if (id == CCIF_HIF_ID) {
		ret = tetris_relation(&pdev->dev, NULL, "mediatek,md_ccif4", true);
		if (ret)
			return ret;
		ret = tetris_relation(&pdev->dev, NULL, "mediatek,md_ccif5", true);
		if (ret)
			return ret;
	}
	/* Publish only the completed device-owned resource record, never a HIF slot. */
	platform_set_drvdata(pdev, res);
	return 0;
}

static void tetris_hif_supplier_remove(struct platform_device *pdev)
{
	platform_set_drvdata(pdev, NULL);
	/* Driver core releases claims/clocks/node refs and allocations via devres.
	 * Parsed IRQ descriptors own node refs only, not domain mappings. */
}
