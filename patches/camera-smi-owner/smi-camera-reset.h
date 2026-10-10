/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MTK_SMI_CAMERA_RESET_H
#define MTK_SMI_CAMERA_RESET_H

#include <linux/device.h>
#include <linux/errno.h>

/* Exclusive reset lease on DT-described MT6878 camera common31. Successful
 * ON retains supplier runtime PM and module/consumer references until OFF.
 * Failed writes retain the lease/clamp; no implicit retry or force-clear.
 * Consumer must serialize the entire reset, retain DMA on errors and prevent
 * supplier/consumer unbind until release. Never call under supplier dev lock.
 */
#if IS_REACHABLE(CONFIG_MTK_SMI)
int mtk_smi_camera_reset_clamp(struct device *supplier,
	struct device *consumer, bool on);
#else
static inline int mtk_smi_camera_reset_clamp(struct device *supplier,
	struct device *consumer, bool on)
{
	return -EOPNOTSUPP;
}
#endif

#endif
