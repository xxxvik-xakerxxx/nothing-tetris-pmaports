// SPDX-License-Identifier: GPL-2.0-only
#include <linux/device.h>
#include <linux/err.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/irq.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <dt-bindings/power/mediatek,mt6878-power.h>
#include "mt6878-gpueb-sram.h"
#include "mt6878-gpueb-reset.h"

enum { GPUEB_MBOX_CONTROL_FIRST = 4, GPUEB_MBOX_CONTROL_COUNT = 4 };

/* ee2be53 MT6878 DT. GPR/data are aliases inside the sole SRAM claim;
 * the four mailbox control words are OUTSIDE the separate reset bank.
 */
static const struct {
	const char *name;
	resource_size_t start, size;
} gpueb_resources[] = {
	{ "gpueb_base", GPUEB_SRAM_BASE, GPUEB_SRAM_SIZE },
	{ "gpueb_gpr_base", GPUEB_SRAM_BASE + GPUEB_GPR_OFFSET, GPUEB_GPR_SIZE },
	{ "gpueb_reg_base", 0x13c60000, 0x2000 },
	{ "mbox0_base", GPUEB_SRAM_BASE + GPUEB_MBOX_OFFSET, GPUEB_MBOX_SIZE },
	{ "mbox0_set", 0x13c62004, 0x4 },
	{ "mbox0_clr", 0x13c62074, 0x4 },
	{ "mbox0_send", 0x13c62000, 0x4 },
	{ "mbox0_recv", 0x13c62078, 0x4 },
};

int mt6878_gpueb_reset_validate_resources(struct platform_device *parent)
{
	struct resource *resource;
	unsigned int i, count = 0;

	if (!parent || !parent->dev.of_node)
		return -EINVAL;
	if (!of_device_is_available(parent->dev.of_node) ||
	    !of_device_is_compatible(parent->dev.of_node, "mediatek,gpueb"))
		return -ENODEV;
	for (i = 0; i < parent->num_resources; i++)
		if (resource_type(&parent->resource[i]) == IORESOURCE_MEM)
			count++;
	if (count != ARRAY_SIZE(gpueb_resources))
		return -EINVAL;
	for (i = 0; i < ARRAY_SIZE(gpueb_resources); i++) {
		resource = platform_get_resource_byname(parent, IORESOURCE_MEM,
						gpueb_resources[i].name);
		/* Compare endpoints with a bounded static profile, avoiding size
		 * arithmetic on possibly reversed or wrapping supplied resources.
		 */
		if (!resource || resource->start != gpueb_resources[i].start ||
		    resource->end != gpueb_resources[i].start + gpueb_resources[i].size - 1)
			return -ERANGE;
	}
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_validate_resources);

struct mt6878_gpueb_reset {
	struct device *parent;
	struct mt6878_gpueb_sram *sram;
	struct mt6878_gpueb_window *gpr, *mbox;
	void __iomem *registers;
	struct resource *mbox_control[GPUEB_MBOX_CONTROL_COUNT];
	unsigned int mbox_claims;
	struct mutex lock;
	spinlock_t irq_lock;
	int irq, first_error;
	bool reset_written;
};

static void release_mailbox_resources(struct mt6878_gpueb_reset *scope)
{
	struct resource *resource;

	while (scope->mbox_claims) {
		resource = scope->mbox_control[--scope->mbox_claims];
		release_mem_region(resource->start, resource_size(resource));
	}
}

static int latch(struct mt6878_gpueb_reset *scope, int error)
{
	unsigned long flags;
	int ret;
	spin_lock_irqsave(&scope->irq_lock, flags);
	if (!scope->first_error)
		scope->first_error = error;
	ret = scope->first_error;
	spin_unlock_irqrestore(&scope->irq_lock, flags);
	return ret;
}

static irqreturn_t unexpected_irq(int irq, void *data)
{
	struct mt6878_gpueb_reset *scope = data;
	/* NO_AUTOEN and no enable API: no firmware channel may be consumed yet.
 * Unexpected delivery is contained, not ACKed or called BOOTREADY/OFF.
 */
	latch(scope, -EPROTO);
	disable_irq_nosync(irq);
	return IRQ_HANDLED;
}

struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(
	struct platform_device *parent, struct mt6878_gpueb_sram *sram)
{
	struct mt6878_gpueb_reset *scope;
	struct resource *resource;
	struct of_phandle_args supplier;
	unsigned int i;
	int ret, irq;

