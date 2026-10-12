/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_CCCI_SMEM_PROVIDER_H
#define TETRIS_CCCI_SMEM_PROVIDER_H
#include "ap_md_mem.h"
struct module;

/* Native B4.1 table capacities, including their existing tail guards.
 * This is consumer storage, not a second table definition or permission ABI.
 */
#define TETRIS_CCCI_NC_COUNT 26
#define TETRIS_CCCI_CACHE_COUNT 11
struct tetris_ccci_smem_copy {
	struct module *provider;
	struct ccci_mem_layout layout;
	struct ccci_smem_region nc[TETRIS_CCCI_NC_COUNT];
	struct ccci_smem_region cache[TETRIS_CCCI_CACHE_COUNT];
};

/* Direct GPL symbol binding to the actual AP-only util module. Caller supplies
 * fresh private storage. On success it owns exactly one additional module ref;
 * on failure storage is unchanged and no reference is acquired. Provider owns
 * all mappings/claims until boot. Caller must NEVER iounmap returned addresses.
 */
int mtk_ccci_owned_mapped_copy(struct tetris_ccci_smem_copy *out);
#endif
