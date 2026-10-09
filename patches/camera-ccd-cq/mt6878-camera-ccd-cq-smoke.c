// SPDX-License-Identifier: GPL-2.0-only
/* CI-only translation unit. No registration, runtime or archive linkage. */
#include <linux/build_bug.h>
#include "mt6878-camera-ccd-cq.h"

static_assert(sizeof(unsigned int) == 4);
static_assert(sizeof(mt6878_cq_u64) == 8);
static_assert(MT6878_CQ_DESC_BYTES == 12);
static_assert(MT6878_CQ_MAX_WORDS == 511);
