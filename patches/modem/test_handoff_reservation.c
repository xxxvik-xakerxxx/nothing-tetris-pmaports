/* SPDX-License-Identifier: GPL-2.0-only */
/* CI-only Linux API boundary. Production callbacks and factory follow below. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef uint64_t u64;
typedef uint8_t u8;
typedef uint32_t u32;
struct arm_smccc_res { unsigned long a0, a1, a2, a3; };
struct module { int unused; };
#define THIS_MODULE NULL
#define EXPORT_SYMBOL_GPL(symbol)
#define MODULE_LICENSE(license)
#define CONFIG_MODULES 1
static int CONFIG_OF_DYNAMIC;
#define IS_ENABLED(config) (config)
#define GFP_KERNEL 0
#define IORESOURCE_MEM 0x200
#define check_add_overflow(a, b, out) __builtin_add_overflow((a), (b), (out))
struct resource { u64 start, end; unsigned long flags; };
struct reserved_mem { u64 base, size; void *ops; };
struct device_node {
	const char *full_name;
	struct device_node *parent;
	struct reserved_mem *reserved;
	struct resource resource;
	int refs, resource_error, reg_cells, address_cells, size_cells;
	bool available, no_map, reusable, extra;
};
static int allocations, claim_calls, release_calls, fail_claim, claims_live;
static bool fail_alloc;
static struct resource claims[2];
static struct device_node root, rom, smem;
static struct reserved_mem rom_mem, smem_mem;
static void *kzalloc(size_t size, int flags)
{
	(void)flags;
	if (fail_alloc)
		return NULL;
	void *p = calloc(1, size);
	if (p)
		allocations++;
	return p;
}
static void kfree(void *p)
{
	if (p) {
		allocations--;
		free(p);
	}
}
static struct device_node *of_node_get(struct device_node *n)
{
	if (n)
		n->refs++;
	return n;
}
static void of_node_put(struct device_node *n)
{
	if (n)
		n->refs--;
}
static struct device_node *of_get_parent(struct device_node *n)
{
	return of_node_get(n->parent);
}
static bool of_device_is_available(struct device_node *n) { return n->available; }
static bool of_property_read_bool(struct device_node *n, const char *key)
{
	return !strcmp(key, "no-map") ? n->no_map : n->reusable;
}
static struct reserved_mem *of_reserved_mem_lookup(struct device_node *n)
{
	return n->reserved;
}
static int of_n_addr_cells(struct device_node *n) { return n->address_cells; }
static int of_n_size_cells(struct device_node *n) { return n->size_cells; }
static int of_property_count_u32_elems(struct device_node *n, const char *key)
{
	assert(!strcmp(key, "reg"));
	return n->reg_cells;
}
static int of_address_to_resource(struct device_node *n, int index, struct resource *r)
{
	if (n->resource_error)
		return n->resource_error;
	if (index && !n->extra)
		return -EINVAL;
	*r = n->resource;
	return 0;
}
static struct resource *request_mem_region(u64 base, u64 size, const char *name)
{
	(void)name;
	claim_calls++;
	if (claim_calls == fail_claim)
		return NULL;
	assert(claims_live < 2);
	struct resource *r = &claims[claims_live++];
	r->start = base;
	r->end = base + size - 1;
	return r;
}
static void release_mem_region(u64 base, u64 size)
{
	assert(claims_live > 0);
	struct resource *r = &claims[claims_live - 1];
	assert(r->start == base && r->end == base + size - 1);
	claims_live--;
	release_calls++;
}
/* PRODUCTION_INSERT */
static void setup(void)
{
	assert(!allocations && !claims_live);
	claim_calls = release_calls = fail_claim = 0;
	fail_alloc = false;
	CONFIG_OF_DYNAMIC = 0;
	root = (struct device_node){ .full_name = "/reserved-memory" };
	rom_mem = (struct reserved_mem){ .base = 0x80000000, .size = 0x10000 };
	smem_mem = (struct reserved_mem){ .base = 0x90000000, .size = 0x20000 };
	rom = (struct device_node){ .full_name = "/reserved-memory/rom@80000000",
		.parent = &root, .reserved = &rom_mem, .available = true, .no_map = true,
		.reg_cells = 4, .address_cells = 2, .size_cells = 2,
		.resource = { 0x80000000, 0x8000ffff, IORESOURCE_MEM } };
	smem = rom;
	smem.full_name = "/reserved-memory/smem@90000000";
	smem.reserved = &smem_mem;
	smem.resource = (struct resource){ 0x90000000, 0x9001ffff, IORESOURCE_MEM };
}
static void rejected(int expected)
{
	u8 digest[32] = { 1 };
	struct mt6878_md_handoff_reservation *owner = (void *)1;
	assert(mt6878_md_handoff_reserve(&rom, &smem, digest, &owner) == expected);
	assert(!owner && !allocations && !claims_live);
	assert(!root.refs && !rom.refs && !smem.refs);
}
int main(void)
{
	u8 digest[32] = { 1 };
	struct mt6878_md_handoff_reservation *owner;
	struct mt6878_md_handoff_state state, saved;
	setup();
	assert(mt6878_md_handoff_reserve(&rom, &rom, digest, &owner) == -EINVAL);
	assert(!owner);
	assert(mt6878_md_handoff_reserve(&rom, &smem, NULL, &owner) == -EINVAL);
	assert(!owner);
	assert(mt6878_md_handoff_reserve(&rom, &smem, digest, NULL) == -EINVAL);
	setup(); fail_alloc = true; rejected(-ENOMEM);
	setup(); CONFIG_OF_DYNAMIC = 1; rejected(-EOPNOTSUPP);
	setup(); rom.available = false; rejected(-ENODEV);
	setup(); rom.parent = NULL; rejected(-EINVAL);
	setup(); root.full_name = "/other"; rejected(-EINVAL);
	setup(); rom.no_map = false; rejected(-EINVAL);
	setup(); smem.reusable = true; rejected(-EINVAL);
	setup(); rom.reg_cells = -EINVAL; rejected(-EINVAL);
	setup(); smem.reg_cells = 8; rejected(-EINVAL);
	setup(); rom.address_cells = 3; rejected(-EINVAL);
	setup(); rom.size_cells = 0; rejected(-EINVAL);
	setup(); rom.reserved = NULL; rejected(-EOPNOTSUPP);
	setup(); smem_mem.ops = (void *)1; rejected(-EOPNOTSUPP);
	setup(); rom.resource_error = -EIO; rejected(-EIO);
	setup(); rom.extra = true; rejected(-EINVAL);
	setup(); rom.resource.flags = 0; rejected(-EINVAL);
	setup(); rom.resource.end = rom.resource.start - 1; rejected(-EINVAL);
	setup(); rom_mem.size = 0; rejected(-EINVAL);
	setup(); rom_mem.base = UINT64_MAX - 1; rom_mem.size = 4; rejected(-EINVAL);
	setup(); rom_mem.base++; rejected(-ESTALE);
	setup(); rom_mem.size--; rejected(-ESTALE);
	setup(); smem_mem = rom_mem; smem.resource = rom.resource; rejected(-EINVAL);
	setup(); fail_claim = 1; rejected(-EBUSY); assert(!release_calls);
	setup(); fail_claim = 2; rejected(-EBUSY); assert(release_calls == 1);
	setup();
	assert(!mt6878_md_handoff_reserve(&rom, &smem, digest, &owner));
	assert(claims_live == 2 && allocations == 1 && rom.refs == 1 && smem.refs == 1);
	assert(!root.refs && !release_calls);
	assert(!mt6878_md_reserved_handoff_ops.snapshot(owner, &saved));
	digest[0] = 99;
	assert(saved.rom_digest[0] == 1);
	assert(mt6878_md_reserved_handoff_ops.authenticate(owner, &saved) == -ENOKEY);
	for (int i = 0; i < 5; i++) {
		state = saved;
		switch (i) {
		case 0: state.rom_base++; break;
		case 1: state.rom_size++; break;
		case 2: state.smem_base++; break;
		case 3: state.smem_size++; break;
		case 4: state.rom_digest[31]++; break;
		}
		assert(mt6878_md_reserved_handoff_ops.authenticate(owner, &state) == -ESTALE);
	}
	assert(mt6878_md_reserved_handoff_ops.snapshot(NULL, &state) == -EINVAL);
	assert(mt6878_md_reserved_handoff_ops.snapshot(owner, NULL) == -EINVAL);
	assert(mt6878_md_reserved_handoff_ops.authenticate(NULL, &saved) == -EINVAL);
	assert(mt6878_md_reserved_handoff_ops.authenticate(owner, NULL) == -EINVAL);
	assert(!mt6878_md_reserved_handoff_ops.snapshot(owner, &state));
	assert(saved.rom_base == state.rom_base && saved.rom_size == state.rom_size);
	assert(saved.smem_base == state.smem_base && saved.smem_size == state.smem_size);
	assert(!memcmp(saved.rom_digest, state.rom_digest, sizeof(state.rom_digest)));
	/* Test-only reclamation after callbacks: production has NO release path. */
	of_node_put(owner->smem_node);
	of_node_put(owner->rom_node);
	release_mem_region(state.smem_base, state.smem_size);
	release_mem_region(state.rom_base, state.rom_size);
	kfree(owner);
	assert(!allocations && !claims_live && !rom.refs && !smem.refs);
	puts("handoff reservation native fault tests PASS (AUTH never succeeds)");
	return 0;
}
