/* SPDX-License-Identifier: GPL-2.0-only */
/* GitHub-native boundary mock. Includes production bodies unchanged. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __iomem
#define GFP_KERNEL 0
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define PAGE_SIZE TEST_PAGE_SIZE
typedef unsigned long long phys_addr_t;

struct mutex { int locked; };
static void mutex_init(struct mutex *m) { m->locked = 0; }
static void mutex_lock(struct mutex *m) { assert(!m->locked); m->locked = 1; }
static void mutex_unlock(struct mutex *m) { assert(m->locked); m->locked = 0; }
static unsigned int alloc_calls, fail_alloc, live_allocs;
static void *kzalloc(size_t bytes, int flags)
{
	void *value;

	(void)flags;
	if (++alloc_calls == fail_alloc)
		return NULL;
	value = calloc(1, bytes);
	assert(value);
	live_allocs++;
	return value;
}
static void kfree(void *value)
{
	if (value) {
		assert(live_allocs);
		live_allocs--;
		free(value);
	}
}
static uint32_t get_unaligned_le32(const void *raw)
{
	const unsigned char *p = raw;

	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t get_unaligned_le64(const void *raw)
{
	const unsigned char *p = raw;

	return get_unaligned_le32(p) | (uint64_t)get_unaligned_le32(p + 4) << 32;
}
static void put32(unsigned char *p, uint32_t n)
{
	unsigned int i;

	for (i = 0; i < 4; i++)
		p[i] = (unsigned char)(n >> (i * 8));
}
static void put64(unsigned char *p, uint64_t n)
{
	put32(p, (uint32_t)n);
	put32(p + 4, (uint32_t)(n >> 32));
}

struct mock_map { uint64_t base; unsigned int size; void *pointer; };
static struct mock_map maps[8];
static unsigned int map_calls, fail_map, live_maps, unmap_calls, unmap_order[8];
static bool mapping_test;
static void *ioremap_wc(phys_addr_t base, size_t bytes)
{
	struct mock_map *map;

	assert(mapping_test && map_calls < ARRAY_SIZE(maps));
	map = &maps[map_calls++];
	map->base = base;
	map->size = (unsigned int)bytes;
	if (map_calls == fail_map)
		return NULL;
	map->pointer = malloc(bytes);
	assert(map->pointer);
	live_maps++;
	return map->pointer;
}
static void iounmap(void *pointer)
{
	unsigned int i;

	assert(pointer);
	for (i = 0; i < map_calls; i++) {
		if (maps[i].pointer == pointer) {
			assert(live_maps && unmap_calls < ARRAY_SIZE(unmap_order));
			unmap_order[unmap_calls++] = i + 1;
			maps[i].pointer = NULL;
			live_maps--;
			free(pointer);
			return;
		}
	}
	assert(!"unowned unmap");
}

static int mtk_ccci_find_args_val(const char *, unsigned char *, unsigned int);
#include "smem.c"
#include "arguments.c"

static unsigned char chk[512], nc_wire[36 * 40], cache_wire[10 * 40];
static struct tetris_smem_input input;
static unsigned int args_calls, fail_argument, short_argument, bad_count;
/* Published owners intentionally remain process-reachable, like pinned boot ownership. */
static struct tetris_smem_owner *retained[2];

static int mtk_ccci_find_args_val(const char *name, unsigned char *out, unsigned int capacity)
{
	const unsigned char *value;
	unsigned int bytes;
	unsigned char count[4];

	args_calls++;
	if (args_calls == fail_argument)
		return -EACCES;
	if (!strcmp(name, "nc_smem_layout_num")) {
		put32(count, bad_count ? 37 : input.nc_bytes / 40);
		value = count;
		bytes = 4;
	} else if (!strcmp(name, "c_smem_layout_num")) {
		put32(count, input.cache_bytes / 40);
		value = count;
		bytes = 4;
	} else if (!strcmp(name, "md1_chk")) {
		value = chk;
		bytes = sizeof(chk);
	} else if (!strcmp(name, "nc_smem_layout")) {
		value = nc_wire;
		bytes = input.nc_bytes;
	} else {
		assert(!strcmp(name, "c_smem_layout"));
		value = cache_wire;
		bytes = input.cache_bytes;
	}
	assert(bytes <= capacity);
	memcpy(out, value, bytes);
	return (int)bytes - (args_calls == short_argument ? 1 : 0);
}

