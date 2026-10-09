// SPDX-License-Identifier: GPL-2.0-only
/* Compile the actual candidate adapter/core against fault-injected OS calls. */
#include "sram-host.h"
#include "mt6878-gpueb-sram-core.c"
#include "mt6878-gpueb-sram.c"
#include <stdio.h>

static struct resource claimed;
static int claim_active, fail_alloc, fail_map, claims, releases, maps, unmaps;

static void *kzalloc(size_t bytes, int flags)
{
	assert(flags == GFP_KERNEL);
	return fail_alloc ? NULL : calloc(1, bytes);
}

static void kfree(void *pointer) { free(pointer); }

static struct resource *request_mem_region(uint64_t start, uint64_t size, const char *name)
{
	assert(start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE && name);
	claims++;
	if (claim_active)
		return NULL;
	claim_active = 1;
	claimed = (struct resource){ start, start + size - 1, IORESOURCE_MEM };
	return &claimed;
}

static void release_mem_region(uint64_t start, uint64_t size)
{
	assert(claim_active && start == claimed.start && size == GPUEB_SRAM_SIZE);
	claim_active = 0;
	releases++;
}

static void *ioremap(uint64_t start, uint64_t size)
{
	assert(claim_active && start == GPUEB_SRAM_BASE && size == GPUEB_SRAM_SIZE);
	maps++;
	return fail_map ? NULL : malloc(size);
}

static void iounmap(void *mapping)
{
	assert(mapping && claim_active);
	unmaps++;
	free(mapping);
}

static void test_core(void)
{
	struct gpueb_sram_core core = { 0 };
	struct gpueb_sram_range result = { 7, 8 };
	assert(gpueb_sram_validate(UINT64_MAX, 2) == -ERANGE);
	assert(gpueb_sram_validate(GPUEB_SRAM_BASE, 0) == -ERANGE);
	assert(gpueb_sram_validate(GPUEB_SRAM_BASE + 4, GPUEB_SRAM_SIZE) == -EINVAL);
	assert(gpueb_sram_validate(GPUEB_SRAM_BASE, GPUEB_SRAM_SIZE - 4) == -EINVAL);
	assert(gpueb_sram_open(NULL, 0, 0) == -EINVAL);
	assert(gpueb_sram_claim_window(&core, GPUEB_WINDOW_GPR) == -ESHUTDOWN);
	assert(gpueb_sram_close(&core) == -EINVAL);
	assert(!gpueb_sram_open(&core, GPUEB_SRAM_BASE, GPUEB_SRAM_SIZE));
	assert(gpueb_sram_open(&core, GPUEB_SRAM_BASE, GPUEB_SRAM_SIZE) == -EBUSY);
	assert(gpueb_sram_claim_window(&core, -1) == -EINVAL);
	assert(gpueb_sram_claim_window(&core, GPUEB_WINDOW_COUNT) == -EINVAL);
	assert(gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, 0, 4, &result) == -ENOENT);
	assert(result.start == 7 && result.size == 8);
	assert(!gpueb_sram_claim_window(&core, GPUEB_WINDOW_GPR));
	assert(gpueb_sram_claim_window(&core, GPUEB_WINDOW_GPR) == -EBUSY);
	assert(!gpueb_sram_claim_window(&core, GPUEB_WINDOW_MBOX));
	assert(gpueb_sram_close(&core) == -EBUSY);
	assert(gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, UINT64_MAX, 4, &result) == -ERANGE);
	assert(gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, 0, UINT64_MAX, &result) == -ERANGE);
	assert(gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, 1, 4, &result) == -ERANGE);
	assert(gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, 0, 0, &result) == -ERANGE);
	assert(gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, GPUEB_GPR_SIZE, 4, &result) == -ERANGE);
	assert(!gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, GPUEB_GPR_SIZE - 4, 4, &result));
	assert(result.start + result.size == GPUEB_SRAM_BASE + GPUEB_MBOX_OFFSET);
	assert(!gpueb_sram_window_range(&core, GPUEB_WINDOW_MBOX, 0, GPUEB_MBOX_SIZE, &result));
	assert(result.start + result.size == GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE);
	assert(!gpueb_sram_quarantine(&core));
	assert(!gpueb_sram_quarantine(&core));
	assert(gpueb_sram_window_range(&core, GPUEB_WINDOW_GPR, 0, 4, &result) == -ESHUTDOWN);
	assert(!gpueb_sram_put_window(&core, GPUEB_WINDOW_GPR));
	assert(gpueb_sram_put_window(&core, GPUEB_WINDOW_GPR) == -ENOENT);
	assert(!gpueb_sram_put_window(&core, GPUEB_WINDOW_MBOX));
	assert(gpueb_sram_close(&core) == -EBUSY);
	assert(gpueb_sram_claim_window(&core, GPUEB_WINDOW_MBOX) == -ESHUTDOWN);
}

struct contender { struct mt6878_gpueb_sram *sram; struct mt6878_gpueb_window *window; };
static void *contend(void *argument)
{
	struct contender *c = argument;
	c->window = mt6878_gpueb_sram_get_window(c->sram, GPUEB_WINDOW_GPR);
	return NULL;
}

