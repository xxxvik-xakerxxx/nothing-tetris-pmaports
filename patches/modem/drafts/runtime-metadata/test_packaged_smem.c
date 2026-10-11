/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the actual packaged importer and pinned vendor lookup. */
static unsigned int plan_allocs, plan_fail;
void *kzalloc(size_t size, int flags)
{
	(void)flags;
	return ++plan_allocs == plan_fail ? NULL : calloc(1, size);
}
#include "owned_smem_plan.c"

static void packaged_probe(struct tetris_metadata_banks *source, int imported)
{
	struct tetris_metadata_banks copied, untouched;
	unsigned int i;

	memset(&untouched, 0xa5, sizeof(untouched));
	copied = untouched;
	assert(mtk_ccci_owned_banks_copy(NULL) == -EINVAL);
	if (imported) {
		assert(mtk_ccci_owned_banks_copy(&copied) == -ENODATA);
		assert(!memcmp(&copied, &untouched, sizeof(copied)));
		assert(mtk_ccci_owned_smem_init() == -ENODATA);
		assert(!tetris_owned_smem_plan.ready && !plan_allocs);
	} else {
		assert(!mtk_ccci_owned_banks_copy(&copied));
		assert(!memcmp(&copied, source, sizeof(copied)));
		/* Prove retained banks, like tags, do not borrow caller storage. */
		memset(source, 0xa5, sizeof(*source));
		assert(!mtk_ccci_owned_banks_copy(&untouched));
		assert(!memcmp(&copied, &untouched, sizeof(copied)));
		for (i = 1; i <= 2; i++) {
			plan_allocs = 0;
			plan_fail = i;
			assert(mtk_ccci_owned_smem_init() == -ENOMEM);
			assert(!tetris_owned_smem_plan.ready);
		}
		plan_fail = 0;
		assert(!mtk_ccci_owned_smem_init());
		assert(tetris_owned_smem_plan.ready);
		assert(mtk_ccci_owned_smem_init() == -EALREADY);
		assert(tetris_owned_smem_plan.layout.md_bank0.base_ap_view_phy == copied.firmware.base);
		assert(!tetris_owned_smem_plan.layout.md_bank0.base_ap_view_vir);
		assert(!tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.base_ap_view_vir);
		assert(!tetris_owned_smem_plan.layout.md_bank4_cacheable_total.base_ap_view_vir);
		assert(tetris_owned_smem_plan.layout.md_bank4_noncacheable == tetris_owned_smem_plan.nc);
		assert(tetris_owned_smem_plan.layout.md_bank4_cacheable == tetris_owned_smem_plan.cache);
		for (i = 0; i < ARRAY_SIZE(tetris_owned_smem_plan.nc); i++)
			assert(!tetris_owned_smem_plan.nc[i].base_ap_view_vir);
		for (i = 0; i < ARRAY_SIZE(tetris_owned_smem_plan.cache); i++)
			assert(!tetris_owned_smem_plan.cache[i].base_ap_view_vir);
	}
	mtk_ccci_owned_smem_cleanup();
	mtk_ccci_owned_args_cleanup();
	assert(!tetris_owned_smem_plan.ready && !tetris_owned_tags && !s_init_done);
	copied = untouched;
	assert(mtk_ccci_owned_banks_copy(&copied) == -ENODATA);
	assert(!memcmp(&copied, &untouched, sizeof(copied)));
	assert(mtk_ccci_owned_smem_init() == -ENODATA);
	mtk_ccci_owned_smem_cleanup();
	mtk_ccci_owned_args_cleanup();
}
