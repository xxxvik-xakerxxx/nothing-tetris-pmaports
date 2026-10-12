/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual generated init and transactions; only kernel boundaries are mocked. */
#if CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
static unsigned long mapped_cpu_el = CurrentEL_EL1;
static unsigned int mapped_el_calls, mapped_calls, mapped_unmaps, mapped_live;
static unsigned int mapped_fail, mapped_fault, export_calls;
static bool export_fail;
static void *mapped_addresses[TETRIS_SMEM_SPANS_MAX];
static unsigned int mapped_order[TETRIS_SMEM_SPANS_MAX];
static resource_size_t expected_claim_base[2];

unsigned long test_read_sysreg_CurrentEL(void)
{
	assert(!tetris_owned_smem_plan.ready && !mapped_live);
	assert(tetris_owned_smem_plan.reservation.count == 2);
	mapped_el_calls++;
	return mapped_cpu_el;
}

void *ioremap_wc(phys_addr_t base, size_t bytes)
{
	const struct tetris_smem_extent_plan *plan = &tetris_owned_smem_plan.extents;
	unsigned int i = mapped_live;
	void *address;

	assert(mapped_cpu_el == CurrentEL_EL1 && !tetris_owned_smem_plan.ready);
	assert(mapped_el_calls && i < plan->count);
	assert(base == plan->span[i].base && bytes == plan->span[i].bytes);
	assert(tetris_owned_smem_plan.reservation.count == plan->count);
	assert(tetris_owned_smem_plan.reservation.held[i]->start == base);
	assert(tetris_owned_smem_plan.reservation.held[i]->end == base + bytes - 1);
	if (++mapped_calls == mapped_fail)
		return NULL;
	address = calloc(1, bytes);
	assert(address);
	mapped_addresses[i] = address;
	mapped_live++;
	return address;
}

unsigned int readl(const void *address)
{
	(void)address;
	assert(!"MAP_ONLY must not read SMEM");
	return 0;
}

void iounmap(void *address)
{
	assert(mapped_live && address == mapped_addresses[mapped_live - 1]);
	/* Claims must remain held until every mapping has been unwound. */
	assert(tetris_owned_smem_plan.reservation.count == 2);
	mapped_order[mapped_unmaps++ % TETRIS_SMEM_SPANS_MAX] = mapped_live;
	mapped_addresses[--mapped_live] = NULL;
	free(address);
}

int __real_tetris_smem_export_mapped_private(struct tetris_smem_owner *,
	struct ccci_mem_layout *, struct ccci_smem_region *, unsigned int,
	struct ccci_smem_region *, unsigned int);

int __wrap_tetris_smem_export_mapped_private(struct tetris_smem_owner *owner,
	struct ccci_mem_layout *layout, struct ccci_smem_region *nc, unsigned int nc_count,
	struct ccci_smem_region *cache, unsigned int cache_count)
{
	struct ccci_mem_layout before = *layout;
	struct ccci_smem_region before_nc[26], before_cache[11];
	unsigned int pins = module_pins;
	int ret;

	assert(owner == tetris_owned_smem_plan.owner && owner->state == TETRIS_SMEM_MAPPED);
	assert(mapped_live == 2 && !tetris_owned_smem_plan.ready);
	memcpy(before_nc, nc, sizeof(before_nc));
	memcpy(before_cache, cache, sizeof(before_cache));
	export_calls++;
	ret = __real_tetris_smem_export_mapped_private(owner, layout, nc,
		export_fail ? 25 : nc_count, cache, cache_count);
	assert(module_pins == pins && mapped_live == 2);
	if (ret) {
		assert(!memcmp(&before, layout, sizeof(before)));
		assert(!memcmp(before_nc, nc, sizeof(before_nc)));
		assert(!memcmp(before_cache, cache, sizeof(before_cache)));
	}
	return ret;
}

static void assert_mapped_private_copy(void)
{
	struct tetris_smem_owner *owner = tetris_owned_smem_plan.owner;
	struct ccci_mem_layout *layout = &tetris_owned_smem_plan.layout;
	unsigned int i;

	assert(owner && owner->state == TETRIS_SMEM_MAPPED && mapped_live == 2);
	assert(layout->md_bank4_noncacheable == tetris_owned_smem_plan.nc);
	assert(layout->md_bank4_cacheable == tetris_owned_smem_plan.cache);
	assert(layout->md_bank4_noncacheable != owner->nc);
	assert(layout->md_bank4_cacheable != owner->cache);
	assert(layout->md_bank4_noncacheable_total.base_ap_view_vir == mapped_addresses[0]);
	assert(!layout->md_bank4_cacheable_total.base_ap_view_vir);
	assert(!layout->md_bank0.base_ap_view_vir);
	for (i = 0; i < ARRAY_SIZE(owner->cache); i++) {
		assert(!memcmp(&owner->cache[i], &tetris_owned_smem_plan.cache[i], sizeof(owner->cache[i])));
		if (owner->cache[i].flag & 8)
			assert(!owner->cache[i].base_ap_view_vir);
	}
	assert(!memcmp(owner->nc, tetris_owned_smem_plan.nc, sizeof(owner->nc)));
	/* Private copies do not alias owner storage (fixture-only mutation). */
	tetris_owned_smem_plan.nc[0].offset ^= 1;
	assert(tetris_owned_smem_plan.nc[0].offset != owner->nc[0].offset);
	tetris_owned_smem_plan.nc[0].offset ^= 1;
}

