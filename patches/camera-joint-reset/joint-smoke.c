// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include "mt6878-camera-joint-reset.h"

static_assert(__same_type(&mt6878_camera_joint_reset,
	(int (*)(struct mt6878_camera_joint_reset *, struct mt6878_native_capture *,
		const struct mt6878_camsv_job *))NULL));
MODULE_LICENSE("GPL");
static_assert(__same_type(&mt6878_camera_cold_probe,
	(int (*)(struct mt6878_native_capture *, struct platform_device *,
		struct device *, struct device *, struct device *, struct v4l2_subdev *,
		struct v4l2_subdev *, unsigned int))NULL));
