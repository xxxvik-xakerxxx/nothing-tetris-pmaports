/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_SMEM_RESERVATION_H
#define TETRIS_SMEM_RESERVATION_H
#include "tetris_runtime_smem/smem.h"
#include "smem_boot_evidence/boot_evidence.h"

#define TETRIS_SMEM_SPANS_MAX 23U
struct tetris_smem_extent {
	unsigned long long base;
	unsigned int bytes, bank;
};
struct tetris_smem_extent_plan {
	unsigned int count;
	struct tetris_smem_extent span[TETRIS_SMEM_SPANS_MAX];
};
struct resource;
struct tetris_smem_reservation {
	struct resource *held[TETRIS_SMEM_SPANS_MAX];
	unsigned int count;
};

/* Pure copied mapping geometry; no virtual pointers, grant or I/O. */
int tetris_smem_extent_preview(struct tetris_smem_owner *owner,
		struct tetris_smem_extent_plan *output);
/* Serialized init/exit only. Exact planned spans, never CONSYS/full bank tails.
 * iomem exclusivity is not NS permission, authentication or firmware START.
 */
int tetris_smem_reserve_extents(const struct tetris_smem_extent_plan *plan,
		const struct tetris_smem_boot_evidence *evidence,
		struct tetris_smem_reservation *reservation);
void tetris_smem_release_extents(struct tetris_smem_reservation *reservation);
#endif
