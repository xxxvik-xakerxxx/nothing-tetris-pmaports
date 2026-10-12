/* SPDX-License-Identifier: GPL-2.0-only */
/* Boundary fixture: actual vendor types, private owner and copy-layout bodies. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <asm-generic/errno.h>
#define __iomem
#define GFP_KERNEL 0
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define IS_ENABLED(config) (config)
#define EXPORT_SYMBOL_GPL(name)
typedef uint64_t phys_addr_t;
struct mutex { bool held; };
static void mutex_lock(struct mutex *lock) { assert(!lock->held); lock->held = true; }
static void mutex_unlock(struct mutex *lock) { assert(lock->held); lock->held = false; }
#include "private.h"
#include "mt-plat/tetris_ccci_smem.h"
struct module { int refs; };
static struct module provider = { 1 };
#define THIS_MODULE (&provider)
static bool pin_fail, alloc_fail;
static int live_copies, export_fault;
static bool try_module_get(struct module *module)
{
	assert(module == &provider);
	if (pin_fail)
		return false;
	module->refs++;
	return true;
}
static void module_put(struct module *module)
{
	assert(module == &provider && module->refs > 1);
	module->refs--;
}
static void *kzalloc(size_t size, int flags)
{
	(void)flags;
	assert(size == sizeof(struct tetris_ccci_smem_copy));
	if (alloc_fail)
		return NULL;
	live_copies++;
	return calloc(1, size);
}
static void kfree(void *memory)
{
	assert(memory && live_copies == 1);
	live_copies--;
	free(memory);
}
static struct tetris_smem_owner owner;
static struct { struct tetris_smem_owner *owner; } tetris_owned_smem_plan;
/* REAL_EXPORT */

/* Rename only the fixture's provider entry to inject malformed provider output;
 * all successful/failed copies still execute the unchanged real provider body.
 */
#define mtk_ccci_owned_mapped_copy test_real_provider_copy
#include "provider.h"
#undef mtk_ccci_owned_mapped_copy

int mtk_ccci_owned_mapped_copy(struct tetris_ccci_smem_copy *out)
{
	int ret = test_real_provider_copy(out);

	if (ret)
		return ret;
	switch (export_fault) {
	case 1: out->layout.md_bank0.base_ap_view_vir = (void *)1; break;
	case 2: out->layout.md_bank4_noncacheable = owner.nc; break;
	case 3: out->cache[0].base_ap_view_vir = (void *)1; break;
	case 4: out->nc[25].id = 0; break;
	case 5: out->layout.md_bank4_cacheable_total.base_ap_view_vir = (void *)1; break;
	case 6: out->cache[0].flag = 0; break;
	}
	return 0;
}
struct ccci_modem {
	struct ccci_mem_layout mem_layout;
	struct tetris_ccci_smem_copy *tetris_smem;
};
#include "consumer.h"

static void unchanged_failure(int expected, struct tetris_ccci_smem_copy *copy)
{
	struct tetris_ccci_smem_copy before = *copy;

	assert(test_real_provider_copy(copy) == expected);
	assert(!memcmp(copy, &before, sizeof(before)) && provider.refs == 1);
}

int main(void)
{
	struct tetris_ccci_smem_copy copy = { 0 };
	struct ccci_modem md = { 0 };
	unsigned int i;

	/* Fixture addresses never map or dereference physical memory. */
	owner.state = TETRIS_SMEM_MAPPED;
	owner.layout.md_bank0.base_ap_view_phy = 0x80000000;
	owner.layout.md_bank0.size = 0x1000000;
	owner.layout.md_bank4_noncacheable_total.base_ap_view_vir = (void *)0x20000000;
	owner.layout.md_bank4_noncacheable = owner.nc;
	owner.layout.md_bank4_cacheable = owner.cache;
	owner.nc[25].id = owner.cache[10].id = SMEM_USER_MAX;
	owner.cache[0].id = SMEM_USER_RAW_MD_CONSYS;
	owner.cache[0].flag = SMF_NO_REMAP;
	assert(test_real_provider_copy(NULL) == -EINVAL);
	unchanged_failure(-ENODATA, &copy);
	tetris_owned_smem_plan.owner = &owner;
	assert(test_real_provider_copy((void *)&tetris_owned_smem_plan) == -EINVAL);
	assert(test_real_provider_copy((void *)&owner) == -EINVAL);
	copy.provider = &provider;
	unchanged_failure(-EALREADY, &copy);
	copy.provider = NULL;
	pin_fail = true;
	unchanged_failure(-ENODEV, &copy);
	pin_fail = false;
	owner.state = TETRIS_SMEM_VALIDATED;
	unchanged_failure(-EALREADY, &copy);
	owner.state = TETRIS_SMEM_FAILED;
	owner.first_error = -EIO;
	unchanged_failure(-EIO, &copy);
	owner.state = TETRIS_SMEM_MAPPED;
	owner.first_error = 0;
	assert(!test_real_provider_copy(&copy) && provider.refs == 2);
	assert(copy.layout.md_bank4_noncacheable == copy.nc);
	assert(copy.layout.md_bank4_cacheable == copy.cache);
	assert(test_real_provider_copy(&copy) == -EALREADY && provider.refs == 2);
	module_put(copy.provider);
	assert(tetris_ccci_mem_prepare(NULL) == -EINVAL);
	md.mem_layout.md_bank0.size = 1;
	assert(tetris_ccci_mem_prepare(&md) == -EEXIST && !live_copies);
	memset(&md, 0, sizeof(md));
	alloc_fail = true;
	assert(tetris_ccci_mem_prepare(&md) == -ENOMEM && !live_copies);
	alloc_fail = false;
	owner.state = TETRIS_SMEM_FAILED;
	owner.first_error = -EIO;
	assert(tetris_ccci_mem_prepare(&md) == -EIO && !live_copies && provider.refs == 1);
	owner.state = TETRIS_SMEM_MAPPED;
	owner.first_error = 0;
	pin_fail = true;
	assert(tetris_ccci_mem_prepare(&md) == -ENODEV && !live_copies && provider.refs == 1);
	pin_fail = false;
	for (i = 1; i <= 6; i++) {
		export_fault = i;
		assert(tetris_ccci_mem_prepare(&md) == -EPROTO);
		assert(!live_copies && !md.tetris_smem && provider.refs == 1);
		assert(!md.mem_layout.md_bank4_noncacheable);
	}
	export_fault = 0;
	assert(!tetris_ccci_mem_prepare(&md) && live_copies == 1 && provider.refs == 2);
	assert(md.mem_layout.md_bank4_noncacheable == md.tetris_smem->nc);
	assert(md.mem_layout.md_bank4_noncacheable != owner.nc);
	assert(!md.mem_layout.md_bank0.base_ap_view_vir);
	md.tetris_smem->nc[0].size = 123;
	assert(owner.nc[0].size == 0);
	assert(tetris_ccci_mem_prepare(&md) == -EALREADY && provider.refs == 2);
	tetris_ccci_mem_abort(&md);
	assert(!md.tetris_smem && !live_copies && provider.refs == 1);
	assert(!md.mem_layout.md_bank4_noncacheable);
	tetris_ccci_mem_abort(&md);
	assert(provider.refs == 1 && owner.state == TETRIS_SMEM_MAPPED);
	return 0;
}
