// SPDX-License-Identifier: GPL-2.0+
/* CI-only load-owner control-flow faults. Authentication/hardware boundaries
 * are MOCKED here, not substituted in production or claimed to authenticate.
 * Actual stock producer/secure calls are covered by separate fixtures.
 */
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <asm/global_data.h>
#include <linux/errno.h>
#include "tetris_modem_loaded_boot.h"
#include "tetris_modem_storage.h"
#include "tetris_modem_reserve.h"
#include "tetris_scp_security.h"

struct blk_desc { int unused; };
static struct bd_info bd = { .bi_dram = { { 0x40000000ULL, 0x100000000ULL } } };
static struct global_data data = { .bd = &bd };
struct global_data *gd = &data;
const struct tetris_scp_security_ops tetris_scp_security_hw_ops = { 0 };
static unsigned int fault, calls, loads, initialized, boots, maps, unmapped;

unsigned int current_el(void) { return fault == 1 ? 3 : 1; }
int tetris_scp_check_atf_profile(struct blk_desc *dev)
{
	assert(dev);
	calls++;
	return fault == 2 ? -EKEYREJECTED : 0;
}
unsigned int readl(const volatile void *p)
{
	uintptr_t address = (uintptr_t)p;
	calls++;
	if (address == 0x1c001e00)
		return fault == 3 ? 4 : 0;
	if (address == 0x1c001f24)
		return 3;
	if (address == 0x10001c5c)
		return 0x200;
	if (address == 0x10001c4c)
		return 0x800;
	assert(address == 0x1027008c);
	return 0xc0;
}
int tetris_modem_reserve_diagnostic_window(void *fdt, unsigned long long *base)
{
	assert(fdt);
	calls++;
	*base = 0x80000000ULL;
	return fault == 4 ? -ENOMEM : 0;
}
int tetris_modem_reserve_boot_bank(void *fdt, unsigned int role,
		unsigned long long capacity, unsigned long long *base)
{
	assert(fdt && role <= 2);
	assert(capacity == (role == 2 ? 0x100000ULL : 0x8000000ULL));
	calls++;
	*base = role == 0 ? 0xa0000000ULL : role == 1 ? 0xc0000000ULL : 0xd0000000ULL;
	return fault == role + 5 ? -ENOMEM : 0;
}
void *map_sysmem(unsigned long long base, unsigned long size)
{
	assert(size == (base == 0x80000000ULL ? 0x20000000ULL : 0x8000000ULL));
	calls++;
	maps++;
	return fault == maps + 10 ? NULL : (void *)(uintptr_t)base;
}
void unmap_sysmem(const void *p)
{
	assert(p);
	calls++;
	unmapped++;
}
void flush_dcache_range(unsigned long start, unsigned long end)
{
	assert(end > start);
	calls++;
}
int tetris_modem_load_slot_rows_b41(struct blk_desc *dev, char slot,
		const unsigned char root[32], const struct tetris_scp_security_ops *ops,
		void *destination, size_t capacity, unsigned int ccb,
		const char *phy, const unsigned char pin[32],
		const struct tetris_modem_emi_resources *resources,
		struct tetris_modem_boot_plan *plan, struct tetris_modem_emi_rows *rows)
{
	assert(dev && slot == 'a' && root[0] == 0xe1 && root[31] == 0x5e);
	assert(ops == &tetris_scp_security_hw_ops && destination == (void *)0x80000000UL);
	assert(capacity == 0x20000000ULL && ccb == 1 && !strcmp(phy, "1"));
	assert(pin[0] == 0x5d && resources->sib.capacity == 0x100000);
	calls++;
	loads++;
	memset(plan, 0, sizeof(*plan));
	memset(rows, 0, sizeof(*rows));
	return fault == 8 ? -EKEYREJECTED : 0;
}
int tetris_modem_initialize_smem_b41(const struct tetris_modem_boot_plan *plan,
		void *firmware, size_t capacity, void *nc, size_t nc_capacity,
		void *cache, size_t cache_capacity, size_t alignment,
		const struct tetris_modem_cache_ops *ops)
{
	assert(plan && firmware && capacity == 0x20000000ULL);
	assert(nc == (void *)0xa0000000UL && cache == (void *)0xc0000000UL);
	assert(nc_capacity == 0x8000000 && cache_capacity == nc_capacity && alignment == 64);
	calls++;
	initialized++;
	assert(!ops->flush(ops->ctx, (unsigned long)nc, (unsigned long)nc + nc_capacity));
	return fault == 9 ? -EIO : 0;
}
int tetris_modem_bootstrap_once(struct blk_desc *dev,
		const struct tetris_modem_bootstrap_plan *plan)
{
	assert(dev && plan->resources.nc.base == 0xa0000000ULL && loads == 1 && initialized == 1);
	calls++;
	boots++;
	return fault == 10 ? -ETIMEDOUT : 0;
}
int tetris_modem_bootstrap_report(struct tetris_modem_bootstrap_report *report)
{
	memset(report, 0, sizeof(*report));
	return 0;
}
int main(int argc, char **argv)
{
	unsigned char pin[32] = {
		0x5d, 0x2b, 0xed, 0xd0, 0x00, 0x49, 0xfc, 0xed,
		0x98, 0x3d, 0x3a, 0xe5, 0x39, 0x89, 0x61, 0x6c,
		0x5c, 0x9f, 0x46, 0xc4, 0xed, 0xdd, 0x32, 0xa0,
		0x1a, 0x1a, 0xd4, 0x6f, 0xf8, 0xd2, 0xc5, 0x0f,
	};
	struct blk_desc dev = { 0 };
	struct tetris_modem_loaded_report report;
	unsigned int before;
	int ret;

	assert(argc == 2);
	fault = (unsigned int)atoi(argv[1]);
	assert(fault <= 16);
	if (fault == 14)
		bd.bi_dram[0].size = 0x60000000ULL;
	if (fault == 16)
		pin[0] ^= 1;
	ret = tetris_modem_loaded_boot_once(&dev, &dev, 'a', 1,
		fault == 15 ? "invalid" : "1", pin);
	assert(!tetris_modem_loaded_boot_report(&report) && report.error == ret);
	assert((!ret) == (!fault));
	assert(boots == (!fault || fault == 10));
	if (fault && fault != 10)
		assert(report.stage != TETRIS_MD_LOAD_BOOTSTRAP && !boots);
	if ((fault && fault <= 7) || fault >= 14)
		assert(!loads);
	assert(unmapped == (maps ? maps - (fault >= 11 && fault <= 13) : 0));
	before = calls;
	assert(tetris_modem_loaded_boot_once(&dev, &dev, 'a', 1, "1", pin) ==
		(ret ? ret : -EALREADY));
	assert(calls == before);
	return 0;
}
