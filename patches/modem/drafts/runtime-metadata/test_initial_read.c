/* SPDX-License-Identifier: GPL-2.0-only */
/* Native boundary only: included with the actual generated importer and init. */
#if !CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
static unsigned int initial_read_boundary_calls;
#endif

#if CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ
#include <stdarg.h>
static unsigned long test_cpu_el = CurrentEL_EL1;
static unsigned int test_word, initial_read_fault;
static bool map_fail;
static unsigned int mapped_word, releases_at_map, pins_at_map, log_calls;
static bool logged_nonzero;

static void initial_read_log(const char *format, ...)
{
	const char *scalar;
	va_list args;

	assert(!strcmp(format, "Tetris CCCI: initial NC read completed; %s\n"));
	assert(!read_mapped && read_calls == unmap_calls && read_calls);
	assert(module_pins == pins_at_map && claim_releases == releases_at_map);
	va_start(args, format);
	scalar = va_arg(args, const char *);
	assert(!strcmp(scalar, test_word ? "nonzero" : "zero"));
	logged_nonzero = !strcmp(scalar, "nonzero");
	va_end(args);
	log_calls++;
}

unsigned long test_read_sysreg_CurrentEL(void)
{
	initial_read_boundary_calls++;
	el_calls++;
	assert(tetris_owned_smem_plan.reservation.count ==
			tetris_owned_smem_plan.extents.count);
	assert(!tetris_owned_smem_plan.ready && !read_mapped);
	return test_cpu_el;
}

void *ioremap_wc(phys_addr_t base, size_t bytes)
{
	initial_read_boundary_calls++;
	map_calls++;
	assert(test_cpu_el == CurrentEL_EL1 && !read_mapped);
	assert(!tetris_owned_smem_plan.ready);
	assert(base == tetris_owned_smem_plan.extents.span[0].base);
	assert(tetris_owned_smem_plan.extents.span[0].bank == 0);
	assert(bytes == PAGE_SIZE);
	assert(tetris_owned_smem_plan.reservation.count == 2);
	assert(el_calls == map_calls);
	if (map_fail)
		return NULL;
	releases_at_map = claim_releases;
	pins_at_map = module_pins;
	read_mapped = true;
	mapped_word = test_word;
	return &mapped_word;
}

unsigned int readl(const void *address)
{
	initial_read_boundary_calls++;
	read_calls++;
	assert(read_mapped && address == &mapped_word);
	assert(!tetris_owned_smem_plan.ready && claim_releases == releases_at_map);
	assert(module_pins == pins_at_map);
	assert(read_calls == unmap_calls + 1 && read_calls == map_calls);
	return mapped_word;
}

void iounmap(void *address)
{
	initial_read_boundary_calls++;
	unmap_calls++;
	assert(read_mapped && address == &mapped_word);
	assert(read_calls == unmap_calls);
	read_mapped = false;
	/* Poison after unmap to detect retained or repeated reads. */
	mapped_word = 0xa5a5a5a5U;
}

/* Inject after reserve_extents validated its full input, at the last claim.
 * The real init must revalidate the copied state before mapping or pinning.
 */
static void initial_read_claim_fault(void)
{
	struct tetris_smem_boot_record *record = &tetris_owned_smem_plan.boot_evidence.record[0];
	struct tetris_smem_extent_plan *plan = &tetris_owned_smem_plan.extents;

	if (!initial_read_fault || !tetris_owned_smem_plan.owner ||
	    claim_calls != plan->count)
		return;
	switch (initial_read_fault) {
	case 1: plan->span[0].bank = 1; break;
	case 2: plan->span[0].base += PAGE_SIZE; break;
	case 3: plan->span[0].bytes -= PAGE_SIZE; break;
	case 4: record->range_size = PAGE_SIZE; break;
	case 5: record->actual_enable = 0; break;
	case 6: record->actual_start += 4096; break;
	case 7: record->actual_end += 4096; break;
	case 8: record->policy[7] &= ~(3ULL << 34); break;
	case 9: record->policy[7] &= ~(1ULL << 34); break;
	case 10: record->policy[7] &= ~(2ULL << 34); break;
	case 11: tetris_owned_smem_plan.boot_evidence.scope = 2; break;
	case 12: record->slot = 43; break;
	case 13: record->bank = 1; break;
	case 14: record->reservation_capacity -= PAGE_SIZE; break;
	case 15: record->range_start += 4096; break;
	case 16: plan->count = 0; break;
	case 17: tetris_owned_smem_plan.has_boot_evidence = false; break;
	case 18: tetris_owned_smem_plan.owner->first_error = -EIO;
		tetris_owned_smem_plan.owner->state = TETRIS_SMEM_FAILED; break;
	default: assert(!"unknown initial read fault");
	}
}

static void reset_initial_read_boundary(void)
{
	assert(!read_mapped);
	el_calls = map_calls = read_calls = unmap_calls = 0;
	log_calls = 0;
	initial_read_boundary_calls = initial_read_fault = 0;
	claim_calls = claim_releases = claim_fail = 0;
	test_cpu_el = CurrentEL_EL1;
	map_fail = false;
}

