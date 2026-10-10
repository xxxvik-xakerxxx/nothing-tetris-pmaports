/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_RUNTIME_SMEM_PRIVATE_H
#define TETRIS_RUNTIME_SMEM_PRIVATE_H
#include <linux/mutex.h>
#include "smem.h"

enum tetris_smem_state {
	TETRIS_SMEM_VALIDATED = 1, TETRIS_SMEM_MAPPED,
	TETRIS_SMEM_PUBLISHED, TETRIS_SMEM_FAILED,
};

struct tetris_smem_row {
	unsigned int id, offset, size, flags, md_offset, bank;
	void __iomem *virtual;
};
struct tetris_smem_span {
	unsigned int bank, offset, size;
	void __iomem *virtual;
};
struct tetris_smem_owner {
	struct mutex lock;
	enum tetris_smem_state state;
	int first_error;
	struct tetris_metadata_banks banks;
	unsigned int logical, nc_size, cache_size, span_count;
	struct tetris_smem_row rows[23];
	struct tetris_smem_span spans[23];
	struct ccci_smem_region nc[26], cache[11];
	struct ccci_mem_layout layout;
};
struct tetris_smem_slot {
	struct mutex lock;
	struct tetris_smem_owner *owner;
};

/* Unattached transaction primitive. NO shipping caller, Kconfig or DT hook.
 * It has no permission callback/boolean: a future real caller MUST establish
 * NS range/security/coherency ownership before invoking this function.
 */
int tetris_smem_map_private(struct tetris_smem_owner *owner);
void tetris_smem_slot_init(struct tetris_smem_slot *slot);
int tetris_smem_publish_private(struct tetris_smem_slot *slot,
		struct tetris_smem_owner *owner);
/* Copy tables into consumer-owned storage; never expose mutable owner tables.
 * Published mappings cannot be freed, even after an export error.
 */
int tetris_smem_export_private(struct tetris_smem_slot *slot,
		struct ccci_mem_layout *layout, struct ccci_smem_region *nc,
		unsigned int nc_count, struct ccci_smem_region *cache,
		unsigned int cache_count);
#endif