static unsigned int wire_rows(unsigned char *wire, const struct tetris_modem_smem_entry *entries,
		unsigned int count, uint64_t base, unsigned int md_base)
{
	unsigned int cursor = 0, used = 0, i;

	for (i = 0; i < count; i++) {
		const struct tetris_modem_smem_entry *entry = &entries[i];
		unsigned int passes = entry->offset > cursor ? 2 : 1, pass;

		for (pass = 0; pass < passes; pass++) {
			bool pad = passes == 2 && pass == 0;
			unsigned int offset = pad ? cursor : entry->offset;
			unsigned char *row = wire + used;

			memset(row, 0, 40);
			put64(row, base + offset);
			put32(row + 16, entry->id);
			put32(row + 20, offset);
			put32(row + 24, pad ? entry->offset - cursor : entry->size);
			put32(row + 32, pad ? 4 : entry->flags);
			put32(row + 36, md_base + offset);
			used += 40;
		}
		cursor = entry->offset + entry->size;
	}
	return used;
}

static void rebuild_wire(void)
{
	struct tetris_modem_smem_inputs policy = {
		.drdi_version = word(chk + 0x190), .udc_en = word(chk + 0x184),
		.consys_size = word(chk + 0x180), .nv_cache_size = word(chk + 0x18c), .ccb_gear = 1,
	};
	struct tetris_modem_smem_plan plan;

	assert(!tetris_modem_plan_smem_b41(&policy, &plan));
	input.nc_bytes = wire_rows(nc_wire, plan.nc, 18, input.banks.nc.base, 0);
	input.cache_bytes = wire_rows(cache_wire, plan.cache, 5, input.banks.cache.base, 0x8000000);
}

static void verify_plan(const struct tetris_smem_owner *owner, bool mapped)
{
	unsigned int i;
	const struct ccci_smem_region *ccb = NULL, *raw = NULL, *monitor = NULL;

	assert(owner->span_count == 2 && owner->logical == word(chk + 172));
	assert(owner->layout.md_bank0.base_ap_view_vir == NULL);
	assert(owner->layout.md_bank4_cacheable_total.base_ap_view_vir == NULL);
	for (i = 0; i < ARRAY_SIZE(owner->rows); i++) {
		const struct tetris_smem_row *row = &owner->rows[i];

		if (row->size && !(row->flags & 8))
			assert(!!row->virtual == mapped);
		else
			assert(!row->virtual);
	}
	assert(owner->nc[25].id == SMEM_USER_MAX && owner->cache[10].id == SMEM_USER_MAX);
	for (i = 0; i < ARRAY_SIZE(owner->cache); i++) {
		const struct ccci_smem_region *region = &owner->cache[i];

		if (region->id == SMEM_USER_CCB_DHL)
			ccb = region;
		if (region->id == SMEM_USER_RAW_DHL)
			raw = region;
		if (region->id == SMEM_USER_CCB_MD_MONITOR)
			monitor = region;
		if (region->id == SMEM_USER_RAW_MD_CONSYS) {
			assert(!region->base_ap_view_vir && region->size == word(chk + 0x180));
			assert(region->flag == (SMF_NCLR_FIRST | SMF_NO_REMAP));
		}
		if (region->id == SMEM_USER_MD_POST_DUMP)
			assert(!region->size && !region->base_ap_view_vir);
	}
	assert(ccb && raw && monitor && ccb->size == 0x200000 && raw->size == 0x1400000);
	assert(monitor->base_ap_view_phy == ccb->base_ap_view_phy && monitor->size == ccb->size);
	assert(raw->base_ap_view_phy == ccb->base_ap_view_phy + 0x200000);
	if (mapped) {
		assert(raw->base_ap_view_vir == (unsigned char *)ccb->base_ap_view_vir + 0x200000);
		assert(maps[0].base == input.banks.nc.base);
		assert(maps[1].base >= input.banks.cache.base + word(chk + 0x180));
		assert(maps[0].size < input.banks.nc.capacity && maps[1].size < input.banks.cache.capacity);
		assert(!(maps[0].base & (PAGE_SIZE - 1)) && !(maps[1].base & (PAGE_SIZE - 1)));
	}
}

