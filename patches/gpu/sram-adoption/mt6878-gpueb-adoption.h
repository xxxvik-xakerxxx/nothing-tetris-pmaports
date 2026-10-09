/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_ADOPTION_H
#define MT6878_GPUEB_ADOPTION_H
#include "mt6878-gpueb-sram.h"
#ifndef GPUEB_ADOPTION_HOST_TEST
#include <linux/err.h>
#include <linux/errno.h>
#endif
struct platform_device;
struct device;
struct resource;
struct mt6878_gpueb_adoption;
struct mt6878_gpueb_adopted_window;

#if defined(GPUEB_ADOPTION_IMPLEMENTATION) || defined(GPUEB_ADOPTION_HOST_TEST) || \
	defined(CONFIG_MTK_MT6878_GPUEB_ADOPTION)

/* Called explicitly by the future real remoteproc parent. No automatic probe,
 * DT change, power claim, firmware execution or independent child claim.
 */
struct mt6878_gpueb_adoption *mt6878_gpueb_adopt_parent(struct platform_device *parent);
int mt6878_gpueb_unadopt_parent(struct mt6878_gpueb_adoption *parent);
struct mt6878_gpueb_adopted_window *mt6878_gpueb_adopt_window(
		struct device *parent, const struct resource *resource,
		enum gpueb_sram_window type);
int mt6878_gpueb_adopted_resource(struct mt6878_gpueb_adopted_window *window,
				struct resource *resource);
void mt6878_gpueb_unadopt_window(struct mt6878_gpueb_adopted_window *window);
int mt6878_gpueb_adoption_unknown_start(struct mt6878_gpueb_adoption *parent);
/* Intentionally -EOPNOTSUPP until a reviewed real boot/power/IRQ owner exists.
 * A resource lease or RPROC_RUNNING is NOT permission to touch hardware.
 */
int mt6878_gpueb_adoption_io_gate(struct mt6878_gpueb_adopted_window *window);
#else
static inline struct mt6878_gpueb_adoption *mt6878_gpueb_adopt_parent(struct platform_device *parent)
{
	return ERR_PTR(-EOPNOTSUPP);
}
static inline int mt6878_gpueb_unadopt_parent(struct mt6878_gpueb_adoption *parent)
{
	return -EOPNOTSUPP;
}
static inline struct mt6878_gpueb_adopted_window *mt6878_gpueb_adopt_window(
		struct device *parent, const struct resource *resource, enum gpueb_sram_window type)
{
	return ERR_PTR(-EOPNOTSUPP);
}
static inline int mt6878_gpueb_adopted_resource(struct mt6878_gpueb_adopted_window *window,
					      struct resource *resource)
{
	return -EOPNOTSUPP;
}
static inline void mt6878_gpueb_unadopt_window(struct mt6878_gpueb_adopted_window *window) {}
static inline int mt6878_gpueb_adoption_unknown_start(struct mt6878_gpueb_adoption *parent)
{
	return -EOPNOTSUPP;
}
static inline int mt6878_gpueb_adoption_io_gate(struct mt6878_gpueb_adopted_window *window)
{
	return -EOPNOTSUPP;
}
#endif
#endif
