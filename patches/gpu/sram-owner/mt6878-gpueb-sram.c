// SPDX-License-Identifier: GPL-2.0-only
#ifdef GPUEB_SRAM_HOST_TEST
#include "sram-host.h"
#else
#include <linux/device.h>
#include <linux/err.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#endif
#include "mt6878-gpueb-sram.h"

struct mt6878_gpueb_sram {
	struct device *parent;
	struct mutex lock;
	struct gpueb_sram_core core;
	void __iomem *mapping;
};

struct mt6878_gpueb_window {
	struct mt6878_gpueb_sram *sram;
	enum gpueb_sram_window type;
};

struct mt6878_gpueb_sram *mt6878_gpueb_sram_create(struct device *parent,
					       const struct resource *resource)
{
	struct mt6878_gpueb_sram *sram;
	u64 size;
	int ret;

	if (!parent || !resource || resource_type(resource) != IORESOURCE_MEM ||
	    resource->end < resource->start)
		return ERR_PTR(-EINVAL);
	/* Check subtraction before adding one; reject a full-u64 wrapping range. */
	if (resource->end - resource->start >= GPUEB_SRAM_SIZE)
		return ERR_PTR(-ERANGE);
	size = resource->end - resource->start + 1;
	ret = gpueb_sram_validate(resource->start, size);
	if (ret)
		return ERR_PTR(ret);
	sram = kzalloc(sizeof(*sram), GFP_KERNEL);
	if (!sram)
		return ERR_PTR(-ENOMEM);
	mutex_init(&sram->lock);
	if (!request_mem_region(resource->start, size, dev_name(parent))) {
		ret = -EBUSY;
		goto free;
	}
	sram->mapping = ioremap(resource->start, size);
	if (!sram->mapping) {
		ret = -ENOMEM;
		goto release;
	}
	ret = gpueb_sram_open(&sram->core, resource->start, size);
	if (ret)
		goto unmap;
	sram->parent = get_device(parent);
	return sram;
unmap:
	iounmap(sram->mapping);
release:
	release_mem_region(resource->start, size);
free:
	kfree(sram);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_create);

struct mt6878_gpueb_window *mt6878_gpueb_sram_get_window(
		struct mt6878_gpueb_sram *sram, enum gpueb_sram_window type)
{
	struct mt6878_gpueb_window *window;
	int ret;

	if (IS_ERR_OR_NULL(sram))
		return ERR_PTR(-EINVAL);
	window = kzalloc(sizeof(*window), GFP_KERNEL);
	if (!window)
		return ERR_PTR(-ENOMEM);
	mutex_lock(&sram->lock);
	ret = gpueb_sram_claim_window(&sram->core, type);
	mutex_unlock(&sram->lock);
	if (ret) {
		kfree(window);
		return ERR_PTR(ret);
	}
	window->sram = sram;
	window->type = type;
	return window;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_get_window);

int mt6878_gpueb_sram_describe(struct mt6878_gpueb_window *window,
		u64 offset, u64 size, struct gpueb_sram_range *range)
{
	struct mt6878_gpueb_sram *sram;
	int ret;

	if (IS_ERR_OR_NULL(window))
		return -EINVAL;
	sram = window->sram;
	mutex_lock(&sram->lock);
	ret = gpueb_sram_window_range(&sram->core, window->type, offset, size, range);
	mutex_unlock(&sram->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_describe);

void mt6878_gpueb_sram_put_window(struct mt6878_gpueb_window *window)
{
	struct mt6878_gpueb_sram *sram;

	if (IS_ERR_OR_NULL(window))
		return;
	sram = window->sram;
	mutex_lock(&sram->lock);
	gpueb_sram_put_window(&sram->core, window->type);
	mutex_unlock(&sram->lock);
	kfree(window);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_put_window);

int mt6878_gpueb_sram_unknown_start(struct mt6878_gpueb_sram *sram)
{
	int ret;

	if (IS_ERR_OR_NULL(sram))
		return -EINVAL;
	mutex_lock(&sram->lock);
	ret = gpueb_sram_quarantine(&sram->core);
	mutex_unlock(&sram->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_unknown_start);

int mt6878_gpueb_sram_destroy(struct mt6878_gpueb_sram *sram)
{
	int ret;

	if (IS_ERR_OR_NULL(sram))
		return -EINVAL;
	mutex_lock(&sram->lock);
	ret = gpueb_sram_close(&sram->core);
	mutex_unlock(&sram->lock);
	if (ret)
		return ret;
	iounmap(sram->mapping);
	release_mem_region(sram->core.whole.start, sram->core.whole.size);
	put_device(sram->parent);
	kfree(sram);
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_destroy);
MODULE_LICENSE("GPL");
