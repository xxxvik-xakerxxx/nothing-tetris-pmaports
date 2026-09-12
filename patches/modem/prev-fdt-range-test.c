/* Host-only predicate test. No physical memory is mapped or accessed. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef uint64_t phys_addr_t;
/* Synthetic distinct encodings preserve only the predicate's type comparison. */
#define MT_NORMAL 1
#define MT_DEVICE_NGNRNE 2
#define MT_NORMAL_NC 3
#define PTE_BLOCK_MEMTYPE(x) (x)
#define PMD_ATTRINDX_MASK 3
#define PTE_BLOCK_NON_SHARE 0
#define PTE_BLOCK_OUTER_SHARE 0
#define PTE_BLOCK_INNER_SHARE 0
#define PTE_BLOCK_PXN 0
#define PTE_BLOCK_UXN 0
struct mm_region { uint64_t virt, phys, size, attrs; };
static struct { uint64_t ram_base, ram_size; } state;
#define gd (&state)

/* INSERT_ACTUAL_SOURCE */

int main(void)
{
    state.ram_base = 0x40000000ULL;
    state.ram_size = 0x80000000ULL;
    assert(is_normal_memory_range(0x40000000ULL, 40));
    assert(!is_normal_memory_range(0x3fffffffULL, 40));
    assert(is_normal_memory_range(0x66efffd8ULL, 40));
    assert(!is_normal_memory_range(0x66efffd9ULL, 40));
    assert(!is_normal_memory_range(0x66f00000ULL, 40));
    assert(is_normal_memory_range(0x70000000ULL, 40));
    assert(!is_normal_memory_range(0x78000000ULL, 40));
    assert(is_normal_memory_range(0x7ffff000ULL, 40));
    assert(is_normal_memory_range(0xbfffffd8ULL, 40));
    assert(!is_normal_memory_range(0xbfffffd9ULL, 40));
    assert(!is_normal_memory_range(0xc0000000ULL, 40));
    /* Larger synthetic DRAM admits that same map range, not reserved holes. */
    state.ram_size = 0xc0000000ULL;
    assert(is_normal_memory_range(0xc0000000ULL, 40));
    assert(!is_normal_memory_range(0xfe0d0000ULL, 40));
    assert(!is_normal_memory_range(0x40000000ULL, 0));
    assert(!is_normal_memory_range(UINT64_MAX - 20, 40));
    state.ram_size = 0;
    assert(!is_normal_memory_range(0x40000000ULL, 40));
    state.ram_base = UINT64_MAX - 20;
    state.ram_size = 40;
    assert(!is_normal_memory_range(UINT64_MAX - 20, 1));
    puts("previous-FDT actual range predicate: 17 boundary cases passed");
    return 0;
}
