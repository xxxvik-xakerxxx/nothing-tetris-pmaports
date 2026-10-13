// SPDX-License-Identifier: GPL-2.0-only
/* CI-only actual C API tests with synthetic allocator history; no real DMA. */
#include "mt6878-gpueb-dram.c"
#include <stdio.h>

static struct cma area, foreign_area;
static struct cma *selected_area;
static struct page allocation;
static struct device parent, foreign_parent;
static struct mt6878_gpueb_dram *held;
static struct mt6878_gpueb_dram *created;
static unsigned int allocations, releases, owned;
static int absent_area, allocation_failure, release_failure, metadata_failure;

static void *kzalloc(size_t bytes, int flags)
{
    void *pointer;
    assert(flags == GFP_KERNEL);
    if (metadata_failure) return NULL;
    pointer = calloc(1, bytes);
    if (pointer && bytes == sizeof(*created)) { assert(!created); created = pointer; }
    return pointer;
}
static void kfree(void *ptr)
{
    if (ptr == created) {
        assert(!pthread_mutex_destroy(&created->lock.value));
        created = NULL;
    }
    free(ptr);
}
static struct cma *dev_get_cma_area(struct device *device)
{ assert(device == &parent); return absent_area ? NULL : selected_area; }
static struct page *cma_alloc(struct cma *source, unsigned long count,
                            unsigned int align, bool no_warn)
{
    assert(source == &area && count == 1536 && align == 4 && !no_warn && !owned);
    allocations++;
    if (allocation_failure) return NULL;
    owned = 1; return &allocation;
}
static bool cma_release(struct cma *source, const struct page *page, unsigned long count)
{
    assert(source == &area && page == &allocation && count == 1536 && owned);
    releases++;
    if (release_failure) return false;
    owned = 0; return true;
}
static void setup(void)
{
    assert(!created && !owned && !parent.refs && !foreign_parent.refs);
    held = NULL; allocations = releases = 0;
    absent_area = allocation_failure = release_failure = metadata_failure = 0;
    allocation.fixture_physical = 0x60000000ULL;
    selected_area = &area;
}
int main(void)
{
    struct mt6878_gpueb_dram_loan *loan;
    u32 word;
    unsigned int i;
    const phys_addr_t invalid[] = { 0, 0x3fff0000ULL, 0x60001000ULL,
                                   0x7fa10000ULL, 0x80000000ULL, ~(phys_addr_t)0 };
    setup();
    assert(mt6878_gpueb_dram_create(NULL, &held) == -EINVAL && !allocations);
    assert(mt6878_gpueb_dram_create(&parent, NULL) == -EINVAL && !allocations);
    absent_area = 1;
    assert(mt6878_gpueb_dram_create(&parent, &held) == -ENODEV && !held && !parent.refs);
    setup(); metadata_failure = 1;
    assert(mt6878_gpueb_dram_create(&parent, &held) == -ENOMEM && !held && !allocations);
    setup(); allocation_failure = 1;
    assert(mt6878_gpueb_dram_create(&parent, &held) == -ENOMEM && !held && !owned && !parent.refs);
    for (i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
        setup(); allocation.fixture_physical = invalid[i];
        assert(mt6878_gpueb_dram_create(&parent, &held) == -ERANGE && !held);
        assert(allocations == 1 && releases == 1 && !owned && !parent.refs);
    }
    setup();
    allocation.fixture_physical = 0x80000000ULL; release_failure = 1;
    assert(mt6878_gpueb_dram_create(&parent, &held) == -EIO && held);
    assert(held->first_error == -ERANGE && owned && parent.refs == 1);
    assert(PTR_ERR(mt6878_gpueb_dram_acquire(held, &parent)) == -ERANGE);
    metadata_failure = 1;
    assert(PTR_ERR(mt6878_gpueb_dram_acquire(held, &parent)) == -ERANGE);
    assert(mt6878_gpueb_dram_destroy(held) == -EIO && held->first_error == -ERANGE);
    metadata_failure = release_failure = 0;
    assert(!mt6878_gpueb_dram_destroy(held) && !owned && !parent.refs);
    setup(); assert(!mt6878_gpueb_dram_create(&parent, &held));
    assert(held && owned && parent.refs == 1);
    assert(mt6878_gpueb_dram_create(&parent, &held) == -EINVAL && allocations == 1);
    assert(PTR_ERR(mt6878_gpueb_dram_acquire(held, &foreign_parent)) == -ENODEV);
    metadata_failure = 1;
    assert(PTR_ERR(mt6878_gpueb_dram_acquire(held, &parent)) == -ENOMEM);
    metadata_failure = 0;
    loan = mt6878_gpueb_dram_acquire(held, &parent); assert(!IS_ERR(loan));
    assert(PTR_ERR(mt6878_gpueb_dram_acquire(held, &parent)) == -EBUSY);
    assert(mt6878_gpueb_dram_destroy(held) == -EBUSY && owned && !releases);
    word = 0;
    assert(!mt6878_gpueb_dram_candidate_gpr6(loan, &word) && word == 0x60000);
    assert(mt6878_gpueb_dram_candidate_gpr6(loan, NULL) == -EINVAL);
    allocation.fixture_physical += 0x10000;
    word = 0xa5a5a5a5;
    assert(mt6878_gpueb_dram_candidate_gpr6(loan, &word) == -ESTALE && word == 0xa5a5a5a5);
    allocation.fixture_physical -= 0x10000;
    /* Release uses its saved real allocation area, not a new device selector. */
    selected_area = &foreign_area;
    mt6878_gpueb_dram_put(loan);
    release_failure = 1;
    assert(mt6878_gpueb_dram_destroy(held) == -EIO && owned && parent.refs == 1);
    assert(PTR_ERR(mt6878_gpueb_dram_acquire(held, &parent)) == -EIO);
    /* Mock allocator recovery only. There has been NO hardware publication. */
    release_failure = 0;
    assert(!mt6878_gpueb_dram_destroy(held) && !owned && !parent.refs);
    setup(); allocation.fixture_physical = 0x7fa00000ULL;
    assert(!mt6878_gpueb_dram_create(&parent, &held) && held);
    loan = mt6878_gpueb_dram_acquire(held, &parent); assert(!IS_ERR(loan));
    assert(!mt6878_gpueb_dram_candidate_gpr6(loan, &word) && word == 0x7fa00);
    mt6878_gpueb_dram_put(loan); assert(!mt6878_gpueb_dram_destroy(held));
    puts("PASS: actual private DRAM allocator/loan faults; no GPR or firmware execution");
    return 0;
}
