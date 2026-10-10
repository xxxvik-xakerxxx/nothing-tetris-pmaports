/* SPDX-License-Identifier: GPL-2.0-only */
/* Included in clk-mt6878-cam.c; drvdata remains the real clock onecell. */
#include <linux/mfd/syscon.h>
#include <linux/of.h>
#include <linux/pm_runtime.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <soc/mediatek/cam-main-lease.h>

static struct platform_driver clk_mt6878_cam_drv;

struct mt6878_cam_main_lease {
	struct device *supplier;
	struct regmap *regmap;
	struct task_struct *task;
};

static int cam_main_lease_check(struct mt6878_cam_main_lease *lease)
{
	if (!lease || !lease->supplier || IS_ERR_OR_NULL(lease->regmap))
		return -EINVAL;
	if (lease->task != current)
		return -EPERM;
	lockdep_assert_held(&lease->supplier->mutex);
	if (lease->supplier->driver != &clk_mt6878_cam_drv.driver ||
	    !device_is_bound(lease->supplier))
		return -ENODEV;
	if (!pm_runtime_enabled(lease->supplier) ||
	    !pm_runtime_active(lease->supplier))
		return -EHOSTDOWN;
	return 0;
}

int mt6878_cam_main_prepare(struct device *supplier,
	struct mt6878_cam_main_lease **result)
{
	struct mt6878_cam_main_lease *lease;
	struct regmap *map;
	int ret;

	if (!result)
		return -EINVAL;
	*result = NULL;
	if (!supplier || !supplier->of_node)
		return -EINVAL;
	lease = kzalloc(sizeof(*lease), GFP_KERNEL);
	if (!lease)
		return -ENOMEM;
	/* Never wait behind supplier removal while holding consumer locks. */
	if (!device_trylock(supplier)) {
		ret = -EBUSY;
		goto free;
	}
	if (supplier->driver != &clk_mt6878_cam_drv.driver ||
	    !device_is_bound(supplier)) {
		ret = -ENODEV;
		goto unlock;
	}
	if (!pm_runtime_enabled(supplier)) {
		ret = -EHOSTDOWN;
		goto unlock;
	}
	/* clk-gate.c has already populated the syscon registry. Refuse generic
	 * syscon nodes: that lookup could create a new mapping on a failed bind.
	 */
	if (of_device_is_compatible(supplier->of_node, "syscon")) {
		ret = -EOPNOTSUPP;
		goto unlock;
	}
	map = syscon_node_to_regmap(supplier->of_node);
	if (IS_ERR(map)) {
		ret = PTR_ERR(map);
		goto unlock;
	}
	if (!try_module_get(THIS_MODULE)) {
		ret = -ENODEV;
		goto unlock;
	}
	ret = pm_runtime_get_sync(supplier);
	if (ret < 0) {
		pm_runtime_put_noidle(supplier);
		goto put_module;
	}
	if (!pm_runtime_active(supplier)) {
		ret = -EHOSTDOWN;
		pm_runtime_put_sync(supplier);
		goto put_module;
	}
	lease->supplier = get_device(supplier);
	lease->regmap = map;
	lease->task = current;
	*result = lease;
	return 0; /* Device mutex remains held by this task until retire. */

put_module:
	module_put(THIS_MODULE);
unlock:
	device_unlock(supplier);
free:
	kfree(lease);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_cam_main_prepare);

struct regmap *mt6878_cam_main_regmap(struct mt6878_cam_main_lease *lease)
{
	int ret = cam_main_lease_check(lease);

	return ret ? ERR_PTR(ret) : lease->regmap;
}
EXPORT_SYMBOL_GPL(mt6878_cam_main_regmap);

int mt6878_cam_main_reset_pulse(struct mt6878_cam_main_lease *lease,
	unsigned int sv_id)
{
	int ret = cam_main_lease_check(lease);

	if (ret)
		return ret;
	(void)sv_id; /* No engine can bypass the missing joint reset owner. */
	/* e96 sv_reset_by_camsys_top requires SMI clamp and SCQ poll BEFORE
	 * CAM_MAIN 0x58. No public supplier API proves both on this lease.
	 */
	return -EOPNOTSUPP;
}
EXPORT_SYMBOL_GPL(mt6878_cam_main_reset_pulse);

int mt6878_cam_main_retire(struct mt6878_cam_main_lease **slot)
{
	struct mt6878_cam_main_lease *lease;
	struct device *supplier;
	int ret;

	if (!slot || !*slot)
		return -EINVAL;
	lease = *slot;
	if (lease->task != current)
		return -EPERM; /* Never unlock another task's supplier mutex. */
	supplier = lease->supplier;
	lockdep_assert_held(&supplier->mutex);
	/* Only synchronous register access is allowed. Invalidate caller's
	 * handle before dropping PM; no DMA/callback lifetime is inferred.
	 */
	*slot = NULL;
	lease->regmap = NULL;
	ret = pm_runtime_put_sync(supplier);
	device_unlock(supplier);
	put_device(supplier);
	kfree(lease);
	module_put(THIS_MODULE);
	return ret < 0 ? ret : 0;
}
EXPORT_SYMBOL_GPL(mt6878_cam_main_retire);

static int cam_main_lease_probe(struct platform_device *pdev)
{
	int ret;

	/* Native genpd performs the real power transition, not a fake status. */
	pm_runtime_enable(&pdev->dev);
	/* Same registration/genpd deadlock avoidance as clk-mtk.c's PM path. */
	ret = pm_runtime_resume_and_get(&pdev->dev);
	if (ret < 0)
		goto disable_pm;
	ret = mtk_clk_simple_probe(pdev);
	pm_runtime_put(&pdev->dev);
	if (!ret)
		return 0;
disable_pm:
	pm_runtime_disable(&pdev->dev);
	return ret;
}

static void cam_main_lease_remove(struct platform_device *pdev)
{
	/* Driver core holds device_lock, so synchronous leases have retired.
	 * No raw mapping/devm lifetime is owned by this extension.
	 */
	lockdep_assert_held(&pdev->dev.mutex);
	mtk_clk_simple_remove(pdev);
	pm_runtime_disable(&pdev->dev);
}

#if IS_ENABLED(CONFIG_KUNIT)
#include "cam-main-lease-test.inc"
#endif
