/* SPDX-License-Identifier: GPL-2.0-only */
/* CI-only real OF adapter with mocked DT/rmem boundary; no hardware mapping. */
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include "metadata_resources.h"
typedef uint8_t u8;
typedef uint64_t u64;
typedef uint64_t phys_addr_t;
#define U64_MAX UINT64_MAX
#define PAGE_SHIFT 12
#define PAGE_SIZE (1ULL << PAGE_SHIFT)
#define IORESOURCE_MEM 0x200UL
#define IORESOURCE_SYSTEM_RAM (IORESOURCE_MEM | 0x1000000UL)
#define IORESOURCE_BUSY 0x80000000UL
#define IORES_DESC_NONE 0
struct resource { u64 start, end; unsigned long flags; struct resource *parent; };
static struct resource iomem_resource;
enum { ROOT, PARENT, FW, NC, CACHE, TAGS, FOREIGN, SIB, DRAM, NODE_COUNT };
struct device_node {
	bool present, no_map, reusable, compatible, have_reg, have_ranges, have_rmem;
	int refs, cells, reg_length, no_map_length, ranges_length;
	u8 reg[64], addr_cells[4], size_cells[4];
};
struct reserved_mem { u64 base, size; };
struct property { int unused; };
static struct device_node nodes[NODE_COUNT];
static struct reserved_mem reservations[NODE_COUNT];
static struct property property;
static int live_mode, live_node;
static unsigned long cleared_pfn;
static bool have_cleared_pfn;
static int pfn_is_map_memory(unsigned long pfn)
{
	return have_cleared_pfn && pfn == cleared_pfn;
}
static int walk_iomem_res_desc(unsigned long desc, unsigned long flags, u64 start,
		u64 end, void *data, int (*callback)(struct resource *, void *))
{
	struct resource resource = { start, end, IORESOURCE_MEM, &iomem_resource };
	int which = -1, ret;
	assert(desc == IORES_DESC_NONE && flags == IORESOURCE_MEM);
	for (int i = FW; i <= TAGS; i++) {
		if (start == reservations[i].base)
			which = i;
	}
	assert(which >= FW);
	if (which != live_node)
		return callback(&resource, data);
	if (live_mode == 1) { /* retained entry, but init cleared NOMAP before resources */
		resource.flags = IORESOURCE_SYSTEM_RAM | IORESOURCE_BUSY;
		return callback(&resource, data);
	}
	if (live_mode == 2)
		return -EINVAL; /* no real resource; PFN negative is merely a hole */
	if (live_mode == 3) {
		resource.end -= PAGE_SIZE; /* uncovered reservation tail */
		return callback(&resource, data);
	}
	if (live_mode == 4 || live_mode == 6) {
		u64 middle = start + (end - start + 1) / 2;
		resource.end = middle - 1;
		ret = callback(&resource, data);
		if (ret)
			return ret;
		resource.start = middle + (live_mode == 4 ? PAGE_SIZE : 0);
		resource.end = end;
		return callback(&resource, data);
	}
	if (live_mode == 5)
		resource.parent = &resource; /* child of a resource, not top-level NOMAP */
	return callback(&resource, data);
}
static void put64(u8 *p, u64 value)
{
	for (unsigned int i = 0; i < 8; i++)
		p[i] = (u8)(value >> (56 - 8 * i));
}
static u64 get_unaligned_be64(const void *p)
{
	const u8 *b = p;
	u64 value = 0;
	for (unsigned int i = 0; i < 8; i++)
		value = (value << 8) | b[i];
	return value;
}
static uint32_t get_unaligned_be32(const void *p)
{
	const u8 *b = p;
	return (uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 |
		(uint32_t)b[2] << 8 | b[3];
}
static void of_node_put(struct device_node *node)
{
	if (node) {
		assert(node->refs > 0);
		node->refs--;
	}
}
static struct device_node *get_node(unsigned int id)
{
	if (!nodes[id].present)
		return NULL;
	nodes[id].refs++;
	return &nodes[id];
}
static struct device_node *of_find_node_by_path(const char *path)
{
	static const char * const paths[] = {
		"/", "/reserved-memory", "/reserved-memory/tetris-modem-diagnostic",
		"/reserved-memory/tetris-modem-boot-nc", "/reserved-memory/tetris-modem-boot-cache",
		"/reserved-memory/tetris-modem-linux-tags", "/reserved-memory/other",
		"/reserved-memory/tetris-modem-boot-sib", "/memory",
	};
	for (unsigned int i = 0; i < NODE_COUNT; i++) {
		if (!strcmp(paths[i], path))
			return get_node(i);
	}
	return NULL;
}
static const struct property *of_find_property(const struct device_node *node,
		const char *key, int *length)
{
	if (!node)
		return NULL;
	if (!strcmp(key, "reg") && node->have_reg) {
		if (length)
			*length = node->reg_length;
		return &property;
	}
	if (!strcmp(key, "no-map") && node->no_map) {
		*length = node->no_map_length;
		return &property;
	}
	if (!strcmp(key, "reusable") && node->reusable)
		return &property;
	if (!strcmp(key, "compatible") && node->compatible)
		return &property;
	if (!strcmp(key, "ranges") && node->have_ranges) {
		*length = node->ranges_length;
		return &property;
	}
	return NULL;
}
static const void *of_get_property(const struct device_node *node,
		const char *key, int *length)
{
	if (!node)
		return NULL;
	if (!strcmp(key, "reg") && node->have_reg) {
		*length = node->reg_length;
		return node->reg_length ? node->reg : NULL;
	}
	if (!strcmp(key, "#address-cells")) {
		*length = 4;
		return node->addr_cells;
	}
	if (!strcmp(key, "#size-cells")) {
		*length = 4;
		return node->size_cells;
	}
	return NULL;
}
static int of_n_addr_cells(const struct device_node *node) { return node->cells; }
static int of_n_size_cells(const struct device_node *node) { return node->cells; }
static struct reserved_mem *of_reserved_mem_lookup(const struct device_node *node)
{
	return node->have_rmem ? &reservations[node - nodes] : NULL;
}
static struct device_node *next_child(const struct device_node *parent,
		struct device_node *previous)
{
	unsigned int first = previous ? (unsigned int)(previous - nodes) + 1 : FW;
	assert(parent == &nodes[PARENT]);
	of_node_put(previous);
	for (unsigned int i = first; i <= SIB; i++) {
		if (nodes[i].present)
			return get_node(i);
	}
	return NULL;
}
static struct device_node *next_memory(struct device_node *previous, const char *type)
{
	assert(!strcmp(type, "memory"));
	if (previous) {
		of_node_put(previous);
		return NULL;
	}
	return get_node(DRAM);
}
#define for_each_child_of_node(parent, child) \
	for ((child) = next_child((parent), NULL); (child); (child) = next_child((parent), (child)))
#define for_each_node_by_type(node, type) \
	for ((node) = next_memory(NULL, (type)); (node); (node) = next_memory((node), (type)))
/* OF_ADAPTER */
static void bank(unsigned int id, u64 base, u64 capacity)
{
	put64(nodes[id].reg, base);
	put64(nodes[id].reg + 8, capacity);
	reservations[id] = (struct reserved_mem){ base, capacity };
}
int main(void)
{
	for (unsigned int fault = 0; fault < 53; fault++) {
		struct tetris_metadata_banks out, untouched;
		int ret;

		memset(nodes, 0, sizeof(nodes));
		live_mode = 0;
		live_node = TAGS;
		have_cleared_pfn = false;
		for (unsigned int i = 0; i < NODE_COUNT; i++) {
			nodes[i].present = true;
			nodes[i].no_map = true;
			nodes[i].have_reg = true;
			nodes[i].have_ranges = true;
			nodes[i].have_rmem = true;
			nodes[i].reg_length = 16;
			nodes[i].cells = 2;
			nodes[i].addr_cells[3] = nodes[i].size_cells[3] = 2;
		}
		nodes[SIB].present = false;
		nodes[FOREIGN].present = false;
		bank(FW, 0x80000000, 0x20000000);
		bank(NC, 0xa0000000, 0x8000000);
		bank(CACHE, 0xc0000000, 0x8000000);
		bank(TAGS, 0x180000000ULL, 65536);
		bank(DRAM, 0x40000000, 0x180000000ULL);
		if (fault == 1) nodes[NC].present = false;
		if (fault == 2) nodes[NC].no_map = false;
		if (fault == 3) nodes[FW].no_map_length = 4;
		if (fault == 4) nodes[CACHE].reusable = true;
		if (fault == 5) nodes[FW].reg_length = 32;
		if (fault == 6) nodes[FW].have_rmem = false;
		if (fault == 7) reservations[NC].base++;
		if (fault == 8) reservations[CACHE].size--;
		if (fault == 9) nodes[FW].cells = 1;
		if (fault == 10) nodes[PARENT].ranges_length = 16;
		if (fault == 11) bank(FW, 0x80000000, 0x1e000000);
		if (fault == 12) bank(NC, 0xa0000001, 0x8000000);
		if (fault == 13) bank(CACHE, 0xa6000000, 0x8000000);
		if (fault == 14) {
			nodes[FOREIGN].present = true;
			bank(FOREIGN, 0x9e000000, 0x10000);
		}
		if (fault == 15) bank(DRAM, 0x80000000, 0x1e000000);
		if (fault == 16) {
			nodes[DRAM].reg_length = 32;
			bank(DRAM, 0x80000000, 0x10000000);
			put64(nodes[DRAM].reg + 16, 0x90000000);
			put64(nodes[DRAM].reg + 24, 0x10000000);
		}
		if (fault == 17) nodes[DRAM].reg_length = 15;
		if (fault == 18) {
			nodes[SIB].present = true;
			bank(SIB, 0x160000000ULL, 65536);
		}
		if (fault == 19) nodes[ROOT].addr_cells[3] = 1;
		if (fault == 20) {
			nodes[FOREIGN].present = true;
			bank(FOREIGN, UINT64_MAX - 1, 16);
		}
		if (fault == 21) nodes[TAGS].present = false;
		if (fault == 22) bank(FW, 0, 0x20000000);
		if (fault == 23) bank(NC, 1ULL << 35, 0x8000000);
		if (fault == 24) {
			nodes[FOREIGN].present = true;
			bank(FOREIGN, 0x200000000ULL, 0);
		}
		if (fault == 25) nodes[FW].present = false;
		if (fault == 26) bank(CACHE, 0xc0000000, 0x7ff0000);
		if (fault == 27) nodes[PARENT].have_ranges = false;
		if (fault == 28) {
			nodes[FOREIGN].present = true;
			nodes[FOREIGN].reg_length = 17;
		}
		if (fault == 29) {
			nodes[FOREIGN].present = true;
			nodes[FOREIGN].reg_length = 0;
		}
		if (fault == 30) { /* legitimate dynamic reserved node; no static reg */
			nodes[FOREIGN].present = true;
			nodes[FOREIGN].have_reg = false;
		}
		if (fault == 31) { /* MD shares one bank; independent AP tag bank */
			bank(DRAM, 0x80000000, 0x50000000);
			nodes[DRAM].reg_length = 32;
			put64(nodes[DRAM].reg + 16, 0x180000000ULL);
			put64(nodes[DRAM].reg + 24, 65536);
		}
		if (fault == 32) { /* each full window fits, but MD has no common bank */
			bank(DRAM, 0x80000000, 0x20000000);
			nodes[DRAM].reg_length = 48;
			put64(nodes[DRAM].reg + 16, 0xa0000000);
			put64(nodes[DRAM].reg + 24, 0x28000000);
			put64(nodes[DRAM].reg + 32, 0x180000000ULL);
			put64(nodes[DRAM].reg + 40, 65536);
		}
		if (fault >= 33 && fault <= 36)
			nodes[FW + fault - 33].compatible = true;
		if (fault >= 37 && fault <= 40) {
			/* Failed-init survivor: DT no-map and matching catalogue remain.
			 * Suppress compatible in this boundary to independently exercise
			 * the retained-state guard, not only the new compatible rejection.
			 */
			live_node = FW + (int)fault - 37;
			live_mode = 1;
			have_cleared_pfn = true;
			cleared_pfn = (unsigned long)(reservations[live_node].base >> PAGE_SHIFT);
		}
		if (fault >= 41 && fault <= 44) {
			/* Later clear: retained NOMAP resource is stale; middle PFN maps. */
			unsigned int id = FW + fault - 41;
			have_cleared_pfn = true;
			cleared_pfn = (unsigned long)((reservations[id].base + reservations[id].size / 2) >> PAGE_SHIFT);
		}
		if (fault >= 45 && fault <= 48) {
			live_node = TAGS;
			live_mode = (int)fault - 43; /* absent/prefix/gap/child resource */
		}
		if (fault == 49) {
			live_node = TAGS;
			live_mode = 1;
		}
		if (fault == 50) {
			live_node = TAGS;
			live_mode = 6; /* adjacent NOMAP spans provide complete coverage */
		}
		if (fault == 51 || fault == 52) {
			have_cleared_pfn = true;
			cleared_pfn = (unsigned long)((reservations[TAGS].base + reservations[TAGS].size) >> PAGE_SHIFT);
			if (fault == 51)
				cleared_pfn--; /* reject last page, not merely first/middle */
		}
		memset(&out, 0xa5, sizeof(out));
		untouched = out;
		ret = tetris_owned_banks(&out);
		if (fault && fault != 30 && fault != 31 && fault != 50 && fault != 52)
			assert(ret < 0 && !memcmp(&out, &untouched, sizeof(out)));
		else
			assert(!ret && out.firmware.capacity == 0x20000000 && out.tags.base == 0x180000000ULL);
		for (unsigned int i = 0; i < NODE_COUNT; i++)
			assert(nodes[i].refs == 0);
	}
	return 0;
}
