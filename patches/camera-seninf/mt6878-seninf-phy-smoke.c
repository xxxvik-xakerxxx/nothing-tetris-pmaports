// SPDX-License-Identifier: GPL-2.0-only
/* CI targets this object explicitly in a temporary output tree. Never linked. */
#include <linux/build_bug.h>
#include <linux/compiler_attributes.h>
#include <linux/kernel.h>

#include "mt6878-seninf-phy.h"

static_assert(ARRAY_SIZE(mt6878_phy_init) == 31);
static_assert(ARRAY_SIZE(mt6878_phy_efuse) == 12);
static_assert(ARRAY_SIZE(mt6878_phy_mac) == 28);
static_assert(ARRAY_SIZE(mt6878_phy_trios) == 26);
static_assert(sizeof(((struct mt6878_phy_inputs *)0)->lanes) ==
	      3 * sizeof(unsigned int));

static int __maybe_unused mt6878_seninf_phy_smoke_validate(
	const struct mt6878_phy_backend *backend,
	const struct mt6878_seninf_plan *plan,
	const struct mt6878_phy_inputs *inputs)
{
	/* Pure validation only: no register, power, IRQ or sensor callbacks. */
	return mt6878_phy_validate(backend, plan, inputs);
}
