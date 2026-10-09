// SPDX-License-Identifier: GPL-2.0-only
#include <linux/build_bug.h>
#include <linux/kernel.h>
#include "mt6878-camsv-platform.h"

static_assert(ARRAY_SIZE(((struct mt6878_camsv_platform *)0)->lines) == 4);
static_assert(ARRAY_SIZE(((struct mt6878_camsv_resources *)0)->clocks) == 8);
