/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/ioport.h>
#include <asm/page.h>
#include "smem_reservation.h"

void tetris_smem_release_extents(struct tetris_smem_reservation *reservation)
{
	while (reservation->count) {
		struct resource *held = reservation->held[--reservation->count];

		release_mem_region(held->start, resource_size(held));
		reservation->held[reservation->count] = NULL;
	}
}

int tetris_smem_reserve_extents(const struct tetris_smem_extent_plan *plan,
		const struct tetris_smem_boot_evidence *evidence,
		struct tetris_smem_reservation *reservation)
{
	unsigned int i, j;

	if (!plan || !evidence || !reservation || !plan->count ||
	    plan->count > TETRIS_SMEM_SPANS_MAX)
		return -EINVAL;
	if (reservation->count)
		return -EALREADY;
	/* Evidence was decoded by the sole caller. Never interpret claims as a
	 * fresh secure monitor response or permit any physical access here.
	 */
	if (evidence->version != 1 || evidence->scope != 1 || evidence->count != 2)
		return -EBADMSG;
	for (i = 0; i < TETRIS_SMEM_SPANS_MAX; i++)
		if (reservation->held[i])
			return -EINVAL;
	/* Validate the entire plan before claiming any range. */
	for (i = 0; i < plan->count; i++) {
		const struct tetris_smem_extent *span = &plan->span[i];
		const struct tetris_smem_boot_record *record;

		if (span->bank > 1 || !span->bytes || !span->base ||
		    ((span->base | span->bytes) & (PAGE_SIZE - 1)) ||
		    span->base > ~0ULL - span->bytes)
			return -ERANGE;
		record = &evidence->record[span->bank];
		if (record->bank != span->bank || record->slot != 42 + span->bank ||
		    span->base < record->range_start ||
		    span->base - record->range_start >= record->range_size ||
		    span->bytes > record->range_size - (span->base - record->range_start))
			return -ERANGE;
		for (j = 0; j < i; j++) {
			const struct tetris_smem_extent *previous = &plan->span[j];

			if (span->base < previous->base + previous->bytes &&
			    previous->base < span->base + span->bytes)
				return -EADDRINUSE;
		}
	}
	for (i = 0; i < plan->count; i++) {
		reservation->held[i] = request_mem_region(plan->span[i].base,
				plan->span[i].bytes, "tetris-ccci-smem");
		if (!reservation->held[i]) {
			tetris_smem_release_extents(reservation);
			return -EBUSY;
		}
		reservation->count++;
	}
	return 0;
}