int main(int argc, char **argv)
{
	static const unsigned int fields[] = { 0, 8, 16, 20, 24, 28, 32, 36 };
	struct tetris_smem_owner *owner = NULL, *other = NULL;
	struct tetris_smem_slot slot;
	struct ccci_mem_layout exported, before;
	struct ccci_smem_region nc[26], cache[11];
	FILE *file;
	int which, ret;
	unsigned int i;

	assert(argc == 3);
	which = atoi(argv[1]);
	assert(which >= 0 && which < 70);
	file = fopen(argv[2], "rb");
	assert(file && fread(chk, 1, sizeof(chk), file) == sizeof(chk));
	assert(!fclose(file));
	input = (struct tetris_smem_input) {
		.chk = chk, .chk_bytes = sizeof(chk), .nc = nc_wire, .cache = cache_wire,
		.banks = {
			.firmware = { 0x80000000ULL, 0x20000000ULL },
			.nc = { 0xa0000000ULL, 0x8000000ULL },
			.cache = { 0xc0000000ULL, 0x8000000ULL },
			.tags = { 0x180000000ULL, 65536 },
		}, /* Synthetic allocations, never phone addresses. */
	};
	rebuild_wire();
	if (which >= 1 && which <= 6) {
		static const unsigned int offsets[] = { 0, 12, 16, 20, 168, 508 };

		chk[offsets[which - 1]] ^= 1;
	}
	if (which == 7)
		input.chk_bytes--;
	if (which == 8)
		put32(chk + 0x190, 2);
	if (which == 9)
		put32(chk + 0x184, 1);
	if (which == 10)
		put32(chk + 0x180, 0);
	if (which == 11)
		put32(chk + 0x18c, 0xffffffffU);
	if (which == 14)
		input.nc = NULL;
	if (which == 15)
		input.nc_bytes -= 40;
	if (which == 16)
		input.cache_bytes--;
	if (which >= 17 && which <= 24)
		nc_wire[fields[which - 17]] ^= 1;
	if (which >= 25 && which <= 32)
		cache_wire[fields[which - 25]] ^= 1;
	if (which == 33) {
		bool found = false;

		for (i = 0; i < input.nc_bytes; i += 40) {
			if (word(nc_wire + i + 32) == 4) {
				nc_wire[i + 32] = 1;
				found = true;
				break;
			}
		}
		assert(found);
	}
	if (which == 34)
		put32(nc_wire + 40 + 16, word(nc_wire + 16));
	if (which == 35)
		input.banks.firmware.capacity -= 0x2000000;
	if (which == 36)
		input.banks.nc.capacity--;
	if (which == 37)
		input.banks.cache.capacity--;
	if (which == 38)
		input.banks.tags.capacity--;
	if (which == 39)
		input.banks.nc.base = input.banks.firmware.base + 0x1e000000;
	if (which == 40)
		input.banks.cache.base++;
	if (which == 41)
		input.banks.tags.base = ~0ULL - 4095;
	if (which == 42 || which == 58)
		fail_alloc = 1;
	if (which == 61)
		fail_alloc = 2;
	if (which == 59) {
		input.banks.firmware.base = 0x100000000ULL;
		input.banks.nc.base = 0x120000000ULL;
		input.banks.cache.base = 0x140000000ULL;
		rebuild_wire();
	}
	if (which == 62) {
		put32(chk + 0x180, 0x10001);
		rebuild_wire();
	}
	if (which == 66)
		put32(cache_wire + 16, 46);
	if (which == 67)
		put32(chk + 172, 0x20000001);
	if (which >= 52 && which <= 56)
		fail_argument = (unsigned int)which - 51;
	if (which == 57)
		short_argument = 4;
	if (which == 60)
		bad_count = 1;
	if (which == 12)
		ret = tetris_smem_create(NULL, &owner);
	else if (which == 13)
		ret = tetris_smem_create(&input, NULL);
	else if (which == 51 || (which >= 52 && which <= 58) || which == 60 || which == 61)
		ret = tetris_smem_from_arguments(&input.banks, &owner);
	else
		ret = tetris_smem_create(&input, &owner);
	if ((which >= 1 && which <= 42) || (which >= 52 && which <= 58) ||
	    which == 60 || which == 61 || which == 62 || which == 66 || which == 67) {
		assert(ret < 0 && !owner && !map_calls && !live_allocs);
		if (which >= 52 && which <= 56) {
			assert(ret == -EACCES && args_calls == fail_argument);
		}
		return 0;
	}
	assert(!ret && owner && !map_calls);
	verify_plan(owner, false);
	assert(!tetris_smem_preview(owner, &exported, nc, 26, cache, 11) && !map_calls);
	assert(!exported.md_bank0.base_ap_view_vir && !cache[2].base_ap_view_vir);
	if (which == 68) {
		assert(tetris_smem_preview(owner, &exported, nc, 26, nc, 26) == -EINVAL);
		assert(!tetris_smem_destroy(owner) && !live_maps && !live_allocs);
		return 0;
	}
	tetris_smem_slot_init(&slot);
	if (which == 45) {
		assert(tetris_smem_publish_private(&slot, owner) == -ENODATA);
		assert(!slot.owner && owner->state == TETRIS_SMEM_FAILED);
		assert(tetris_smem_map_private(owner) == -ENODATA && !map_calls);
		assert(!tetris_smem_destroy(owner));
		assert(!live_allocs);
		return 0;
	}
	if (which == 64) {
		memset(nc_wire, 0xee, sizeof(nc_wire));
		memset(cache_wire, 0xee, sizeof(cache_wire));
		/* Independent owned decoded metadata, no retained input pointers. */
		verify_plan(owner, false);
	}
	mapping_test = true;
	if (which == 43 || which == 44)
		fail_map = (unsigned int)which - 42;
	ret = tetris_smem_map_private(owner);
	if (which == 43 || which == 44) {
		assert(ret == -ENOMEM && owner->first_error == ret && !live_maps);
		assert(tetris_smem_map_private(owner) == ret && map_calls == fail_map);
		assert(tetris_smem_publish_private(&slot, owner) == ret && !slot.owner);
		assert(unmap_calls == (which == 44 ? 1U : 0U));
		if (unmap_calls)
			assert(unmap_order[0] == 1);
		assert(!tetris_smem_destroy(owner) && !live_allocs);
		return 0;
	}
	assert(!ret && map_calls == 2);
	verify_plan(owner, true);
	if (which == 47)
		assert(tetris_smem_map_private(owner) == -EALREADY && map_calls == 2);
	if (which == 65) {
		assert(!tetris_smem_destroy(owner) && !live_allocs && !live_maps);
		assert(unmap_calls == 2 && unmap_order[0] == 2 && unmap_order[1] == 1);
		return 0;
	}
	assert(!tetris_smem_publish_private(&slot, owner) && slot.owner == owner);
	retained[0] = owner;
	if (which == 46) {
		assert(!tetris_smem_create(&input, &other));
		assert(!tetris_smem_map_private(other));
		assert(tetris_smem_publish_private(&slot, other) == -EEXIST);
		assert(slot.owner == owner && other->first_error == -EEXIST && live_maps == 2);
		assert(unmap_order[0] == 4 && unmap_order[1] == 3);
		assert(tetris_smem_map_private(other) == -EEXIST && map_calls == 4);
		assert(!tetris_smem_destroy(other));
	}
	if (which == 48)
		assert(tetris_smem_publish_private(&slot, owner) == -EALREADY);
	assert(tetris_smem_destroy(owner) == -EBUSY && live_maps == 2);
	memset(&exported, 0x55, sizeof(exported));
	before = exported;
	if (which == 50) {
		assert(tetris_smem_export_private(&slot, &exported, nc, 25, cache, 11) == -EINVAL);
		assert(!memcmp(&before, &exported, sizeof(before)) && live_maps == 2);
	}
	if (which == 69) {
		assert(tetris_smem_export_private(&slot, &exported, owner->nc, 26, cache, 11) == -EINVAL);
		assert(owner->nc[0].id == SMEM_USER_RAW_DFD && live_maps == 2);
	}
	assert(!tetris_smem_export_private(&slot, &exported, nc, 26, cache, 11));
	assert(exported.md_bank4_noncacheable == nc && exported.md_bank4_cacheable == cache);
	assert(!memcmp(nc, owner->nc, sizeof(nc)) && !memcmp(cache, owner->cache, sizeof(cache)));
	nc[0].size = 0;
	assert(owner->nc[0].size == 0); /* absent DFD stays zero */
	cache[2].size = 0;
	assert(owner->cache[2].size == 0x200000); /* consumer cannot modify owner */
	assert(!unmap_calls || which == 46);
	assert(retained[0] && live_allocs == 1);
	return 0;
}
