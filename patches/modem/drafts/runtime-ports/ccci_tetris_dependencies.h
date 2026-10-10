/* SPDX-License-Identifier: GPL-2.0-only */
/* Private to md_sys1_platform.c; no firmware, MMIO or power operations. */
#include <linux/device.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/unaligned.h>
#include "ccci_hif.h"
#include "ccci_hif_internal.h"

static int tetris_ccci_descriptor(struct device_node *node)
{
	const u8 *raw;
	int length;
	u64 base;
	u32 used;

	raw = of_get_property(node, "ccci,modem_info_v2", &length);
	if (!raw)
		return -ENODATA;
	if (length != 32)
		return -EBADMSG;
	/* This vendor ABI is raw little-endian bytes, NOT FDT cells. */
	base = get_unaligned_le64(raw);
	used = get_unaligned_le32(raw + 8);
	/* The frozen producer allocates at 4096 alignment, independently of PAGE_SIZE. */
	if (!base || (base & 4095) || used < 21 * 76 || used > SZ_64K ||
	    base > U64_MAX - SZ_64K || get_unaligned_le32(raw + 12) ||
	    get_unaligned_le32(raw + 16) != 2 ||
	    get_unaligned_le32(raw + 20) != 21 ||
	    get_unaligned_le32(raw + 24) || get_unaligned_le32(raw + 28))
		return -EBADMSG;
	/* Shape validation only: does not map tags or authenticate firmware. */
	return 0;
}

static int tetris_ccci_supplier(const char *compatible,
				struct platform_device **supplier)
{
	struct device_node *node, *selected = NULL;
	struct platform_device *pdev;

	for_each_compatible_node(node, NULL, compatible) {
		if (!of_device_is_available(node))
			continue;
		if (selected) {
			of_node_put(selected);
			of_node_put(node);
			return -EINVAL;
		}
		selected = of_node_get(node);
	}
	if (!selected)
		return -ENODEV;
	pdev = of_find_device_by_node(selected);
	of_node_put(selected);
	if (!pdev)
		return -EPROBE_DEFER;
	*supplier = pdev;
	return 0;
}

static int tetris_ccci_dependencies(struct platform_device *consumer)
{
	static const char * const compatibles[] = {
		"mediatek,ccci_ccif", "mediatek,dpmaif",
	};
	static const unsigned int ids[] = { CCIF_HIF_ID, DPMAIF_HIF_ID };
	struct platform_device *suppliers[2] = { NULL, NULL };
	struct device_link *link;
	unsigned int i;
	int ret;

	ret = tetris_ccci_descriptor(consumer->dev.of_node);
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(suppliers); i++) {
		ret = tetris_ccci_supplier(compatibles[i], &suppliers[i]);
		if (ret)
			goto out;
		/* Managed links order probing/unbind, without runtime-PM power-on. */
		link = device_link_add(&consumer->dev, &suppliers[i]->dev,
					  DL_FLAG_AUTOREMOVE_CONSUMER);
		if (!link) {
			ret = -ENOMEM;
			goto out;
		}
		if (!device_is_bound(&suppliers[i]->dev) ||
		    !READ_ONCE(ccci_hif[ids[i]]) ||
		    !READ_ONCE(ccci_hif_op[ids[i]])) {
			ret = -EPROBE_DEFER;
			goto out;
		}
	}
out:
	/* Driver core drops AUTOREMOVE_CONSUMER links on failed probe/unbind.
	 * add may return an existing link: never delete an unowned shared link.
	 */
	for (i = ARRAY_SIZE(suppliers); i; i--) {
		if (suppliers[i - 1])
			put_device(&suppliers[i - 1]->dev);
	}
	return ret;
}
