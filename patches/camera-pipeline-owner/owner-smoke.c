// SPDX-License-Identifier: GPL-2.0-only
/* Explicit CI object only, no probe or production archive linkage. */
#include <linux/build_bug.h>
#include "mt6878-camera-pipeline-owner.h"

static_assert(sizeof(struct mtkcam_ipi_frame_param) == 92291);
static_assert(MT6878_CAMSV_RECIPE_WRITES == 59);
static_assert(sizeof_field(struct mt6878_pipeline_owner, callback_users) == sizeof(unsigned int));
