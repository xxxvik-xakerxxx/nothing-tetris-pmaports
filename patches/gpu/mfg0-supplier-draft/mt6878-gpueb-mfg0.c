// SPDX-License-Identifier: GPL-2.0-only
#ifndef GPUEB_MFG0_HOST_TEST
#include <linux/device.h>
#include <linux/err.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <dt-bindings/power/mediatek,mt6878-power.h>
#endif
#include "mt6878-gpueb-mfg0.h"

struct mt6878_gpueb_mfg0 {
	struct device *parent;
	struct module *parent_module;
	struct task_struct *task;
	int first_error;
	bool attempted;
};

static int mfg0_domain(struct device *dev)
{
	struct of_phandle_args supplier;
	int ret;

	if (!dev->pm_domain || !dev->of_node)
		return -EINVAL;
	if (of_count_phandle_with_args(dev->of_node, "power-domains",
				       "#power-domain-cells") != 1)
		return -EINVAL;
	ret = of_parse_phandle_with_args(dev->of_node, "power-domains",
					"#power-domain-cells", 0, &supplier);
	if (ret)
		return ret;
	ret = supplier.args_count == 1 &&
		supplier.args[0] == MT6878_POWER_DOMAIN_MFG0_SHUTDOWN &&
		of_device_is_compatible(supplier.np,
					"mediatek,mt6878-power-controller");
	of_node_put(supplier.np);
	return ret ? 0 : -EINVAL;
}

int mt6878_gpueb_mfg0_prepare(struct platform_device *parent,
	struct mt6878_gpueb_mfg0 **result)
{
	struct mt6878_gpueb_mfg0 *scope;
	struct device *dev;
	int ret;

	if (!result)
		return -EINVAL;
	*result = NULL;
	if (!parent)
		return -EINVAL;
	dev = &parent->dev;
	scope = kzalloc(sizeof(*scope), GFP_KERNEL);
	if (!scope)
		return -ENOMEM;
	if (!device_trylock(dev)) {
		ret = -EBUSY;
		goto free;
	}
	if (!device_is_bound(dev) || !dev->driver ||
	    !dev->driver->suppress_bind_attrs || !pm_runtime_enabled(dev)) {
		ret = -ENODEV;
		goto unlock;
	}
	ret = mfg0_domain(dev);
	if (ret)
		goto unlock;
	if (!try_module_get(THIS_MODULE)) {
		ret = -ENODEV;
		goto unlock;
	}
	scope->parent_module = dev->driver->owner;
	if (!try_module_get(scope->parent_module)) {
		ret = -ENODEV;
		goto put_self;
	}
	scope->parent = get_device(dev);
	scope->task = current;
	*result = scope;
	return 0;
put_self:
	module_put(THIS_MODULE);
unlock:
	device_unlock(dev);
free:
	kfree(scope);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_mfg0_prepare);

int mt6878_gpueb_mfg0_quarantine(struct mt6878_gpueb_mfg0 *scope, int error)
{
	if (IS_ERR_OR_NULL(scope) || !error)
		return -EINVAL;
	if (scope->first_error)
		return scope->first_error;
	if (scope->task != current)
		return -EPERM;
	lockdep_assert_held(&scope->parent->mutex);
	scope->first_error = error < 0 ? error : -EPROTO;
	scope->task = NULL;
	/* Quarantine lifetime references, NOT a task-owned mutex. A completed
	 * bound-parent control work item must be allowed to return on failure.
	 */
	device_unlock(scope->parent);
	return scope->first_error;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_mfg0_quarantine);

int mt6878_gpueb_mfg0_resume(struct mt6878_gpueb_mfg0 *scope)
{
	struct device *dev;
	int ret;

	if (IS_ERR_OR_NULL(scope))
		return -EINVAL;
	if (scope->first_error)
		return scope->first_error;
	if (scope->task != current)
		return -EPERM;
	if (scope->attempted)
		return -EALREADY;
	dev = scope->parent;
	lockdep_assert_held(&dev->mutex);
	scope->attempted = true;
	/* Publish ownership BEFORE the first possible genpd power write. Unlike
	 * resume_and_get, get_sync retains usage_count even on a failed resume.
	 * A genpd error can follow partial bus/SRAM/power writes; do not detach
	 * suppliers, put the reference or turn that error into successful probe.
	 */
	ret = pm_runtime_get_sync(dev);
	if (ret < 0)
		return mt6878_gpueb_mfg0_quarantine(scope, ret);
	if (!pm_runtime_active(dev))
		return mt6878_gpueb_mfg0_quarantine(scope, -EHOSTDOWN);
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_mfg0_resume);

int mt6878_gpueb_mfg0_finish(struct mt6878_gpueb_mfg0 **slot)
{
	struct mt6878_gpueb_mfg0 *scope;
	struct device *dev;

	if (!slot || IS_ERR_OR_NULL(*slot))
		return -EINVAL;
	scope = *slot;
	if (scope->first_error)
		return scope->first_error;
	if (scope->task != current)
		return -EPERM;
	dev = scope->parent;
	lockdep_assert_held(&dev->mutex);
	*slot = NULL;
	/* No physical-OFF claim or automatic power-down on registration failure.
	 * The reset helper's own reference, if acquired, remains independent.
	 */
	if (scope->attempted)
		pm_runtime_put_noidle(dev);
	device_unlock(dev);
	put_device(dev);
	module_put(scope->parent_module);
	kfree(scope);
	module_put(THIS_MODULE);
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_mfg0_finish);
MODULE_DESCRIPTION("MT6878 GPUEB cold MFG0 runtime-PM acquisition transaction");
MODULE_LICENSE("GPL");
