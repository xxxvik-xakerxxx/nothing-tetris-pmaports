// SPDX-License-Identifier: GPL-2.0-only
/* Explicit CI kernel object only. No probe, runtime or production linkage. */
#include <linux/build_bug.h>
#include <linux/ioctl.h>
#include "mt6878-camera-ccd-composer-session.h"

static_assert(sizeof(struct ccd_worker_item) == 1036);
static_assert(sizeof(struct mtkcam_ipi_frame_param) == 92291);
static_assert(MT6878_CAMSV_RECIPE_WRITES == 59);
