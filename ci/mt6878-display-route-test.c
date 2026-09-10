/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define BIT(n) (UINT32_C(1) << (n))
#define GENMASK(h, l) ((UINT32_MAX >> (31 - (h))) & (UINT32_MAX << (l)))

enum {
	DDP_COMPONENT_OVL_2L0, DDP_COMPONENT_OVL_2L1, DDP_COMPONENT_OVL_2L2,
	DDP_COMPONENT_DSC0, DDP_COMPONENT_DSI0, DDP_COMPONENT_COLOR0,
	DDP_COMPONENT_CCORR, DDP_COMPONENT_AAL0, DDP_COMPONENT_GAMMA,
	DDP_COMPONENT_POSTMASK0, DDP_COMPONENT_DITHER0,
};

struct mtk_mmsys_routes {
	uint32_t from_comp, to_comp, addr, mask, val;
};

#include "drivers/soc/mediatek/mt6878-mmsys.h"

static uint32_t regs[0x1000 / 4];

/* Model the pinned mtk_mmsys_ddp_connect/disconnect masked-write semantics. */
static void route(uint32_t from, uint32_t to, bool connect)
{
	for (unsigned int i = 0; i < sizeof(mt6878_mmsys_routing_table) /
	     sizeof(mt6878_mmsys_routing_table[0]); i++) {
		const struct mtk_mmsys_routes *r = &mt6878_mmsys_routing_table[i];

		if (r->from_comp != from || r->to_comp != to)
			continue;
		assert(r->addr < sizeof(regs) && !(r->addr & 3));
		assert(!(r->val & ~r->mask));
		regs[r->addr / 4] = (regs[r->addr / 4] & ~r->mask) |
			(connect ? r->val : 0);
	}
}

static void verify(void)
{
	assert(regs[0xd00 / 4] == 0x00010001);
	assert(regs[0xd30 / 4] == 0);
	assert(regs[0xd60 / 4] == 0x00020000);
	assert(regs[0xd54 / 4] == 1);
	assert(regs[0xd68 / 4] == 0);
	assert(regs[0xd7c / 4] == 0);
}

int main(void)
{
	const uint32_t seeds[] = { 0, UINT32_MAX, 0x5a5aa5a5 };

	for (unsigned int s = 0; s < sizeof(seeds) / sizeof(seeds[0]); s++) {
		for (unsigned int i = 0; i < sizeof(regs) / sizeof(regs[0]); i++)
			regs[i] = seeds[s];
		regs[0xd00 / 4] = 0x00050005;
		regs[0xd30 / 4] = 0x00020002;
		regs[0xd60 / 4] = 0x00020002;
		for (unsigned int cycle = 0; cycle < 3; cycle++) {
			route(DDP_COMPONENT_OVL_2L2, DDP_COMPONENT_DSC0, true);
			verify();
			assert(regs[0x100 / 4] == seeds[s]);
			assert(regs[0x110 / 4] == seeds[s]);
			route(DDP_COMPONENT_OVL_2L2, DDP_COMPONENT_DSC0, false);
			assert(regs[0xd00 / 4] == 0);
			assert(regs[0xd30 / 4] == 0);
			assert(regs[0xd60 / 4] == 0);
		}
	}
	puts("MT6878 route: patch application and connect/disconnect model PASS (not hardware lifecycle proof)");
	return 0;
}