static void assert_initial_read_cleanup(unsigned int pins)
{
	unsigned int i;

	assert(!tetris_owned_smem_plan.owner && !tetris_owned_smem_plan.ready);
	assert(!tetris_owned_smem_plan.has_boot_evidence);
	assert(!tetris_owned_smem_plan.reservation.count && module_pins == pins);
	assert(!read_mapped);
	for (i = 0; i < ARRAY_SIZE(held_test); i++)
		assert(!busy_test[i] && !tetris_owned_smem_plan.reservation.held[i]);
	/* Cleanup is atomic from the caller's perspective and idempotent. */
	mtk_ccci_owned_smem_cleanup();
	assert(module_pins == pins && !read_mapped);
}

static void test_initial_read(const struct tetris_metadata_banks *banks)
{
	struct tetris_smem_owner *seed = NULL;
	unsigned int nc_size, cache_size, i, pins = module_pins;
	static const int fault_error[] = { 0, -ERANGE, -ERANGE, -ERANGE,
		-ERANGE, -EACCES, -EACCES, -EACCES, -EACCES, -EACCES, -EACCES,
		-EBADMSG, -EBADMSG, -EBADMSG, -EBADMSG, -ERANGE, -ERANGE,
		-ENODATA, -EIO };
	static const unsigned long wrong_el[] = { 0, 2UL << 2, 3UL << 2, 5 };

	assert(!tetris_smem_from_arguments(banks, &seed));
	nc_size = seed->nc_size;
	cache_size = seed->cache_size;
	assert(!tetris_smem_destroy(seed));
	node_exists = compatible = property_exists = true;
	property_length = sizeof(evidence_wire);
	property_read_error = 0;
	for (i = 1; i < ARRAY_SIZE(fault_error); i++) {
		reset_initial_read_boundary();
		evidence_fixture(banks, nc_size, cache_size);
		initial_read_fault = i;
		assert(mtk_ccci_owned_smem_init() == fault_error[i]);
		assert(claim_calls == 2 && claim_releases == 2);
		assert(!el_calls && !map_calls && !read_calls && !unmap_calls);
		assert(!log_calls);
		assert_initial_read_cleanup(pins);
	}
	for (i = 0; i < ARRAY_SIZE(wrong_el); i++) {
		reset_initial_read_boundary();
		evidence_fixture(banks, nc_size, cache_size);
		test_cpu_el = wrong_el[i];
		assert(mtk_ccci_owned_smem_init() == -EACCES);
		assert(claim_calls == 2 && claim_releases == 2 && el_calls == 1);
		assert(!map_calls && !read_calls && !unmap_calls);
		assert(!log_calls);
		assert_initial_read_cleanup(pins);
	}
	reset_initial_read_boundary();
	evidence_fixture(banks, nc_size, cache_size);
	map_fail = true;
	assert(mtk_ccci_owned_smem_init() == -ENOMEM);
	assert(claim_calls == 2 && claim_releases == 2);
	assert(el_calls == 1 && map_calls == 1 && !read_calls && !unmap_calls);
	assert(!log_calls);
	assert_initial_read_cleanup(pins);
	for (i = 1; i <= 2; i++) {
		reset_initial_read_boundary();
		evidence_fixture(banks, nc_size, cache_size);
		claim_fail = i;
		assert(mtk_ccci_owned_smem_init() == -EBUSY);
		assert(claim_calls == i && claim_releases == i - 1);
		assert(!initial_read_boundary_calls);
		assert_initial_read_cleanup(pins);
	}
	for (i = 0; i < 2; i++) {
		reset_initial_read_boundary();
		evidence_fixture(banks, nc_size, cache_size);
		test_word = i ? 0xfedcba98U : 0;
		assert(!mtk_ccci_owned_smem_init());
		assert(el_calls == 1 && map_calls == 1 && read_calls == 1 && unmap_calls == 1);
		assert(initial_read_boundary_calls == 4 && !read_mapped);
		assert(log_calls == 1 && logged_nonzero == !!i);
		assert(tetris_owned_smem_plan.owner && tetris_owned_smem_plan.ready);
		assert(module_pins == ++pins && !claim_releases);
		assert(tetris_owned_smem_plan.reservation.count == 2);
		assert(!tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.base_ap_view_vir);
		assert(!tetris_owned_smem_plan.layout.md_bank4_cacheable_total.base_ap_view_vir);
		assert(mtk_ccci_owned_smem_init() == -EALREADY);
		assert(initial_read_boundary_calls == 4);
		/* Only the fixture simulates boot-end teardown of a pinned module. */
		mtk_ccci_owned_smem_cleanup();
		assert(claim_releases == 2);
		assert_initial_read_cleanup(pins);
	}
}
#elif !CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
/* Link traps also cover the metadata and resource-only native profiles. */
unsigned long test_read_sysreg_CurrentEL(void)
{
	initial_read_boundary_calls++;
	assert(!"unexpected CPU boundary in default profile");
	return 0;
}
void *ioremap_wc(phys_addr_t base, size_t bytes)
{
	(void)base;
	(void)bytes;
	initial_read_boundary_calls++;
	assert(!"unexpected SMEM map in default profile");
	return NULL;
}
unsigned int readl(const void *address)
{
	(void)address;
	initial_read_boundary_calls++;
	assert(!"unexpected SMEM read in default profile");
	return 0;
}
void iounmap(void *address)
{
	(void)address;
	initial_read_boundary_calls++;
	assert(!"unexpected SMEM unmap in default profile");
}
#endif
