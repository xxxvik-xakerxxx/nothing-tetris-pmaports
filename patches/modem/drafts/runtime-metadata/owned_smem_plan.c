/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/of.h>
#include <linux/string.h>
#include "ccci_util_lib_main.h"
#include "tetris_runtime_smem/smem.h"
#include "smem_boot_evidence/boot_evidence.h"

/* Sole serialized util init/exit lifetime; no runtime consumer or mappings. */
static struct {
	struct ccci_mem_layout layout;
	struct ccci_smem_region nc[26], cache[11];
	struct tetris_smem_boot_evidence boot_evidence;
	bool has_boot_evidence;
	bool ready;
} tetris_owned_smem_plan;

static int collect_boot_evidence(const struct tetris_metadata_banks *banks)
{
	struct device_node *node;
	struct tetris_smem_boot_evidence evidence;
	const struct ccci_mem_region *regions[2] = {
		&tetris_owned_smem_plan.layout.md_bank4_noncacheable_total,
		&tetris_owned_smem_plan.layout.md_bank4_cacheable_total,
	};
	unsigned char wire[TETRIS_SMEM_BOOT_BYTES];
	unsigned int i;
	int length = 0, ret = 0;

	/* The producer uses this sole disabled anchor; importer checked uniqueness.
	 * Absence supports older loaders. A present malformed record is fatal.
	 */
	node = of_find_node_by_path("/modem");
	if (!node)
		return -ENODEV;
	if (!of_device_is_compatible(node, "mediatek,mddriver")) {
		ret = -EINVAL;
		goto put;
	}
	if (!of_find_property(node, TETRIS_SMEM_BOOT_PROPERTY, &length))
		goto put;
	if (length != (int)sizeof(wire)) {
		ret = -EMSGSIZE;
		goto put;
	}
	ret = of_property_read_u8_array(node, TETRIS_SMEM_BOOT_PROPERTY, wire, sizeof(wire));
put:
	of_node_put(node);
	if (ret || !length)
		return ret;
	ret = tetris_smem_boot_decode(wire, sizeof(wire), banks, sizeof(*banks),
			&evidence, sizeof(evidence));
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(regions); i++) {
		if (regions[i]->base_ap_view_phy != evidence.record[i].range_start ||
		    !regions[i]->size || regions[i]->size > evidence.record[i].range_size ||
		    regions[i]->base_ap_view_vir)
			return -ERANGE;
	}
	/* Historical BL33 readbacks only, never Linux NS admission or a mapping. */
	tetris_owned_smem_plan.boot_evidence = evidence;
	tetris_owned_smem_plan.has_boot_evidence = true;
	return 0;
}

void mtk_ccci_owned_smem_cleanup(void)
{
	memset(&tetris_owned_smem_plan, 0, sizeof(tetris_owned_smem_plan));
}

int mtk_ccci_owned_smem_init(void)
{
	struct tetris_metadata_banks banks;
	struct tetris_smem_owner *owner = NULL;
	int ret, release;

	if (tetris_owned_smem_plan.ready)
		return -EALREADY;
	ret = mtk_ccci_owned_banks_copy(&banks);
	if (ret)
		return ret;
	ret = tetris_smem_from_arguments(&banks, &owner);
	if (ret)
		return ret;
	ret = tetris_smem_preview(owner, &tetris_owned_smem_plan.layout,
			tetris_owned_smem_plan.nc, ARRAY_SIZE(tetris_owned_smem_plan.nc),
			tetris_owned_smem_plan.cache, ARRAY_SIZE(tetris_owned_smem_plan.cache));
	release = tetris_smem_destroy(owner);
	if (!ret)
		ret = release;
	if (!ret)
		ret = collect_boot_evidence(&banks);
	if (ret) {
		mtk_ccci_owned_smem_cleanup();
		return ret;
	}
	tetris_owned_smem_plan.ready = true;
	if (tetris_owned_smem_plan.has_boot_evidence)
		pr_info("Tetris CCCI: SMEM boot evidence retained; Linux NS admission not established\n");
	pr_info("Tetris CCCI: owned SMEM plan ready; NC=%u cache=%u; memory access disabled\n",
		tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.size,
		tetris_owned_smem_plan.layout.md_bank4_cacheable_total.size);
	return 0;
}