static void map_only_claim_fault(void)
{
	struct tetris_smem_extent_plan *plan = &tetris_owned_smem_plan.extents;
	struct tetris_smem_boot_evidence *e = &tetris_owned_smem_plan.boot_evidence;
	struct tetris_smem_boot_record *record;
	unsigned int bank;

	if (!mapped_fault || !tetris_owned_smem_plan.owner || claim_calls != plan->count)
		return;
	if (mapped_fault <= 24) {
		bank = (mapped_fault - 1) / 12;
		record = &e->record[bank];
		switch ((mapped_fault - 1) % 12) {
		case 0: record->bank ^= 1; break;
		case 1: record->slot++; break;
		case 2: record->reservation_base += PAGE_SIZE; break;
		case 3: record->reservation_capacity -= PAGE_SIZE; break;
		case 4: record->range_start += PAGE_SIZE; break;
		case 5: record->range_size = PAGE_SIZE;
			record->actual_end = record->range_start + PAGE_SIZE; break;
		case 6: record->actual_enable = 0; break;
		case 7: record->actual_start += PAGE_SIZE; break;
		case 8: record->actual_end += PAGE_SIZE; break;
		case 9: record->policy[7] &= ~(3ULL << 34); break;
		case 10: record->policy[7] &= ~(1ULL << 34); break;
		case 11: record->policy[7] &= ~(2ULL << 34); break;
		}
		return;
	}
	switch (mapped_fault) {
	case 25: e->version++; break;
	case 26: e->bytes--; break;
	case 27: e->scope++; break;
	case 28: e->count--; break;
	case 29: plan->span[1].base += PAGE_SIZE; break;
	case 30: plan->span[1].bytes -= PAGE_SIZE; break;
	case 31: plan->span[1].bank = 0; break;
	case 32: plan->count--; break;
	case 33: tetris_owned_smem_plan.has_boot_evidence = false; break;
	case 34: tetris_owned_smem_plan.owner->banks.cache.capacity -= PAGE_SIZE; break;
	case 35: tetris_owned_smem_plan.owner->first_error = -EIO;
		tetris_owned_smem_plan.owner->state = TETRIS_SMEM_FAILED; break;
	case 36: tetris_owned_banks.nc.base += PAGE_SIZE; break;
	case 37: plan->span[0].base += PAGE_SIZE; break;
	case 38: plan->span[0].bytes -= PAGE_SIZE; break;
	case 39: plan->span[0].bank = 1; break;
	case 40: tetris_owned_smem_plan.owner->rows[0].flags |= 8; break;
	default: assert(!"unknown mapped postclaim fault");
	}
}

static void reset_map_only(void)
{
	assert(!mapped_live);
	mapped_el_calls = mapped_calls = mapped_unmaps = mapped_fail = mapped_fault = 0;
	export_calls = 0;
	export_fail = false;
	mapped_cpu_el = CurrentEL_EL1;
	claim_calls = claim_releases = claim_fail = 0;
	memset(mapped_order, 0, sizeof(mapped_order));
	memset(claim_release_order, 0, sizeof(claim_release_order));
}

static void assert_map_only_cleanup(unsigned int pins)
{
	unsigned int i;

	assert(!mapped_live && module_pins == pins);
	assert(!tetris_owned_smem_plan.owner && !tetris_owned_smem_plan.ready);
	assert(!tetris_owned_smem_plan.reservation.count);
	assert(!tetris_owned_smem_plan.layout.md_bank4_noncacheable);
	for (i = 0; i < ARRAY_SIZE(held_test); i++)
		assert(!busy_test[i]);
	assert(claim_releases == 2 && claim_release_order[0] == expected_claim_base[1] &&
		claim_release_order[1] == expected_claim_base[0]);
	mtk_ccci_owned_smem_cleanup();
	assert(!mapped_live && module_pins == pins);
}

