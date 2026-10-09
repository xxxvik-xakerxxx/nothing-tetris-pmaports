/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GPUEB_ADOPTION_HOST_H
#define GPUEB_ADOPTION_HOST_H
#include "sram-host.h"
#include <string.h>
#define EPROBE_DEFER 517
#define DEFINE_MUTEX(name) struct mutex name = { .value = PTHREAD_MUTEX_INITIALIZER }
struct platform_device {
	struct device dev;
	struct resource full;
	int has_full;
};
static inline struct resource *platform_get_resource_byname(struct platform_device *pdev,
					unsigned int type, const char *name)
{
	assert(type == IORESOURCE_MEM && !strcmp(name, "gpueb_base"));
	return pdev->has_full ? &pdev->full : NULL;
}
#endif
