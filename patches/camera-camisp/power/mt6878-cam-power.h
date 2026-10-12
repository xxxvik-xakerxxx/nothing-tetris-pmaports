/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _MT6878_CAM_POWER_H
#define _MT6878_CAM_POWER_H

#include <dt-bindings/power/mediatek,mt6878-power.h>
#include <linux/regmap.h>

#include "mtk-pm-domains.h"

/* Sparse Linux descriptors for review, not a registered genpd provider. */
extern const struct scpsys_domain_data
mt6878_cam_domain_data[MT6878_POWER_DOMAIN_NR];

/*
 * Local transactions only; caller must own the shared SPM regmap and serialize
 * them. Supplies, parent genpd, clocks, SRAM and bus protection are external.
 * Failure can leave partial hardware state: retain suppliers and stop access.
 */
int mt6878_cam_ctl_set(struct regmap *spm, unsigned int domain, bool on);
int mt6878_vmm_iso_set(struct regmap *spm, bool isolate);

#endif
