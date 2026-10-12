/* SPDX-License-Identifier: GPL-2.0-only */
#include "tetris_hif_resources.h"
#include "ccci_hif_internal.h"

static int tetris_resource_dependencies(struct platform_device *consumer)
{
	static const char *const compatibles[] = { "mediatek,ccci_ccif", "mediatek,dpmaif" };
	static const unsigned int ids[] = { CCIF_HIF_ID, DPMAIF_HIF_ID };
	struct platform_device *supplier;
	struct device_node *node;
	struct device_link *link;
	unsigned int i;
	int ret;

	ret = tetris_passive_node(consumer->dev.of_node);
	if (ret)
		return ret;
	/* This profile must not coexist with any published hardware HIF object. */
	for (i = 0; i < ARRAY_SIZE(ids); i++) {
		if (READ_ONCE(ccci_hif[ids[i]]) || READ_ONCE(ccci_hif_op[ids[i]]))
			return -EBUSY;
	}
	for (i = 0; i < ARRAY_SIZE(ids); i++) {
		ret = tetris_unique_node(compatibles[i], &node);
		if (ret)
			return ret;
		supplier = of_find_device_by_node(node);
		of_node_put(node);
		if (!supplier)
			return -EPROBE_DEFER;
		link = device_link_add(&consumer->dev, &supplier->dev, DL_FLAG_AUTOREMOVE_CONSUMER);
		ret = link ? tetris_hif_acquire(&consumer->dev, supplier, ids[i]) : -ENOMEM;
		put_device(&supplier->dev);
		if (ret)
			return ret;
	}
	/* Driver core unwinds leases/devres and managed links on probe failure. */
	return 0;
}
