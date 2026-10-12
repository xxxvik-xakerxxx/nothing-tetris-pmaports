/* SPDX-License-Identifier: GPL-2.0-only */
/* Included in modem_sys1.c before the real register_prepare.h caller. */
#if defined(CONFIG_TETRIS_CCCI_SMEM_CONSUMER) && CONFIG_TETRIS_CCCI_SMEM_CONSUMER
#if !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)
#error "Tetris SMEM consumer requires the unpublished OWNER prepare transaction"
#endif
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/string.h>
#include "mt-plat/tetris_ccci_smem.h"

static bool tetris_ccci_region_empty(const struct ccci_mem_region *region)
{
	return !region->base_md_view_phy && !region->base_ap_view_phy &&
		!region->base_ap_view_vir && !region->size;
}

static void tetris_ccci_mem_abort(struct ccci_modem *md)
{
	struct tetris_ccci_smem_copy *copy = md->tetris_smem;

	if (!copy)
		return;
	/* Consumer arrays must no longer be reachable before dropping its ref.
	 * Provider's original boot pin, owner, mappings and claims remain intact.
	 */
	memset(&md->mem_layout, 0, sizeof(md->mem_layout));
	md->tetris_smem = NULL;
	module_put(copy->provider);
	kfree(copy);
}

static int tetris_ccci_mem_prepare(struct ccci_modem *md)
{
	struct tetris_ccci_smem_copy *copy;
	unsigned int i;
	int ret;

	if (!md)
		return -EINVAL;
	if (md->tetris_smem)
		return -EALREADY;
	if (!tetris_ccci_region_empty(&md->mem_layout.md_bank0) ||
	    !tetris_ccci_region_empty(&md->mem_layout.md_bank4_noncacheable_total) ||
	    !tetris_ccci_region_empty(&md->mem_layout.md_bank4_cacheable_total) ||
	    md->mem_layout.md_bank4_noncacheable || md->mem_layout.md_bank4_cacheable)
		return -EEXIST;
	copy = kzalloc(sizeof(*copy), GFP_KERNEL);
	if (!copy)
		return -ENOMEM;
	ret = mtk_ccci_owned_mapped_copy(copy);
	if (ret)
		goto free_copy;
	/* Defensive native shape checks, not a new security/READY certificate. */
	if (!copy->provider || copy->layout.md_bank0.base_ap_view_vir ||
	    !copy->layout.md_bank0.size || !copy->layout.md_bank0.base_ap_view_phy ||
	    !copy->layout.md_bank4_noncacheable_total.base_ap_view_vir ||
	    copy->layout.md_bank4_cacheable_total.base_ap_view_vir ||
	    copy->layout.md_bank4_noncacheable != copy->nc ||
	    copy->layout.md_bank4_cacheable != copy->cache ||
	    copy->nc[ARRAY_SIZE(copy->nc) - 1].id != SMEM_USER_MAX ||
	    copy->cache[ARRAY_SIZE(copy->cache) - 1].id != SMEM_USER_MAX) {
		ret = -EPROTO;
		goto put_provider;
	}
	for (i = 0; i < ARRAY_SIZE(copy->cache); i++) {
		if (copy->cache[i].id == SMEM_USER_RAW_MD_CONSYS &&
		    (copy->cache[i].base_ap_view_vir || !(copy->cache[i].flag & SMF_NO_REMAP))) {
			ret = -EPROTO;
			goto put_provider;
		}
	}
	/* Only this fresh unpublished md owns these arrays. Protected bank0 stays
	 * physical metadata, never mapped; no legacy getters or duplicate CCB split.
	 */
	md->mem_layout = copy->layout;
	md->tetris_smem = copy;
	return 0;
put_provider:
	if (copy->provider)
		module_put(copy->provider);
free_copy:
	kfree(copy);
	return ret;
}
#endif
