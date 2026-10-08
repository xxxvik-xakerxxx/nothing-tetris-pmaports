/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
typedef uint64_t u64;
#define __iomem
#define PAGE_SIZE 4096
#define U32_MAX UINT32_MAX
#define SMEM_ATTR_PADDING 4
#define SMEM_ATTR_NO_MAP 8
#define SMEM_USER_MAX 64
#define pr_info(...) ((void)0)

struct rt_smem_region_lk_fmt {
	u64 ap_phy, ap_vir;
	struct {
		int id;
		u32 ap_offset, size, align, flags, md_offset;
	} inf;
};

static struct rt_smem_region_lk_fmt *s_smem_hash_tbl[SMEM_USER_MAX];
static unsigned int calls;
static u64 mapped_base;
static u32 mapped_size;
static int fail_mapping;

static void *ccci_map_phy_addr(u64 base, u32 size)
{
	calls++;
	mapped_base = base;
	mapped_size = size;
	return fail_mapping ? NULL : (void *)(uintptr_t)0x10000000;
}

#include "smem-map-functions.h"

static void row(struct rt_smem_region_lk_fmt *r, int id, u32 offset, u32 size, u32 flags)
{
	memset(r, 0, sizeof(*r));
	r->ap_phy = 0x88000000ULL + offset;
	r->inf.id = id;
	r->inf.ap_offset = offset;
	r->inf.size = size;
	r->inf.flags = flags;
}

int main(void)
{
	struct rt_smem_region_lk_fmt table[6];
	unsigned int variant;

	/* Real stock header sizes create a 0x15fc0 gap before CCB. */
	row(&table[0], 22, 0, 0xd80000, 0x4a);
	row(&table[1], 32, 0xd80000, 0x16a040, 2);
	row(&table[2], 1, 0xeea040, 0x15fc0, SMEM_ATTR_PADDING);
	row(&table[3], 1, 0xf00000, 0x1600000, 2);
	row(&table[4], 28, 0x2500000, 0, 2);
	row(&table[5], 24, 0x2500000, 0x60000, 2);
	assert(map_phy_to_kernel(table, 6) == 0);
	assert(calls == 1 && mapped_base == 0x88d80000 && mapped_size == 0x17e0000);
	assert(table[0].ap_vir == 0);
	assert(table[3].ap_vir == 0x10180000 && table[5].ap_vir == 0x11780000);
	assert(s_smem_hash_tbl[1] == &table[3]);
	assert(s_smem_hash_tbl[28] == &table[4]);

	for (variant = 0; variant < 6; variant++) {
		calls = 0;
		row(&table[0], 1, 0, 0x1000, 0);
		row(&table[1], 2, 0x1000, 0x1000, 0);
		switch (variant) {
		case 0: table[1].ap_phy++; break;
		case 1: table[1].inf.ap_offset--; break;
		case 2: table[1].inf.size = UINT32_MAX; break;
		case 3: table[0].ap_phy++; break;
		case 4: table[1].inf.id = -1; break;
		case 5:
			table[0].inf.size = 0;
			table[1].inf.size = 0;
			break;
		}
		assert(map_phy_to_kernel(table, 2) < 0 && calls == 0);
	}
	calls = 0;
	row(&table[0], 1, 0, 0x1000, 0);
	row(&table[1], 22, 0x1000, 0x1000, SMEM_ATTR_NO_MAP);
	row(&table[2], 2, 0x2000, 0x1000, 0);
	assert(map_phy_to_kernel(table, 3) == 0 && calls == 2);
	assert(mapped_base == 0x88002000 && mapped_size == 0x1000);
	fail_mapping = 1;
	table[0].ap_vir = 0;
	assert(map_phy_to_kernel(table, 3) < 0 && table[0].ap_vir == 0);
	puts("PASS: real cache gap, empty regions, NO_MAP boundaries, malformed spans and map failure");
	return 0;
}