static void test_map_only(const struct tetris_metadata_banks *banks)
{
	struct tetris_smem_owner *seed = NULL;
	unsigned int nc_size, cache_size, i, pins = module_pins;
	static const unsigned long wrong_el[] = { 0, 2UL << 2, 3UL << 2, 5 };

	assert(!tetris_smem_from_arguments(banks, &seed));
	{
		struct tetris_smem_extent_plan plan;

		assert(!tetris_smem_extent_preview(seed, &plan) && plan.count == 2);
		expected_claim_base[0] = plan.span[0].base;
		expected_claim_base[1] = plan.span[1].base;
	}
	nc_size = seed->nc_size;
	cache_size = seed->cache_size;
	assert(!tetris_smem_destroy(seed));
	node_exists = compatible = property_exists = true;
	property_length = sizeof(evidence_wire);
	property_read_error = 0;
	for (i = 1; i <= 40; i++) {
		int expected = -ERANGE;

		reset_map_only();
		evidence_fixture(banks, nc_size, cache_size);
		mapped_fault = i;
		if (i <= 24) {
			unsigned int field = (i - 1) % 12;
			expected = field < 4 ? -EBADMSG : field < 6 ? -ERANGE : -EACCES;
		} else if (i <= 28)
			expected = -EBADMSG;
		else if (i == 33)
			expected = -ENODATA;
		else if (i == 35)
			expected = -EIO;
		else if (i == 40)
			expected = -EADDRNOTAVAIL;
		assert(mtk_ccci_owned_smem_init() == expected);
		tetris_owned_banks = *banks;
		assert(claim_calls == 2 && claim_releases == 2);
		assert(!mapped_el_calls && !mapped_calls && !mapped_unmaps && !export_calls);
		assert_map_only_cleanup(pins);
	}
	/* Actual postclaim geometry with malformed held handles. Restore the
	 * fixture resource before cleanup: the kernel owns those resource objects.
	 */
	for (i = 0; i < 6; i++) {
		struct resource *held;
		struct resource before;
		unsigned int index = i / 3;

		reset_map_only();
		evidence_fixture(banks, nc_size, cache_size);
		assert(!tetris_smem_from_arguments(banks, &tetris_owned_smem_plan.owner));
		assert(!tetris_smem_preview(tetris_owned_smem_plan.owner,
			&tetris_owned_smem_plan.layout, tetris_owned_smem_plan.nc, 26,
			tetris_owned_smem_plan.cache, 11));
		assert(!tetris_smem_extent_preview(tetris_owned_smem_plan.owner,
			&tetris_owned_smem_plan.extents));
		assert(!collect_boot_evidence(banks));
		assert(!tetris_smem_reserve_extents(&tetris_owned_smem_plan.extents,
			&tetris_owned_smem_plan.boot_evidence, &tetris_owned_smem_plan.reservation));
		held = tetris_owned_smem_plan.reservation.held[index];
		before = *held;
		switch (i % 3) {
		case 0: held->start++; break;
		case 1: held->end--; break;
		case 2: tetris_owned_smem_plan.reservation.held[index] = NULL; break;
		}
		assert(map_owned_smem(banks) == -ERANGE);
		assert(!mapped_el_calls && !mapped_calls && !export_calls);
		*held = before;
		tetris_owned_smem_plan.reservation.held[index] = held;
		mtk_ccci_owned_smem_cleanup();
		assert(claim_releases == 2);
		assert_map_only_cleanup(pins);
	}
	for (i = 0; i < ARRAY_SIZE(wrong_el); i++) {
		reset_map_only();
		evidence_fixture(banks, nc_size, cache_size);
		mapped_cpu_el = wrong_el[i];
		assert(mtk_ccci_owned_smem_init() == -EACCES);
		assert(mapped_el_calls == 1 && !mapped_calls && !export_calls);
		assert(claim_releases == 2);
		assert_map_only_cleanup(pins);
	}
	for (i = 1; i <= 2; i++) {
		reset_map_only();
		evidence_fixture(banks, nc_size, cache_size);
		mapped_fail = i;
		assert(mtk_ccci_owned_smem_init() == -ENOMEM);
		assert(mapped_calls == i && mapped_unmaps == i - 1 && !export_calls);
		assert(claim_releases == 2);
		assert_map_only_cleanup(pins);
	}
	reset_map_only();
	evidence_fixture(banks, nc_size, cache_size);
	export_fail = true;
	assert(mtk_ccci_owned_smem_init() == -EINVAL);
	assert(export_calls == 1 && mapped_calls == 2 && mapped_unmaps == 2);
	assert(mapped_order[0] == 2 && mapped_order[1] == 1 && claim_releases == 2);
	assert_map_only_cleanup(pins);
	reset_map_only();
	evidence_fixture(banks, nc_size, cache_size);
	assert(!mtk_ccci_owned_smem_init());
	assert_mapped_private_copy();
	assert(module_pins == ++pins && !claim_releases && !mapped_unmaps);
	assert(mapped_calls == 2 && export_calls == 1);
	assert(mtk_ccci_owned_smem_init() == -EALREADY);
	assert(mapped_calls == 2 && export_calls == 1);
	/* Fixture-only boot end, not an unload path for the boot-pinned module. */
	mtk_ccci_owned_smem_cleanup();
	assert(mapped_order[0] == 2 && mapped_order[1] == 1 && claim_releases == 2);
	assert_map_only_cleanup(pins);
}
#endif
