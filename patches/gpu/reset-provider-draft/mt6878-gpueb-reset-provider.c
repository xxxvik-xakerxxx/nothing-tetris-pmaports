// SPDX-License-Identifier: GPL-2.0-only
#include <linux/device.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/kconfig.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/reset-controller.h>
#include <linux/slab.h>
#include "mt6878-gpueb-sram.h"
#include "mt6878-gpueb-reset.h"
#include "mt6878-gpueb-reset-provider.h"

struct mt6878_gpueb_reset_provider {
	struct reset_controller_dev controller;
	struct mt6878_gpueb_reset *scope;
	struct mt6878_gpueb_sram *sram;
	struct mutex lock;
	int first_error;
	bool asserted;
};

static int first_failure(struct mt6878_gpueb_reset_provider *provider, int error)
{
	if (!provider->first_error)
		provider->first_error = error < 0 ? error : -EPROTO;
	return provider->first_error;
}

/* Caller holds provider->lock. Quarantine precedes the first possible write;
 * even a failed reset readback cannot authorize disposal of firmware memory.
 */
static int assert_owned(struct mt6878_gpueb_reset_provider *provider)
{
	int ret;

	if (provider->first_error)
		return provider->first_error;
	if (provider->asserted)
		return -EALREADY;
	ret = mt6878_gpueb_sram_unknown_start(provider->sram);
	if (ret)
		return first_failure(provider, ret);
	ret = mt6878_gpueb_reset_hold(provider->scope);
	if (ret)
		return first_failure(provider, ret);
	provider->asserted = true;
	return 0;
}

static int provider_assert(struct reset_controller_dev *controller,
			   unsigned long id)
{
	struct mt6878_gpueb_reset_provider *provider = container_of(controller,
			struct mt6878_gpueb_reset_provider, controller);
	int ret;

	if (id)
		return -EINVAL;
	mutex_lock(&provider->lock);
	ret = assert_owned(provider);
	mutex_unlock(&provider->lock);
	return ret;
}

/* Deliberately no deassert/reset/status: entry/map/BOOTREADY and physical OFF
 * remain unproven. Standard reset-core absence must not be replaced by success.
 */
static const struct reset_control_ops provider_ops = {
	.assert = provider_assert,
};

struct mt6878_gpueb_reset_provider *mt6878_gpueb_reset_provider_register(
	struct platform_device *parent, struct mt6878_gpueb_sram *sram)
{
	struct mt6878_gpueb_reset_provider *provider;
	struct module *parent_module;
	u32 cells;
	int ret, cleanup;

	/* reset-controller.h otherwise supplies a successful no-op registration. */
	if (!IS_ENABLED(CONFIG_RESET_CONTROLLER))
		return ERR_PTR(-ENODEV);
	if (!parent || IS_ERR_OR_NULL(sram) || !parent->dev.driver ||
	    !parent->dev.driver->suppress_bind_attrs || !parent->dev.of_node)
		return ERR_PTR(-EINVAL);
	ret = of_property_read_u32(parent->dev.of_node, "#reset-cells", &cells);
	if (ret || cells != 1)
		return ERR_PTR(ret ?: -EINVAL);
	provider = kzalloc(sizeof(*provider), GFP_KERNEL);
	if (!provider)
		return ERR_PTR(-ENOMEM);
	mutex_init(&provider->lock);
	parent_module = parent->dev.driver->owner;
	if (!try_module_get(THIS_MODULE)) {
		ret = -ENODEV;
		goto free;
	}
	if (!try_module_get(parent_module)) {
		ret = -ENODEV;
		goto put_module;
	}
	/* Frozen helper validates attached MFG0, borrows an active PM reference,
	 * claims the exact control bank and both unified-SRAM typed windows, and
	 * requests the exclusive disabled SPI273. No new claim overlaps its bank.
	 */
	provider->scope = mt6878_gpueb_reset_prepare(parent, sram);
	if (IS_ERR(provider->scope)) {
		ret = PTR_ERR(provider->scope);
		goto put_parent;
	}
	provider->sram = sram;
	provider->controller.owner = THIS_MODULE;
	provider->controller.ops = &provider_ops;
	provider->controller.of_node = parent->dev.of_node;
	provider->controller.of_reset_n_cells = 1;
	provider->controller.nr_resets = 1;
	provider->controller.dev = &parent->dev;
	ret = reset_controller_register(&provider->controller);
	if (ret) {
		cleanup = mt6878_gpueb_reset_destroy(provider->scope);
		if (cleanup) {
			/* An unexpected IRQ can quarantine even before publication.
			 * Preserve all pins and the scope, not a blind devm unwind.
			 */
			mt6878_gpueb_sram_unknown_start(sram);
			dev_err(&parent->dev, "reset publication=%d cleanup=%d; retained\n",
				ret, cleanup);
			return ERR_PTR(ret);
		}
		goto put_parent;
	}
	/* No devm registration/removal: consumers and all supplier pins remain
	 * alive through this diagnostic boot, including unknown partial starts.
	 */
	return provider;
put_parent:
	module_put(parent_module);
put_module:
	module_put(THIS_MODULE);
free:
	kfree(provider);
	return ERR_PTR(ret);
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_provider_register);

int mt6878_gpueb_reset_provider_stop(struct mt6878_gpueb_reset_provider *provider)
{
	int ret;

	if (IS_ERR_OR_NULL(provider))
		return -EINVAL;
	mutex_lock(&provider->lock);
	if (provider->first_error) {
		ret = provider->first_error;
		goto out;
	}
	if (!provider->asserted) {
		ret = assert_owned(provider);
		if (ret)
			goto out;
	}
	ret = mt6878_gpueb_reset_drain_irq(provider->scope);
	if (ret)
		ret = first_failure(provider, ret);
	else
		/* Never let remoteproc mark OFFLINE/free DMA based on reset echo. */
		ret = first_failure(provider, -EBUSY);
out:
	mutex_unlock(&provider->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_reset_provider_stop);
MODULE_DESCRIPTION("MT6878 GPUEB parent-owned reset assertion and stop containment");
MODULE_LICENSE("GPL");
