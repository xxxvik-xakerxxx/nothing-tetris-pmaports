// SPDX-License-Identifier: GPL-2.0-only
#include "mt6878-seninf-controller.h"

static_assert(ARRAY_SIZE(((struct mt6878_seninf_controller *)0)->dvfs) == 7);
static_assert(ARRAY_SIZE(((struct mt6878_seninf_events *)0)->mac) == 2);

/* Isolated object only, no runtime registration or production linkage. */
