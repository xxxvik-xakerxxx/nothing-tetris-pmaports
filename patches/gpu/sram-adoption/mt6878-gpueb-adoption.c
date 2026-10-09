// SPDX-License-Identifier: GPL-2.0-only
#ifdef GPUEB_ADOPTION_HOST_TEST
#include "adoption-host.h"
#else
#include <linux/device.h>
#include <linux/err.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#endif
#define GPUEB_ADOPTION_IMPLEMENTATION
#include "mt6878-gpueb-adoption.h"

struct mt6878_gpueb_adoption {
	struct device *device;
	struct mt6878_gpueb_sram *sram;
	unsigned int clients;
};
struct mt6878_gpueb_adopted_window {
	struct mt6878_gpueb_adoption *parent;
	struct mt6878_gpueb_window *lease;
	struct resource resource;
};

/* The validated profile describes exactly one physical SRAM on one SoC. */
static DEFINE_MUTEX(adoption_lock);
static struct mt6878_gpueb_adoption *adopted;

struct mt6878_gpueb_adoption *mt6878_gpueb_adopt_parent(struct platform_device *parent)
{
	struct mt6878_gpueb_adoption *owner;
	struct resource *resource;
	int ret;

	if (!parent)
		return ERR_PTR(-EINVAL);
	resource = platform_get_resource_byname(parent, IORESOURCE_MEM, "gpueb_base");
	if (!resource)
		return ERR_PTR(-EINVAL);
	owner = kzalloc(sizeof(*owner), GFP_KERNEL);
	if (!owner)
		return ERR_PTR(-ENOMEM);
	mutex_lock(&adoption_lock);
	if (adopted) {
		ret = -EBUSY;
		goto fail;
	}
	owner->sram = mt6878_gpueb_sram_create(&parent->dev, resource);
	if (IS_ERR(owner->sram)) {
		ret = PTR_ERR(owner->sram);
		goto fail;
	}
	owner->device = &parent->dev;
	adopted = owner;
	mutex_unlock(&adoption_lock);
	return owner;
fail:
	mutex_unlock(&adoption_lock);
	kfree(owner);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_adopt_parent);

struct mt6878_gpueb_adopted_window *mt6878_gpueb_adopt_window(
		struct device *parent, const struct resource *resource,
		enum gpueb_sram_window type)
{
	struct mt6878_gpueb_adopted_window *window;
	struct gpueb_sram_range range;
	u64 size;
	int ret;

	if (!parent || !resource || resource_type(resource) != IORESOURCE_MEM ||
	    resource->end < resource->start ||
	    resource->end - resource->start >= GPUEB_SRAM_SIZE)
		return ERR_PTR(-EINVAL);
	size = resource->end - resource->start + 1;
	window = kzalloc(sizeof(*window), GFP_KERNEL);
	if (!window)
		return ERR_PTR(-ENOMEM);
	mutex_lock(&adoption_lock);
	if (!adopted || adopted->device != parent) {
		ret = -EPROBE_DEFER;
		goto fail;
	}
	window->lease = mt6878_gpueb_sram_get_window(adopted->sram, type);
	if (IS_ERR(window->lease)) {
		ret = PTR_ERR(window->lease);
		goto fail;
	}
	ret = mt6878_gpueb_sram_describe(window->lease, 0, size, &range);
	/* Require the complete typed slice, not a matching prefix or guessed span. */
	if (!ret && (range.start != resource->start ||
	    size != (type == GPUEB_WINDOW_GPR ? GPUEB_GPR_SIZE : GPUEB_MBOX_SIZE)))
		ret = -EINVAL;
	if (ret) {
		mt6878_gpueb_sram_put_window(window->lease);
		goto fail;
	}
	window->resource = *resource;
	window->parent = adopted;
	adopted->clients++;
	mutex_unlock(&adoption_lock);
	return window;
fail:
	mutex_unlock(&adoption_lock);
	kfree(window);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_adopt_window);

int mt6878_gpueb_adopted_resource(struct mt6878_gpueb_adopted_window *window,
				struct resource *resource)
{
	struct gpueb_sram_range range;
	int ret;

	if (IS_ERR_OR_NULL(window) || !resource)
		return -EINVAL;
	mutex_lock(&adoption_lock);
	ret = mt6878_gpueb_sram_describe(window->lease, 0,
		window->resource.end - window->resource.start + 1, &range);
	if (!ret)
		*resource = window->resource;
	mutex_unlock(&adoption_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_adopted_resource);

void mt6878_gpueb_unadopt_window(struct mt6878_gpueb_adopted_window *window)
{
	if (IS_ERR_OR_NULL(window))
		return;
	mutex_lock(&adoption_lock);
	mt6878_gpueb_sram_put_window(window->lease);
	window->parent->clients--;
	mutex_unlock(&adoption_lock);
	kfree(window);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_unadopt_window);

int mt6878_gpueb_adoption_unknown_start(struct mt6878_gpueb_adoption *parent)
{
	int ret;

	if (IS_ERR_OR_NULL(parent))
		return -EINVAL;
	mutex_lock(&adoption_lock);
	ret = adopted == parent ? mt6878_gpueb_sram_unknown_start(parent->sram) : -EINVAL;
	mutex_unlock(&adoption_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_adoption_unknown_start);

int mt6878_gpueb_unadopt_parent(struct mt6878_gpueb_adoption *parent)
{
	int ret;

	if (IS_ERR_OR_NULL(parent))
		return -EINVAL;
	mutex_lock(&adoption_lock);
	if (adopted != parent) {
		ret = -EINVAL;
		goto out;
	}
	if (parent->clients) {
		ret = -EBUSY;
		goto out;
	}
	ret = mt6878_gpueb_sram_destroy(parent->sram);
	if (ret)
		goto out;
	adopted = NULL;
	kfree(parent);
out:
	mutex_unlock(&adoption_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_unadopt_parent);

int mt6878_gpueb_adoption_io_gate(struct mt6878_gpueb_adopted_window *window)
{
	struct resource resource;
	int ret = mt6878_gpueb_adopted_resource(window, &resource);

	return ret ? ret : -EOPNOTSUPP;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_adoption_io_gate);
MODULE_LICENSE("GPL");
