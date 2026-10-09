// SPDX-License-Identifier: GPL-2.0-only
#include <linux/device.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include "mt6878-gpueb-adoption.h"
#include "mt6878-gpueb-io.h"

struct mt6878_gpueb_io {
	struct mt6878_gpueb_adoption *owner;
	struct mt6878_gpueb_adopted_window *gpr, *data;
	struct gpueb_io_core core;
	spinlock_t lock;
	void __iomem *maps[GPUEB_IO_REGION_COUNT];
	struct resource resources[GPUEB_IO_REGION_COUNT];
	unsigned int controls_claimed;
};

/* Four discrete 4-byte DT resources. No guessed 0x80 register envelope and
 * no IRQ[1] bank at +0x84/+0x88 confused with mbox0 +0x74/+0x78.
 */
static const struct {
	const char *name;
	resource_size_t address;
	enum gpueb_io_region region;
} controls[] = {
	{ "mbox0_send", 0x13c62000, GPUEB_IO_SEND },
	{ "mbox0_set",  0x13c62004, GPUEB_IO_SET },
	{ "mbox0_recv", 0x13c62078, GPUEB_IO_RECV },
	{ "mbox0_clr",  0x13c62074, GPUEB_IO_CLEAR },
};

static void release_prepared(struct mt6878_gpueb_io *scope)
{
	unsigned int i;

	for (i = 0; i < GPUEB_IO_REGION_COUNT; i++)
		if (scope->maps[i])
			iounmap(scope->maps[i]);
	for (i = 0; i < scope->controls_claimed; i++)
		release_mem_region(controls[i].address, 4);
	mt6878_gpueb_unadopt_window(scope->data);
	mt6878_gpueb_unadopt_window(scope->gpr);
	kfree(scope);
}

struct mt6878_gpueb_io *mt6878_gpueb_io_prepare(struct platform_device *parent,
					     struct mt6878_gpueb_adoption *owner)
{
	struct mt6878_gpueb_io *scope;
	struct resource *resource;
	unsigned int i;
	int ret;

	if (!parent || IS_ERR_OR_NULL(owner))
		return ERR_PTR(-EINVAL);
	/* Validate every control bound before any lease, claim or mapping. */
	for (i = 0; i < ARRAY_SIZE(controls); i++) {
		resource = platform_get_resource_byname(parent, IORESOURCE_MEM, controls[i].name);
		if (!resource || resource->start != controls[i].address ||
		    resource->end != controls[i].address + 3)
			return ERR_PTR(-EINVAL);
	}
	scope = kzalloc(sizeof(*scope), GFP_KERNEL);
	if (!scope)
		return ERR_PTR(-ENOMEM);
	scope->owner = owner;
	spin_lock_init(&scope->lock);
	resource = platform_get_resource_byname(parent, IORESOURCE_MEM, "gpueb_gpr_base");
	scope->gpr = mt6878_gpueb_adopt_window(&parent->dev, resource, GPUEB_WINDOW_GPR);
	if (IS_ERR(scope->gpr)) {
		ret = PTR_ERR(scope->gpr);
		scope->gpr = NULL;
		goto fail;
	}
	resource = platform_get_resource_byname(parent, IORESOURCE_MEM, "mbox0_base");
	scope->data = mt6878_gpueb_adopt_window(&parent->dev, resource, GPUEB_WINDOW_MBOX);
	if (IS_ERR(scope->data)) {
		ret = PTR_ERR(scope->data);
		scope->data = NULL;
		goto fail;
	}
	ret = mt6878_gpueb_adopted_resource(scope->gpr, &scope->resources[GPUEB_IO_GPR]);
	if (!ret)
		ret = mt6878_gpueb_adopted_resource(scope->data, &scope->resources[GPUEB_IO_DATA]);
	if (ret)
		goto fail;
	for (i = 0; i < ARRAY_SIZE(controls); i++) {
		resource = platform_get_resource_byname(parent, IORESOURCE_MEM, controls[i].name);
		if (!request_mem_region(resource->start, 4, dev_name(&parent->dev))) {
			ret = -EBUSY;
			goto fail;
		}
		scope->controls_claimed++;
		scope->resources[controls[i].region] = *resource;
	}
	for (i = 0; i < GPUEB_IO_REGION_COUNT; i++) {
		resource = &scope->resources[i];
		scope->maps[i] = ioremap(resource->start, resource_size(resource));
		if (!scope->maps[i]) {
			ret = -ENOMEM;
			goto fail;
		}
	}
	/* zero-allocated core remains UNPROVEN, not OFF or IRQ-ready. */
	return scope;
fail:
	release_prepared(scope);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_prepare);

