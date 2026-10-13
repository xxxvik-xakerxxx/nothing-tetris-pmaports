/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_VMM_CONSUMER_H
#define MT6878_CAMERA_VMM_CONSUMER_H
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/kconfig.h>
#include <dt-bindings/power/mediatek,mt6878-power.h>

/* Actual attached native domain; no consumer-created supplier or rail handle. */
#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)
int mt6878_camera_vmm_check(struct device *consumer, unsigned int domain);
/* Read-only attachment admission BEFORE any resume request; no OFF/ON proof. */
int mt6878_camera_vmm_validate_domain(struct device *consumer, unsigned int domain);
#else
static inline int mt6878_camera_vmm_check(struct device *consumer, unsigned int domain)
{
	return -EOPNOTSUPP;
}
static inline int mt6878_camera_vmm_validate_domain(struct device *consumer, unsigned int domain)
{
	return -EOPNOTSUPP;
}
#endif
#endif
