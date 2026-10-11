/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/string.h>
#include "ccci_util_lib_main.h"
#include "tetris_runtime_smem/smem.h"

/* Sole serialized util init/exit lifetime; no runtime consumer or mappings. */
static struct {
	struct ccci_mem_layout layout;
	struct ccci_smem_region nc[26], cache[11];
	bool ready;
} tetris_owned_smem_plan;

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
	if (ret) {
		mtk_ccci_owned_smem_cleanup();
		return ret;
	}
	tetris_owned_smem_plan.ready = true;
	pr_info("Tetris CCCI: owned SMEM plan ready; NC=%u cache=%u; memory access disabled\n",
		tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.size,
		tetris_owned_smem_plan.layout.md_bank4_cacheable_total.size);
	return 0;
}
