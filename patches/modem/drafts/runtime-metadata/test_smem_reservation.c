/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the actual packaged importer/plan, with real producer args. */
#include "tetris_runtime_smem/private.h"

static struct resource held_test[TETRIS_SMEM_SPANS_MAX];
static bool busy_test[TETRIS_SMEM_SPANS_MAX];
static unsigned int claim_calls, claim_fail, claim_releases;

struct resource *request_mem_region(resource_size_t base, resource_size_t bytes, const char *name)
{
	unsigned int i;

	assert(!strcmp(name, "tetris-ccci-smem"));
	if (++claim_calls == claim_fail)
		return NULL;
	for (i = 0; i < ARRAY_SIZE(held_test); i++)
		if (busy_test[i] && base <= held_test[i].end && held_test[i].start < base + bytes)
			return NULL;
	for (i = 0; i < ARRAY_SIZE(held_test); i++) {
		if (!busy_test[i]) {
			busy_test[i] = true;
			held_test[i] = (struct resource) { .start = base, .end = base + bytes - 1 };
			return &held_test[i];
		}
	}
	return NULL;
}

void release_mem_region(resource_size_t base, resource_size_t bytes)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(held_test); i++) {
		if (busy_test[i] && held_test[i].start == base && resource_size(&held_test[i]) == bytes) {
			busy_test[i] = false;
			claim_releases++;
			return;
		}
	}
	assert(!"attempt to release an unowned extent");
}

static void test_smem_reservation(const struct tetris_metadata_banks *banks)
{
	struct tetris_smem_owner *owner = NULL;
	struct tetris_smem_extent_plan plan, changed, untouched;
	struct tetris_smem_boot_evidence evidence;
	struct tetris_smem_reservation reservation = { 0 }, competing = { 0 };
	unsigned int i, mode;

	assert(!tetris_smem_from_arguments(banks, &owner));
	assert(!tetris_smem_extent_preview(owner, &plan));
	assert(plan.count == 2);
	assert(plan.span[0].base == banks->nc.base && plan.span[0].bank == 0);
	assert(plan.span[1].base > banks->cache.base && plan.span[1].bank == 1);
	assert(plan.span[1].base + plan.span[1].bytes <= banks->cache.base + owner->cache_size);
	memset(&untouched, 0xa5, sizeof(untouched));
	changed = untouched;
	assert(tetris_smem_extent_preview(NULL, &changed) == -EINVAL);
	assert(!memcmp(&changed, &untouched, sizeof(changed)));
	assert(tetris_smem_extent_preview(owner, (void *)owner) == -EINVAL);
	owner->state = TETRIS_SMEM_MAPPED; /* Fixture fault, never actual mappings. */
	assert(tetris_smem_extent_preview(owner, &changed) == -EALREADY);
	assert(!memcmp(&changed, &untouched, sizeof(changed)));
	owner->state = TETRIS_SMEM_VALIDATED;
	evidence_fixture(banks, owner->nc_size, owner->cache_size);
	assert(!tetris_smem_boot_decode(evidence_wire, sizeof(evidence_wire), banks, sizeof(*banks),
			&evidence, sizeof(evidence)));
	assert(!tetris_smem_destroy(owner));

	for (mode = 0; mode < 10; mode++) {
		changed = plan;
		switch (mode) {
		case 0: changed.count = 0; break;
		case 1: changed.count = TETRIS_SMEM_SPANS_MAX + 1; break;
		case 2: changed.span[0].bank = 2; break;
		case 3: changed.span[0].base = 0; break;
		case 4: changed.span[0].base++; break;
		case 5: changed.span[0].bytes = 0; break;
		case 6: changed.span[0].bytes++; break;
		case 7: changed.span[0].base = ~0ULL - PAGE_SIZE + 1; changed.span[0].bytes = PAGE_SIZE; break;
		case 8: changed.span[1] = changed.span[0]; break;
		case 9: changed.span[0].base = evidence.record[0].range_start + evidence.record[0].range_size; break;
		}
		claim_calls = claim_releases = 0;
		assert(tetris_smem_reserve_extents(&changed, &evidence, &reservation) < 0);
		assert(!claim_calls && !claim_releases && !reservation.count);
	}
	for (i = 1; i <= plan.count; i++) {
		claim_calls = claim_releases = 0;
		claim_fail = i;
		assert(tetris_smem_reserve_extents(&plan, &evidence, &reservation) == -EBUSY);
		assert(claim_calls == i && claim_releases == i - 1 && !reservation.count);
		for (mode = 0; mode < ARRAY_SIZE(held_test); mode++)
			assert(!busy_test[mode] && !reservation.held[mode]);
	}
	claim_fail = 0;
	claim_calls = claim_releases = 0;
	assert(!tetris_smem_reserve_extents(&plan, &evidence, &reservation));
	assert(reservation.count == plan.count && claim_calls == plan.count);
	assert(tetris_smem_reserve_extents(&plan, &evidence, &reservation) == -EALREADY);
	assert(claim_calls == plan.count);
	assert(tetris_smem_reserve_extents(&plan, &evidence, &competing) == -EBUSY);
	assert(reservation.count == plan.count && !competing.count && !claim_releases);
	tetris_smem_release_extents(&reservation);
	assert(!reservation.count && claim_releases == plan.count);
	tetris_smem_release_extents(&reservation);
	assert(claim_releases == plan.count);
	for (i = 0; i < ARRAY_SIZE(held_test); i++)
		assert(!busy_test[i] && !reservation.held[i]);
}
