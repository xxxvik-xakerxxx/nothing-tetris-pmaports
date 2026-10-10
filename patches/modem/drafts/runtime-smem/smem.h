/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_RUNTIME_SMEM_H
#define TETRIS_RUNTIME_SMEM_H
#include "metadata_resources.h"
#include "ap_md_mem.h"

struct tetris_smem_owner;

struct tetris_smem_input {
	const unsigned char *chk;
	unsigned int chk_bytes;
	const unsigned char *nc;
	unsigned int nc_bytes;
	const unsigned char *cache;
	unsigned int cache_bytes;
	struct tetris_metadata_banks banks;
};

/* Pure metadata admission, not an NS access grant. Output unchanged on error. */
int tetris_smem_create(const struct tetris_smem_input *input,
		struct tetris_smem_owner **output);
/* Read the existing private FROM_KERNEL args during serialized util init.
 * Does not map SMEM or connect to registration. Banks must come from the
 * same retained reservation validation as the published metadata importer.
 */
int tetris_smem_from_arguments(const struct tetris_metadata_banks *banks,
		struct tetris_smem_owner **output);
/* Useful pure plan output: all virtual addresses remain NULL. */
int tetris_smem_preview(struct tetris_smem_owner *owner,
		struct ccci_mem_layout *layout, struct ccci_smem_region *nc,
		unsigned int nc_count, struct ccci_smem_region *cache,
		unsigned int cache_count);
/* Only unpublished owners may be destroyed; published mappings stay pinned. */
int tetris_smem_destroy(struct tetris_smem_owner *owner);
#endif
