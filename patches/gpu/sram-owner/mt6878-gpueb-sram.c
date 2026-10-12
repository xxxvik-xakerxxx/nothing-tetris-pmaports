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

int mt6878_gpueb_sram_check_parent(struct mt6878_gpueb_sram *sram, struct device *parent)
{
	int ret;

	if (IS_ERR_OR_NULL(sram) || !parent)
		return -EINVAL;
	mutex_lock(&sram->lock);
	ret = sram->core.phase != GPUEB_SRAM_OWNED ? -ESHUTDOWN :
		sram->parent != parent ? -ENODEV : 0;
	mutex_unlock(&sram->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_check_parent);

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

struct mt6878_gpueb_reader {
	struct mt6878_gpueb_sram *sram;
};

int mt6878_gpueb_sram_reader_words(struct mt6878_gpueb_reader *reader,
		enum gpueb_sram_window type, u64 offset, u32 *words, unsigned int count)
{
	struct mt6878_gpueb_sram *sram;
	struct gpueb_sram_range range;
	unsigned int i;
	int ret;

	if (!reader || !words || !count ||
	    count > GPUEB_MBOX_SIZE / sizeof(*words))
		return -EINVAL;
	sram = reader->sram;
	ret = gpueb_sram_window_range(&sram->core, type, offset,
				     (u64)count * sizeof(*words), &range);
	if (!ret)
		for (i = 0; i < count; i++)
			words[i] = readl(sram->mapping + (range.start - sram->core.whole.start) +
					 i * sizeof(*words));
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_reader_words);

int mt6878_gpueb_sram_read_transaction(struct mt6878_gpueb_window *gpr,
		struct mt6878_gpueb_window *mbox,
		int (*consume)(struct mt6878_gpueb_reader *, void *), void *context)
{
	struct mt6878_gpueb_reader reader;
	struct gpueb_sram_range range;
	int ret;

	if (IS_ERR_OR_NULL(gpr) || IS_ERR_OR_NULL(mbox) || !consume ||
	    gpr->sram != mbox->sram || gpr->type != GPUEB_WINDOW_GPR ||
	    mbox->type != GPUEB_WINDOW_MBOX)
		return -EINVAL;
	reader.sram = gpr->sram;
	mutex_lock(&reader.sram->lock);
	ret = gpueb_sram_window_range(&reader.sram->core, GPUEB_WINDOW_GPR,
				     0, GPUEB_GPR_SIZE, &range);
	if (!ret)
		ret = gpueb_sram_window_range(&reader.sram->core, GPUEB_WINDOW_MBOX,
					     0, GPUEB_MBOX_SIZE, &range);
	if (!ret)
		ret = consume(&reader, context);
	mutex_unlock(&reader.sram->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_read_transaction);

int mt6878_gpueb_sram_send_transaction(struct mt6878_gpueb_window *gpr,
		struct mt6878_gpueb_window *mbox, unsigned int channel,
		const u32 *words, unsigned int count,
		int (*before)(struct mt6878_gpueb_reader *, void *),
		int (*commit)(struct mt6878_gpueb_reader *, void *), void *context)
{
	struct mt6878_gpueb_reader reader;
	struct gpueb_sram_range range;
	u64 offset;
	unsigned int i;
	int ret;

	if (IS_ERR_OR_NULL(gpr) || IS_ERR_OR_NULL(mbox) || !words || !before || !commit ||
	    gpr->sram != mbox->sram || gpr->type != GPUEB_WINDOW_GPR ||
	    mbox->type != GPUEB_WINDOW_MBOX)
		return -EINVAL;
	ret = gpueb_sram_tx_slot(channel, count, &offset);
	if (ret)
		return ret;
	reader.sram = gpr->sram;
	mutex_lock(&reader.sram->lock);
	ret = gpueb_sram_window_range(&reader.sram->core, GPUEB_WINDOW_GPR,
				     0, GPUEB_GPR_SIZE, &range);
	if (!ret)
		ret = gpueb_sram_window_range(&reader.sram->core, GPUEB_WINDOW_MBOX,
					     offset, (u64)count * sizeof(*words), &range);
	if (!ret)
		ret = before(&reader, context);
	if (!ret) {
		for (i = 0; i < count; i++)
			writel(words[i], reader.sram->mapping +
				(range.start - reader.sram->core.whole.start) + i * sizeof(*words));
		ret = commit(&reader, context);
	}
	mutex_unlock(&reader.sram->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_sram_send_transaction);

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