static void test_adapter(void)
{
	struct device parent = { 0 };
	struct resource resource = { GPUEB_SRAM_BASE, GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE - 1,
				     IORESOURCE_MEM };
	struct resource bad = resource;
	struct mt6878_gpueb_sram *sram;
	struct mt6878_gpueb_window *gpr, *mbox;
	struct gpueb_sram_range range;
	struct contender contenders[2];
	pthread_t threads[2];
	int old_releases, old_unmaps;

	assert(PTR_ERR(mt6878_gpueb_sram_create(NULL, &resource)) == -EINVAL);
	assert(PTR_ERR(mt6878_gpueb_sram_create(&parent, NULL)) == -EINVAL);
	assert(mt6878_gpueb_sram_destroy(NULL) == -EINVAL);
	assert(mt6878_gpueb_sram_unknown_start(NULL) == -EINVAL);
	assert(mt6878_gpueb_sram_describe(NULL, 0, 4, &range) == -EINVAL);
	assert(PTR_ERR(mt6878_gpueb_sram_get_window(NULL, GPUEB_WINDOW_GPR)) == -EINVAL);
	bad.end = UINT64_MAX;
	assert(PTR_ERR(mt6878_gpueb_sram_create(&parent, &bad)) == -ERANGE);
	bad.end = bad.start - 1;
	assert(PTR_ERR(mt6878_gpueb_sram_create(&parent, &bad)) == -EINVAL);
	bad = resource; bad.flags = 0;
	assert(PTR_ERR(mt6878_gpueb_sram_create(&parent, &bad)) == -EINVAL);
	assert(!claims && !maps && !parent.refs);
	fail_alloc = 1;
	assert(PTR_ERR(mt6878_gpueb_sram_create(&parent, &resource)) == -ENOMEM);
	fail_alloc = 0; fail_map = 1;
	assert(PTR_ERR(mt6878_gpueb_sram_create(&parent, &resource)) == -ENOMEM);
	assert(!claim_active && releases == 1 && !unmaps && !parent.refs);
	fail_map = 0;
	sram = mt6878_gpueb_sram_create(&parent, &resource);
	assert(!IS_ERR(sram) && parent.refs == 1 && claim_active);
	assert(PTR_ERR(mt6878_gpueb_sram_create(&parent, &resource)) == -EBUSY);
	assert(parent.refs == 1 && maps == 2);
	fail_alloc = 1;
	assert(PTR_ERR(mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_GPR)) == -ENOMEM);
	fail_alloc = 0;
	assert(!sram->core.clients);
	assert(PTR_ERR(mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_COUNT)) == -EINVAL);
	contenders[0].sram = contenders[1].sram = sram;
	assert(!pthread_create(&threads[0], NULL, contend, &contenders[0]));
	assert(!pthread_create(&threads[1], NULL, contend, &contenders[1]));
	assert(!pthread_join(threads[0], NULL) && !pthread_join(threads[1], NULL));
	assert(IS_ERR(contenders[0].window) != IS_ERR(contenders[1].window));
	gpr = IS_ERR(contenders[0].window) ? contenders[1].window : contenders[0].window;
	assert(PTR_ERR(IS_ERR(contenders[0].window) ? contenders[0].window : contenders[1].window) == -EBUSY);
	mbox = mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_MBOX);
	assert(!IS_ERR(mbox));
	assert(!mt6878_gpueb_sram_describe(gpr, 0, GPUEB_GPR_SIZE, &range));
	assert(range.start == GPUEB_SRAM_BASE + GPUEB_GPR_OFFSET);
	range = (struct gpueb_sram_range){ 7, 8 };
	assert(mt6878_gpueb_sram_describe(gpr, GPUEB_GPR_SIZE - 4, 8, &range) == -ERANGE);
	assert(range.start == 7 && range.size == 8);
	assert(mt6878_gpueb_sram_describe(gpr, 0, 4, NULL) == -EINVAL);
	old_releases = releases; old_unmaps = unmaps;
	assert(mt6878_gpueb_sram_destroy(sram) == -EBUSY);
	assert(releases == old_releases && unmaps == old_unmaps && parent.refs == 1);
	mt6878_gpueb_sram_put_window(gpr);
	mt6878_gpueb_sram_put_window(mbox);
	assert(!mt6878_gpueb_sram_destroy(sram));
	assert(!parent.refs && !claim_active && releases == old_releases + 1);

	sram = mt6878_gpueb_sram_create(&parent, &resource);
	assert(!IS_ERR(sram));
	gpr = mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_GPR);
	assert(!IS_ERR(gpr));
	assert(!mt6878_gpueb_sram_unknown_start(sram));
	assert(mt6878_gpueb_sram_describe(gpr, 0, 4, &range) == -ESHUTDOWN);
	assert(PTR_ERR(mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_MBOX)) == -ESHUTDOWN);
	mt6878_gpueb_sram_put_window(gpr);
	old_releases = releases; old_unmaps = unmaps;
	assert(mt6878_gpueb_sram_destroy(sram) == -EBUSY);
	assert(releases == old_releases && unmaps == old_unmaps && parent.refs == 1 && claim_active);
	/* Fixture disposal only: the real API intentionally has NO recovery/free
	 * path for this state. Dispose host mocks to keep LeakSanitizer useful. */
	free(sram->mapping);
	parent.refs--;
	claim_active = 0;
	free(sram);
}

int main(void)
{
	test_core();
	test_adapter();
	puts("GPUEB SRAM core + actual resource adapter fault/concurrency tests PASS; no MMIO");
	return 0;
}
