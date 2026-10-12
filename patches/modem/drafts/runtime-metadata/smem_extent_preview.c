/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/string.h>
#include "tetris_runtime_smem/private.h"
#include "smem_reservation.h"

int tetris_smem_extent_preview(struct tetris_smem_owner *owner,
		struct tetris_smem_extent_plan *output)
{
	struct tetris_smem_extent_plan plan = { 0 };
	unsigned long out = (unsigned long)output, source = (unsigned long)owner;
	unsigned int i;
	int ret = 0;

	if (!owner || !output || out > ~0UL - sizeof(*output) ||
	    source > ~0UL - sizeof(*owner) ||
	    (out < source + sizeof(*owner) && source < out + sizeof(*output)))
		return -EINVAL;
	mutex_lock(&owner->lock);
	if (owner->state != TETRIS_SMEM_VALIDATED) {
		ret = owner->first_error ? owner->first_error : -EALREADY;
		goto out;
	}
	if (!owner->span_count || owner->span_count > TETRIS_SMEM_SPANS_MAX) {
		ret = -ERANGE;
		goto out;
	}
	plan.count = owner->span_count;
	for (i = 0; i < plan.count; i++) {
		const struct tetris_smem_span *span = &owner->spans[i];
		const struct tetris_metadata_window *bank = span->bank ? &owner->banks.cache : &owner->banks.nc;

		if (span->bank > 1 || !span->size || span->virtual ||
		    span->offset >= bank->capacity || span->size > bank->capacity - span->offset ||
		    bank->base > ~0ULL - bank->capacity) {
			ret = -ERANGE;
			goto out;
		}
		plan.span[i] = (struct tetris_smem_extent) {
			.base = bank->base + span->offset, .bytes = span->size, .bank = span->bank,
		};
	}
	memcpy(output, &plan, sizeof(plan));
out:
	mutex_unlock(&owner->lock);
	return ret;
}
