// SPDX-License-Identifier: GPL-2.0-only
/* Explicit object parsing only. No probe, initcall or device registration. */
#include <linux/build_bug.h>
#include "mt6878-camsv-direct.h"

int mt6878_camsv_direct_object_smoke(void);
int mt6878_camsv_direct_object_smoke(void)
{
	BUILD_BUG_ON(MT6878_CAMSV_RECIPE_WRITES != 59);
	BUILD_BUG_ON(sizeof(((struct mt6878_camsv_direct *)0)->cq_dma) < 8);
	return 0;
}