	if (!parent || IS_ERR_OR_NULL(sram) || !parent->dev.pm_domain)
		return ERR_PTR(-EINVAL);
	ret = mt6878_gpueb_reset_validate_resources(parent);
	if (ret)
		return ERR_PTR(ret);
	/* One actual attached MT6878 SPM MFG0 domain, not a caller permission
 * flag or a similarly named arbitrary runtime-PM device.
 */
	if (of_count_phandle_with_args(parent->dev.of_node, "power-domains",
				       "#power-domain-cells") != 1)
		return ERR_PTR(-EINVAL);
	ret = of_parse_phandle_with_args(parent->dev.of_node, "power-domains",
					"#power-domain-cells", 0, &supplier);
	if (ret)
		return ERR_PTR(ret);
	ret = supplier.args_count == 1 &&
		supplier.args[0] == MT6878_POWER_DOMAIN_MFG0_SHUTDOWN &&
		of_device_is_compatible(supplier.np, "mediatek,mt6878-power-controller");
	of_node_put(supplier.np);
	if (!ret)
		return ERR_PTR(-EINVAL);
	resource = platform_get_resource_byname(parent, IORESOURCE_MEM, "gpueb_reg_base");
	irq = platform_get_irq_byname(parent, "mbox0");
	if (irq < 0)
		return ERR_PTR(irq);
	if (irq_get_trigger_type(irq) != IRQ_TYPE_LEVEL_HIGH)
		return ERR_PTR(-EINVAL);
	scope = kzalloc(sizeof(*scope), GFP_KERNEL);
	if (!scope)
		return ERR_PTR(-ENOMEM);
	mutex_init(&scope->lock);
	spin_lock_init(&scope->irq_lock);
	scope->sram = sram;
	scope->irq = irq;
	if (!try_module_get(THIS_MODULE)) {
		ret = -ENODEV;
		goto free;
	}
	/* No fabricated ACTIVE state, attach side effects or resume/power writes.
	 * A later real cold-start owner must produce this existing usage reference.
	 */
	ret = pm_runtime_get_if_in_use(&parent->dev);
	if (ret <= 0) {
		ret = ret ?: -EAGAIN;
		goto put_module;
	}
	scope->parent = get_device(&parent->dev);
	scope->gpr = mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_GPR);
	if (IS_ERR(scope->gpr)) {
		ret = PTR_ERR(scope->gpr);
		goto put_pm;
	}
	scope->mbox = mt6878_gpueb_sram_get_window(sram, GPUEB_WINDOW_MBOX);
	if (IS_ERR(scope->mbox)) {
		ret = PTR_ERR(scope->mbox);
		goto put_gpr;
	}
	if (!request_mem_region(resource->start, resource_size(resource), dev_name(scope->parent))) {
		ret = -EBUSY;
		goto put_mbox;
	}
	for (i = 0; i < GPUEB_MBOX_CONTROL_COUNT; i++) {
		struct resource *mbox = platform_get_resource_byname(parent, IORESOURCE_MEM,
				gpueb_resources[GPUEB_MBOX_CONTROL_FIRST + i].name);

		if (!request_mem_region(mbox->start, resource_size(mbox), dev_name(scope->parent))) {
			ret = -EBUSY;
			goto release_mbox;
		}
		scope->mbox_control[i] = mbox;
		scope->mbox_claims++;
	}
	/* Retain exclusive mailbox control claims, but do not map/read/ACK them.
	 * A future IRQ dispatcher must use this owner rather than claim them again.
	 */
	scope->registers = ioremap(resource->start, resource_size(resource));
	if (!scope->registers) {
		ret = -ENOMEM;
		goto release_mbox;
	}
	ret = request_irq(irq, unexpected_irq, IRQF_NO_AUTOEN,
			  dev_name(scope->parent), scope);
	if (ret)
		goto unmap;
	return scope;
unmap:
	iounmap(scope->registers);
release_mbox:
	release_mailbox_resources(scope);
	release_mem_region(resource->start, resource_size(resource));
put_mbox:
	mt6878_gpueb_sram_put_window(scope->mbox);
put_gpr:
	mt6878_gpueb_sram_put_window(scope->gpr);
put_pm:
	pm_runtime_put_noidle(scope->parent);
	put_device(scope->parent);
put_module:
	module_put(THIS_MODULE);
free:
	kfree(scope);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_prepare);

int mt6878_gpueb_reset_drain_irq(struct mt6878_gpueb_reset *scope)
{
	int ret;
	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	mutex_lock(&scope->lock);
	/* The exclusive IRQ is disabled since request; synchronize drains Linux
	 * handlers only. This does not drain AXI/DMA or clear pending firmware IRQs.
	 */
	synchronize_irq(scope->irq);
	ret = READ_ONCE(scope->first_error);
	if (ret)
		mt6878_gpueb_sram_unknown_start(scope->sram);
	mutex_unlock(&scope->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_drain_irq);

int mt6878_gpueb_reset_hold(struct mt6878_gpueb_reset *scope)
{
	int ret;
	unsigned long flags;
	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	mutex_lock(&scope->lock);
	synchronize_irq(scope->irq);
	spin_lock_irqsave(&scope->irq_lock, flags);
	ret = scope->first_error;
	if (ret)
		goto unlock_irq;
	if (scope->reset_written) {
		ret = -EALREADY;
		goto unlock_irq;
	}
	/* Exact B4.1 LK 0x1edf8 reset assertion. Mark uncertain before MMIO:
 * reset readback proves a latch value, never physical OFF or AXI idle.
 */
	scope->reset_written = true;
	writel(0, scope->registers + 0x600);
	if (readl(scope->registers + 0x600)) {
		scope->first_error = -EIO;
		ret = scope->first_error;
	}
unlock_irq:
	spin_unlock_irqrestore(&scope->irq_lock, flags);
	if (ret && ret != -EALREADY)
		mt6878_gpueb_sram_unknown_start(scope->sram);
	mutex_unlock(&scope->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_hold);

int mt6878_gpueb_reset_destroy(struct mt6878_gpueb_reset *scope)
{
	int ret;
	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	mutex_lock(&scope->lock);
	ret = READ_ONCE(scope->first_error);
	if (scope->reset_written || ret) {
		if (ret)
			mt6878_gpueb_sram_unknown_start(scope->sram);
		mutex_unlock(&scope->lock);
		return ret ?: -EBUSY;
	}
	free_irq(scope->irq, scope);
	iounmap(scope->registers);
	release_mailbox_resources(scope);
	release_mem_region(0x13c60000, 0x2000);
	mt6878_gpueb_sram_put_window(scope->mbox);
	mt6878_gpueb_sram_put_window(scope->gpr);
	pm_runtime_put_noidle(scope->parent);
	put_device(scope->parent);
	mutex_unlock(&scope->lock);
	kfree(scope);
	module_put(THIS_MODULE);
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_destroy);
MODULE_LICENSE("GPL");
