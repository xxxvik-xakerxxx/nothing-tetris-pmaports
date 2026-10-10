// SPDX-License-Identifier: GPL-2.0+
/* Fault fixtures alone construct synthetic handles. Production has no such API.
 * Actual auth/crypto code is linked separately and tested by test_native.py.
 */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include "tetris_gpueb_flat.c"
#include "tetris_gpueb_flat_publish.h"
#include <libfdt.h>

static unsigned char arena[RESERVE_BYTES] __attribute__((aligned(65536)));
static int claimed, faults;
static const struct tetris_scp_crypto_ops fixture_ops;
void *__real_malloc(size_t size);
void *__wrap_malloc(size_t size)
{
	return faults & 8 ? NULL : __real_malloc(size);
}

int lmb_alloc_mem(enum lmb_mem_type type, uint64_t align, phys_addr_t *base,
	phys_size_t size, uint32_t flags)
{
	assert(type == LMB_MEM_ALLOC_MAX && align == 65536 && size == sizeof(arena));
	assert(flags == RESERVE_FLAGS && *base == 0x80000000ULL);
	if ((faults & 1) || claimed)
		return -ENOMEM;
	claimed = 1;
	*base = 0x60000000;
	return 0;
}
long lmb_free(phys_addr_t base, phys_size_t size, uint32_t flags)
{
	assert(base == 0x60000000 && size == sizeof(arena));
	assert(flags == (RESERVE_FLAGS | LMB_NONOTIFY));
	assert(claimed);
	if (faults & 4)
		return -EIO;
	claimed = 0;
	return 0;
}
void *map_sysmem(uint64_t base, unsigned long size)
{
	assert(base == 0x60000000 && size == sizeof(arena) && claimed);
	return faults & 2 ? NULL : arena;
}
void unmap_sysmem(const void *pointer) { assert(pointer == arena); }
uint64_t map_to_sysmem(const void *pointer)
{
	return pointer == arena ? 0x60000000 : 0x50000000;
}
static void flush(void *pointer, size_t size)
{
	assert(pointer == arena && size == sizeof(arena));
}
static const struct tetris_scp_crypto_ops fixture_ops = { .flush = flush };

void fixture_reset(int fail)
{
	assert(!claimed);
	faults = fail;
	memset(arena, 0xcc, sizeof(arena));
}
void *fixture_arena(void) { return arena; }
int fixture_claimed(void) { return claimed; }
void fixture_faults(int fail) { faults = fail; }
struct tetris_gpueb_flat *fixture_image(void)
{
	struct tetris_gpueb_flat *image = calloc(1, sizeof(*image));
	assert(image && !claimed);
	claimed = 1;
	image->mapping = arena;
	image->ops = &fixture_ops;
	image->info.reserved_base = 0x60000000;
	image->info.reserved_bytes = RESERVE_BYTES;
	image->info.authenticated_bytes = FLAT_BYTES;
	memset(image->info.plaintext_sha256, 0xab, 32);
	return image;
}

int main(void)
{
	unsigned char fdt[8192], before[8192];
	struct tetris_gpueb_flat *image;
	int node, length;
	const fdt32_t *phandle;

	fixture_reset(0);
	assert(!fdt_create_empty_tree(fdt, sizeof(fdt)));
	assert(!fdt_setprop_u32(fdt, 0, "#address-cells", 2));
	assert(!fdt_setprop_u32(fdt, 0, "#size-cells", 2));
	memcpy(before, fdt, sizeof(fdt));
	image = fixture_image();
	assert(tetris_gpueb_flat_publish(&image, fdt, 48));
	assert(!image && !claimed && !memcmp(before, fdt, sizeof(fdt)));
	for (size_t i = 0; i < sizeof(arena); i++) assert(!arena[i]);

	fixture_reset(4);
	image = fixture_image();
	assert(tetris_gpueb_flat_publish(&image, fdt, 48));
	assert(image && claimed && !memcmp(before, fdt, sizeof(fdt)));
	fixture_faults(0);
	assert(!tetris_gpueb_flat_discard(image));

	fixture_reset(8);
	image = fixture_image();
	assert(tetris_gpueb_flat_publish(&image, fdt, sizeof(fdt)) == -ENOMEM);
	assert(!image && !claimed && !memcmp(before, fdt, sizeof(fdt)));

	fixture_reset(0);
	assert(!fdt_add_mem_rsv(fdt, 0x60001000, 4096));
	memcpy(before, fdt, sizeof(fdt));
	image = fixture_image();
	assert(tetris_gpueb_flat_publish(&image, fdt, sizeof(fdt)) == -EEXIST);
	assert(!image && !claimed && !memcmp(before, fdt, sizeof(fdt)));
	assert(!fdt_del_mem_rsv(fdt, 0));
	fixture_reset(0);
	{
		fdt32_t range[4] = { 0, cpu_to_fdt32(0x60000000), 0,
				    cpu_to_fdt32(RESERVE_BYTES) };
		int parent = fdt_add_subnode(fdt, 0, "reserved-memory");
		assert(parent >= 0);
		assert(!fdt_setprop_u32(fdt, parent, "#address-cells", 2));
		assert(!fdt_setprop_u32(fdt, parent, "#size-cells", 2));
		assert(!fdt_setprop(fdt, parent, "ranges", NULL, 0));
		node = fdt_add_subnode(fdt, parent, "conflict");
		assert(node >= 0);
		assert(!fdt_setprop(fdt, node, "reg", range, sizeof(range)));
		memcpy(before, fdt, sizeof(fdt));
		image = fixture_image();
		assert(tetris_gpueb_flat_publish(&image, fdt, sizeof(fdt)) == -EEXIST);
		assert(!image && !claimed && !memcmp(before, fdt, sizeof(fdt)));
		parent = fdt_path_offset(fdt, "/reserved-memory");
		assert(!fdt_del_node(fdt, parent));
	}

	fixture_reset(0);
	image = fixture_image();
	assert(!tetris_gpueb_flat_publish(&image, fdt, sizeof(fdt)));
	assert(!image && claimed);
	node = fdt_path_offset(fdt, "/gpueb-flat-analysis");
	assert(node >= 0);
	phandle = fdt_getprop(fdt, node, "memory-region", &length);
	assert(phandle && length == 4);
	node = fdt_node_offset_by_phandle(fdt, fdt32_to_cpu(*phandle));
	assert(node >= 0 && fdt_getprop(fdt, node, "no-map", &length) && !length);
	assert(!strcmp(fdt_get_name(fdt, node, NULL), "gpueb-authenticated@60000000"));
	assert(!fdt_check_full(fdt, sizeof(fdt)));
	puts("flat publication atomicity/discard/ownership fixture PASS");
	return 0;
}