static int scope_read32(void *context, enum gpueb_io_region region, u32 offset, u32 *value)
{
	struct mt6878_gpueb_io *scope = context;
	int ret = gpueb_io_bounds(region, offset, 4);

	if (ret)
		return ret;
	*value = readl(scope->maps[region] + offset);
	return 0;
}

static int scope_write32(void *context, enum gpueb_io_region region, u32 offset, u32 value)
{
	struct mt6878_gpueb_io *scope = context;
	int ret = gpueb_io_bounds(region, offset, 4);

	if (ret)
		return ret;
	/* No arbitrary GPR writes and no firmware SRAM upload API. */
	if (region != GPUEB_IO_DATA && region != GPUEB_IO_SET && region != GPUEB_IO_CLEAR)
		return -EPERM;
	writel(value, scope->maps[region] + offset);
	return 0;
}

static const struct gpueb_io_ops mmio_ops = {
	.read32 = scope_read32, .write32 = scope_write32,
};

#define SCOPE_LOCKED_CALL(expression) do { \
	unsigned long flags; \
	int ret; \
	if (IS_ERR_OR_NULL(scope)) \
		return -EINVAL; \
	spin_lock_irqsave(&scope->lock, flags); \
	ret = (expression); \
	spin_unlock_irqrestore(&scope->lock, flags); \
	return ret; \
} while (0)

int mt6878_gpueb_io_get(struct mt6878_gpueb_io *scope)
{
	SCOPE_LOCKED_CALL(gpueb_io_get(&scope->core));
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_get);
int mt6878_gpueb_io_put(struct mt6878_gpueb_io *scope)
{
	SCOPE_LOCKED_CALL(gpueb_io_put(&scope->core));
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_put);
int mt6878_gpueb_io_tx(struct mt6878_gpueb_io *scope, const u32 *words, size_t count)
{
	SCOPE_LOCKED_CALL(gpueb_io_tx(&scope->core, &mmio_ops, scope, words, count));
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_tx);
int mt6878_gpueb_io_rx(struct mt6878_gpueb_io *scope, u32 *words, size_t count)
{
	SCOPE_LOCKED_CALL(gpueb_io_rx(&scope->core, &mmio_ops, scope, words, count));
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_rx);
int mt6878_gpueb_io_gpr_read(struct mt6878_gpueb_io *scope, u32 offset, u32 *value)
{
	SCOPE_LOCKED_CALL(gpueb_io_gpr_read(&scope->core, &mmio_ops, scope, offset, value));
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_gpr_read);
int mt6878_gpueb_io_quiesce(struct mt6878_gpueb_io *scope)
{
	/* Taking the transaction lock drains any in-flight MMIO transaction.
	 * Async callback/work references still prevent final removal.
	 */
	SCOPE_LOCKED_CALL(gpueb_io_quiesce(&scope->core));
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_quiesce);

int mt6878_gpueb_io_request_irq(struct mt6878_gpueb_io *scope)
{
	unsigned long flags;
	int ret;

	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	spin_lock_irqsave(&scope->lock, flags);
	ret = scope->core.first_error ? scope->core.first_error :
		(scope->core.phase == GPUEB_IO_TRANSACTION ? -EOPNOTSUPP : -EHOSTDOWN);
	spin_unlock_irqrestore(&scope->lock, flags);
	/* Stop first at unproven power; even after future power proof, mbox0
	 * other-channel ownership/level IRQ masking/drain need a real backend.
	 * Do not request/enable/disable a possibly live or shared IRQ here.
	 */
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_request_irq);

int mt6878_gpueb_io_unknown_start(struct mt6878_gpueb_io *scope, int error)
{
	unsigned long flags;
	int ret;

	if (IS_ERR_OR_NULL(scope) || error >= 0)
		return -EINVAL;
	spin_lock_irqsave(&scope->lock, flags);
	ret = gpueb_io_quarantine(&scope->core, error);
	spin_unlock_irqrestore(&scope->lock, flags);
	/* Process context only; no sleeping adoption mutex inside an ISR lock. */
	mt6878_gpueb_adoption_unknown_start(scope->owner);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_unknown_start);

int mt6878_gpueb_io_destroy(struct mt6878_gpueb_io *scope)
{
	unsigned long flags;
	int ret;

	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	spin_lock_irqsave(&scope->lock, flags);
	ret = gpueb_io_can_destroy(&scope->core);
	if (!ret)
		gpueb_io_quiesce(&scope->core);
	spin_unlock_irqrestore(&scope->lock, flags);
	if (ret)
		return ret;
	release_prepared(scope);
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_io_destroy);
MODULE_LICENSE("GPL");
