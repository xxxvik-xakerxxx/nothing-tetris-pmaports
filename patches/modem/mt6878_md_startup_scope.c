// SPDX-License-Identifier: GPL-2.0-only
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/overflow.h>
#include <linux/platform_device.h>
#include <linux/sched.h>
#include <linux/string.h>
#include <linux/soc/mediatek/mt6878_md_startup_scope.h>

static DEFINE_MUTEX(md_scope_lock);
static struct {
	struct device *supplier;
	struct device_driver *driver;
	void *supplier_data;
	resource_size_t supplier_start, supplier_end;
	unsigned long supplier_flags;
	struct task_struct *task;
	struct mt6878_md_handoff_owner auth;
	void *auth_owner;
	struct mt6878_md_handoff_state handoff;
	unsigned long init_status;
	int first_error;
	bool initialized, attempted, execution_checked;
} md_scope;

static int md_scope_fault(int error)
{
	if (!md_scope.first_error)
		md_scope.first_error = error < 0 ? error : -EPROTO;
	return md_scope.first_error;
}

int mt6878_md_scoped_dvfsrc_init(struct device *dev, u32 flags, u32 vmode,
			       struct arm_smccc_res *result)
{
	struct resource *resource;
	int ret = 0;

	if (!dev || !dev->driver || !result)
		return -EINVAL;
	if (dev->bus != &platform_bus_type)
		return -EINVAL;
	resource = platform_get_resource(to_platform_device(dev), IORESOURCE_MEM, 0);
	if (!resource || resource->end < resource->start)
		return -EINVAL;
	if (READ_ONCE(md_scope.task) == current)
		return -EBUSY;
	mutex_lock(&md_scope_lock);
	if (md_scope.first_error) {
		ret = md_scope.first_error;
		goto out;
	}
	if (md_scope.attempted || (md_scope.supplier && md_scope.supplier != dev)) {
		ret = -EBUSY;
		goto out;
	}
	/* Exact pinned VCOREFS INIT: not a generic SMC pass-through. */
	arm_smccc_smc(0xc2000506, 0, flags, vmode, 0, 0, 0, 0, result);
	if (!md_scope.supplier)
		md_scope.supplier = get_device(dev);
	md_scope.driver = dev->driver;
	md_scope.supplier_start = resource->start;
	md_scope.supplier_end = resource->end;
	md_scope.supplier_flags = resource->flags;
	md_scope.init_status = result->a0;
	md_scope.initialized = true;
	if (result->a0)
		md_scope_fault(-EPROTO); /* Preserve raw status separately; not errno. */
out:
	mutex_unlock(&md_scope_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_scoped_dvfsrc_init);

static int md_scope_resource(void)
{
	struct resource *resource = platform_get_resource(
		to_platform_device(md_scope.supplier), IORESOURCE_MEM, 0);

	if (!resource || resource->start != md_scope.supplier_start ||
	    resource->end != md_scope.supplier_end || resource->flags != md_scope.supplier_flags)
		return -ESTALE;
	return 0;
}

static int md_scope_snapshot(struct mt6878_md_handoff_state *state)
{
	u64 rom_end, smem_end;
	int ret;

	memset(state, 0, sizeof(*state));
	ret = md_scope.auth.snapshot(md_scope.auth_owner, state);
	if (ret)
		return ret < 0 ? ret : -EPROTO;
	if (!state->rom_size || !state->smem_size ||
	    check_add_overflow(state->rom_base, state->rom_size, &rom_end) ||
	    check_add_overflow(state->smem_base, state->smem_size, &smem_end) ||
	    (state->rom_base < smem_end && state->smem_base < rom_end))
		return -EINVAL;
	return 0;
}

int mt6878_md_scope_begin(const struct mt6878_md_handoff_owner *auth, void *owner)
{
	struct device *dev;
	int ret;

	if (!auth || !auth->snapshot || !auth->authenticate || !owner)
		return -ENOKEY;
	if (READ_ONCE(md_scope.task) == current)
		return -EALREADY;
	/* Driver probe takes device_lock before this mutex. Never invert that order. */
	mutex_lock(&md_scope_lock);
	dev = get_device(md_scope.supplier);
	mutex_unlock(&md_scope_lock);
	if (!dev)
		return -EPROBE_DEFER;
	device_lock(dev);
	mutex_lock(&md_scope_lock);
	if (md_scope.first_error) {
		ret = md_scope.first_error;
		goto unlock;
	}
	if (md_scope.attempted) {
		ret = -EALREADY;
		goto unlock;
	}
	md_scope.attempted = true;
	if (dev != md_scope.supplier || !md_scope.initialized || md_scope.init_status ||
	    !dev->driver || dev->driver != md_scope.driver || !dev_get_drvdata(dev)) {
		ret = md_scope_fault(-ENODEV);
		goto unlock;
	}
	if (!try_module_get(auth->module)) {
		ret = md_scope_fault(-ENODEV);
		goto unlock;
	}
	md_scope.auth = *auth;
	md_scope.auth_owner = owner;
	md_scope.supplier_data = dev_get_drvdata(dev);
	ret = md_scope_resource();
	if (!ret)
		ret = md_scope_snapshot(&md_scope.handoff);
	if (!ret)
		ret = md_scope.auth.authenticate(owner, &md_scope.handoff);
	if (ret) {
		ret = md_scope_fault(ret);
		module_put(auth->module);
		goto unlock;
	}
	WRITE_ONCE(md_scope.task, current);
	/* Retain both locks and the device reference through first-start execution. */
	return 0;
unlock:
	mutex_unlock(&md_scope_lock);
	device_unlock(dev);
	put_device(dev);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_scope_begin);

int mt6878_md_scope_validate_execution(void)
{
	struct mt6878_md_handoff_state now;
	int ret;

	if (READ_ONCE(md_scope.task) != current)
		return -EPERM;
	if (md_scope.first_error)
		return md_scope.first_error;
	if (md_scope.supplier->driver != md_scope.driver ||
	    dev_get_drvdata(md_scope.supplier) != md_scope.supplier_data)
		return md_scope_fault(-ESTALE);
	ret = md_scope_resource();
	if (!ret)
		ret = md_scope_snapshot(&now);
	if (!ret && (now.rom_base != md_scope.handoff.rom_base ||
	    now.rom_size != md_scope.handoff.rom_size ||
	    now.smem_base != md_scope.handoff.smem_base ||
	    now.smem_size != md_scope.handoff.smem_size ||
	    memcmp(now.rom_digest, md_scope.handoff.rom_digest, sizeof(now.rom_digest))))
		ret = -ESTALE;
	if (!ret)
		ret = md_scope.auth.authenticate(md_scope.auth_owner, &now);
	if (ret)
		return md_scope_fault(ret);
	md_scope.execution_checked = true;
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_md_scope_validate_execution);

int mt6878_md_scope_end(int result)
{
	struct device *dev;
	int ret;

	if (READ_ONCE(md_scope.task) != current)
		return -EPERM;
	if (result)
		md_scope_fault(result);
	else if (!md_scope.execution_checked)
		md_scope_fault(-EPROTO);
	ret = md_scope.first_error;
	dev = md_scope.supplier;
	WRITE_ONCE(md_scope.task, NULL);
	module_put(md_scope.auth.module);
	mutex_unlock(&md_scope_lock);
	device_unlock(dev);
	put_device(dev);
	/* INIT remains rejected for this boot. No compensating SMC/idle/reset. */
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_scope_end);

MODULE_LICENSE("GPL");
