// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <soc/mediatek/cam-main-lease.h>

static_assert(__same_type(&mt6878_cam_main_prepare,
	(int (*)(struct device *, struct mt6878_cam_main_lease **))NULL));
static_assert(__same_type(&mt6878_cam_main_regmap,
	(struct regmap *(*)(struct mt6878_cam_main_lease *))NULL));
static_assert(__same_type(&mt6878_cam_main_reset_pulse,
	(int (*)(struct mt6878_cam_main_lease *, unsigned int))NULL));
static_assert(__same_type(&mt6878_cam_main_retire,
	(int (*)(struct mt6878_cam_main_lease **))NULL));
MODULE_LICENSE("GPL");
