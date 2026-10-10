/* SPDX-License-Identifier: GPL-2.0+ */
/* Real libfdt/production publisher; allocation/cache/owner are boundary doubles. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <libfdt.h>
#include <bootm.h>
#include <lmb.h>
#include "tetris_modem_final.h"

static int which, calls, maps, frees, cleans, encoded;
static struct bootm_headers *images;
static void *original;
static struct {
	unsigned long long address;
	void *pointer;
	unsigned long size;
	int live;
} allocations[2];

int lmb_alloc_mem(int type, unsigned long align, unsigned long long *address,
		unsigned long size, unsigned long flags)
{
	int i = calls++;
	(void)type; (void)flags;
	assert(i < 2 && align == 4096 && !cleans);
	if (which == i + 1)
		return -ENOMEM;
	allocations[i].address = 0x40000000ULL + (unsigned long long)i * 0x100000;
	allocations[i].size = size;
	allocations[i].pointer = aligned_alloc(4096, size);
	assert(allocations[i].pointer);
	allocations[i].live = 1;
	*address = allocations[i].address;
	return 0;
}

void *map_sysmem(unsigned long long address, unsigned long size)
{
	int i = maps++;
	assert(i < 2 && address == allocations[i].address && size == allocations[i].size);
	if (which == i + 3)
		return NULL;
	return allocations[i].pointer;
}

void unmap_sysmem(const void *p)
{
	assert(p == allocations[0].pointer || p == allocations[1].pointer);
}

int lmb_free(unsigned long long address, unsigned long size, unsigned long flags)
{
	int i;
	(void)flags;
	for (i = 0; i < 2; i++) {
		if (allocations[i].address == address) {
			assert(allocations[i].live && allocations[i].size == size);
			allocations[i].live = 0;
			free(allocations[i].pointer);
			frees++;
			return 0;
		}
	}
	assert(0);
	return -EINVAL;
}

int tetris_modem_loaded_encode_tags(void *buffer, size_t size)
{
	assert(buffer == allocations[0].pointer && size == 65536 && !encoded);
	encoded++;
	if (which == 5)
		return -EKEYREJECTED;
	memset(buffer, 0x23, 2048);
	return 2048;
}

void flush_dcache_range(unsigned long start, unsigned long end)
{
	int i = cleans++;
	assert(i < 2 && images->ft_addr == original);
	assert(start == (unsigned long)allocations[i].pointer);
	assert(end - start == allocations[i].size);
}

static unsigned int word(const unsigned char *p)
{
	return (unsigned int)p[0] | (unsigned int)p[1] << 8 |
		(unsigned int)p[2] << 16 | (unsigned int)p[3] << 24;
}

int main(int argc, char **argv)
{
	_Alignas(8) unsigned char old[32768], before[32768];
	struct bootm_headers img;
	int parent, node, ret, length, i, saved_calls;
	const unsigned char *descriptor;
	assert(argc == 2);
	which = atoi(argv[1]);
	assert(which >= 0 && which < 10);
	memset(old, 0, sizeof(old));
	assert(!fdt_create_empty_tree(old, sizeof(old)));
	parent = fdt_add_subnode(old, 0, "reserved-memory");
	assert(parent >= 0);
	assert(!fdt_setprop_u32(old, parent, "#address-cells", 2));
	assert(!fdt_setprop_u32(old, parent, "#size-cells", 2));
	assert(!fdt_setprop(old, parent, "ranges", NULL, 0));
	node = fdt_add_subnode(old, 0, "modem");
	assert(node >= 0);
	assert(!fdt_setprop_string(old, node, "compatible", "mediatek,mddriver"));
	assert(!fdt_setprop_string(old, node, "status", "disabled"));
	if (which == 6)
		assert(!fdt_setprop(old, node, "ccci,modem_info_v2", "x", 1));
	if (which == 7)
		assert(!fdt_setprop_string(old, node, "compatible", "test,not-modem"));
	if (which == 8) {
		parent = fdt_path_offset(old, "/reserved-memory");
		assert(!fdt_setprop_u32(old, parent, "#size-cells", 1));
	}
	if (which == 9) {
		node = fdt_add_subnode(old, 0, "second-modem");
		assert(node >= 0);
		assert(!fdt_setprop_string(old, node, "compatible", "mediatek,mddriver"));
	}
	memcpy(before, old, sizeof(old));
	img.ft_addr = old;
	img.ft_len = fdt_totalsize(old);
	images = &img;
	original = old;
	ret = tetris_modem_publish_final(&img);
	if (which) {
		assert(ret < 0 && img.ft_addr == old && !cleans);
		assert(!memcmp(old, before, sizeof(old)));
		for (i = 0; i < 2; i++)
			assert(!allocations[i].live);
	} else {
		assert(!ret && img.ft_addr == allocations[1].pointer && cleans == 2 && !frees);
		assert(!memcmp(old, before, sizeof(old)));
		node = fdt_node_offset_by_compatible(img.ft_addr, -1, "mediatek,mddriver");
		descriptor = fdt_getprop(img.ft_addr, node, "ccci,modem_info_v2", &length);
		assert(descriptor && length == 32);
		assert(word(descriptor) == 0x40000000 && !word(descriptor + 4));
		assert(word(descriptor + 8) == 2048 && !word(descriptor + 12));
		assert(word(descriptor + 16) == 2 && word(descriptor + 20) == 21);
		assert(!word(descriptor + 24) && !word(descriptor + 28));
		assert(!strcmp(fdt_getprop(img.ft_addr, node, "status", NULL), "disabled"));
		assert(fdt_num_mem_rsv(img.ft_addr) == 2);
		node = fdt_path_offset(img.ft_addr, "/reserved-memory/tetris-modem-linux-tags");
		assert(node >= 0 && fdt_getprop(img.ft_addr, node, "no-map", &length) && !length);
		for (i = 2048; i < 65536; i++)
			assert(((unsigned char *)allocations[0].pointer)[i] == 0);
	}
	saved_calls = calls;
	assert(tetris_modem_publish_final(&img) == (which ? ret : -EALREADY));
	assert(calls == saved_calls);
	for (i = 0; i < 2; i++) {
		if (allocations[i].live)
			free(allocations[i].pointer); /* fixture teardown only, not production */
	}
	return 0;
}
