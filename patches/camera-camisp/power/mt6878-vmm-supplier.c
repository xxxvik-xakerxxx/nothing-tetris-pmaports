// SPDX-License-Identifier: GPL-2.0-only
/* Shared VMM genpd supplier; deliberately not registered by any initcall. */
#include <linux/bits.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/notifier.h>

#include "mt6878-vmm-supplier.h"

#define VMM_ISO_STATUS 0x0f28
#define VMM_ISO_BITS GENMASK(26, 24)

static int vmm_fail(struct mt6878_vmm_supplier *vmm, int ret)
{
	if (!vmm->first_error) {
		vmm->first_error = ret;
		dev_err(vmm->dev, "VMM first fault: %d; recovery required\n", ret);
	}
	return vmm->first_error;
}

static int vmm_check_isolation(struct mt6878_vmm_supplier *vmm, bool isolated)
{
	u32 value;
	int ret;

	ret = regmap_read(vmm->spm, VMM_ISO_STATUS, &value);
	if (ret)
		return ret;
	return (value & VMM_ISO_BITS) == (isolated ? VMM_ISO_BITS : 0) ? 0 : -EIO;
}

static int vmm_check_rail(struct mt6878_vmm_supplier *vmm, bool on)
{
	int ret = regulator_is_enabled(vmm->buck);

	if (ret < 0)
		return ret;
	return !!ret == on ? 0 : -EIO;
}

static int vmm_power_on(struct generic_pm_domain *genpd)
{
	struct mt6878_vmm_supplier *vmm =
		container_of(genpd, struct mt6878_vmm_supplier, genpd);
	int ret;

	mutex_lock(&vmm->lock);
	if (vmm->first_error) {
		ret = vmm->first_error;
		goto out;
	}
	ret = vmm_check_rail(vmm, false);
	if (ret)
		goto fault;
	ret = vmm_check_isolation(vmm, true);
	if (ret)
		goto fault;
	ret = regulator_enable(vmm->buck);
	if (ret)
		goto fault;
	ret = vmm_check_rail(vmm, true);
	if (ret)
		goto fault;
	ret = mt6878_vmm_iso_set(vmm->spm, false);
	if (ret)
		goto fault;
	goto out;
fault:
	/* No disable unwind: a failed write may have changed hardware already. */
	ret = vmm_fail(vmm, ret);
out:
	mutex_unlock(&vmm->lock);
	return ret;
}

static int vmm_power_off(struct generic_pm_domain *genpd)
{
	struct mt6878_vmm_supplier *vmm =
		container_of(genpd, struct mt6878_vmm_supplier, genpd);
	int ret;

	mutex_lock(&vmm->lock);
	if (vmm->first_error) {
		ret = vmm->first_error;
		goto out;
	}
	ret = vmm_check_rail(vmm, true);
	if (ret)
		goto fault;
	ret = vmm_check_isolation(vmm, false);
	if (ret)
		goto fault;
	ret = mt6878_vmm_iso_set(vmm->spm, true);
	if (ret)
		goto fault;
	ret = regulator_disable(vmm->buck);
	if (ret)
		goto fault;
	/* always-on constraints must not masquerade as physical power-off. */
	ret = vmm_check_rail(vmm, false);
	if (ret)
		goto fault;
	goto out;
fault:
	/* Do not de-isolate on ABORT_DISABLE or presume the buck stayed enabled. */
	ret = vmm_fail(vmm, ret);
out:
	mutex_unlock(&vmm->lock);
	return ret;
}

int mt6878_vmm_fail_child(struct mt6878_vmm_supplier *vmm, int error)
{
	int ret;

	if (!vmm || !vmm->initialized || error >= 0)
		return -EINVAL;
	mutex_lock(&vmm->lock);
	ret = vmm_fail(vmm, error);
	mutex_unlock(&vmm->lock);
	return ret;
}

int mt6878_vmm_check(struct mt6878_vmm_supplier *vmm)
{
	int ret;

	if (!vmm || !vmm->initialized)
		return -EINVAL;
	mutex_lock(&vmm->lock);
	ret = vmm->first_error;
	if (ret)
		goto out;
	ret = vmm_check_rail(vmm, true);
	if (ret)
		goto fault;
	ret = vmm_check_isolation(vmm, false);
	if (ret)
		goto fault;
	goto out;
fault:
	ret = vmm_fail(vmm, ret);
out:
	mutex_unlock(&vmm->lock);
	return ret;
}

int mt6878_vmm_cam_ctl_set(struct mt6878_vmm_supplier *vmm,
			   unsigned int domain, bool on)
{
	int ret;

	if (!vmm || !vmm->initialized)
		return -EINVAL;
	if (domain != MT6878_POWER_DOMAIN_CAM_MAIN &&
	    domain != MT6878_POWER_DOMAIN_CAM_VCORE)
		return -EINVAL;

	/* Hold the supplier lock through the leaf write and first-error handoff. */
	mutex_lock(&vmm->lock);
	ret = vmm->first_error;
	if (ret)
		goto out;
	ret = vmm_check_rail(vmm, true);
	if (ret)
		goto fault;
	ret = vmm_check_isolation(vmm, false);
	if (ret)
		goto fault;
	ret = mt6878_cam_ctl_set(vmm->spm, domain, on);
	if (ret)
		goto fault;
	goto out;
fault:
	/* Latch the actual leaf errno before genpd notifies/unwinds its parents. */
	ret = vmm_fail(vmm, ret);
out:
	mutex_unlock(&vmm->lock);
	return ret;
}

static int vmm_child_notify(struct notifier_block *nb,
			    unsigned long event, void *data)
{
	struct mt6878_vmm_guard *guard =
		container_of(nb, struct mt6878_vmm_guard, nb);
	int ret;

	/* A failed supplier OFF leaves genpd logically ON and skips power_on. */
	if (event == GENPD_NOTIFY_PRE_ON || event == GENPD_NOTIFY_PRE_OFF) {
		ret = mt6878_vmm_check(guard->supplier);
		if (!ret) {
			guard->pending = event;
			guard->transitioning = true;
		}
		return notifier_from_errno(ret);
	}

	/* Robust notifier rollback also reaches here; block retries conservatively. */
	if (event != GENPD_NOTIFY_ON && event != GENPD_NOTIFY_OFF)
		return NOTIFY_DONE;
	ret = 0;
	if (guard->transitioning &&
	    ((event == GENPD_NOTIFY_OFF && guard->pending == GENPD_NOTIFY_PRE_ON) ||
	     (event == GENPD_NOTIFY_ON && guard->pending == GENPD_NOTIFY_PRE_OFF)))
		ret = mt6878_vmm_fail_child(guard->supplier, -EIO);
	guard->transitioning = false;
	return notifier_from_errno(ret);
}

int mt6878_vmm_supplier_init(struct mt6878_vmm_supplier *vmm,
			     struct device *dev, const char *supply_id,
			     struct regmap *spm,
			     struct generic_pm_domain *mm_infra)
{
	int ret, enabled;

	if (!vmm || !dev || !supply_id || !*supply_id ||
	    IS_ERR_OR_NULL(spm) || !mm_infra)
		return -EINVAL;
	if (mm_infra == &vmm->genpd || (mm_infra->flags & GENPD_FLAG_IRQ_SAFE))
		return -EINVAL;
	if (vmm->buck)
		return vmm->first_error ? vmm->first_error : -EBUSY;

	mutex_init(&vmm->lock);
	vmm->dev = dev;
	vmm->spm = spm;
	/* No dummy fallback; reject existing CAM, ISP, notifier or DVFS handles. */
	vmm->buck = regulator_get_exclusive(dev, supply_id);
	if (IS_ERR(vmm->buck)) {
		ret = PTR_ERR(vmm->buck);
		vmm->buck = NULL;
		return ret;
	}
	/*
	 * Exclusive get can adopt an inherited enable reference. Do not guess
	 * which inherited CAM/ISP users own it, or disable it during failed init.
	 */
	enabled = regulator_is_enabled(vmm->buck);
	if (enabled < 0)
		return vmm_fail(vmm, enabled);
	if (enabled)
		return vmm_fail(vmm, -EBUSY);
	ret = vmm_check_isolation(vmm, true);
	if (ret)
		return vmm_fail(vmm, ret);

	vmm->genpd.name = "mt6878-vmm";
	vmm->genpd.power_on = vmm_power_on;
	vmm->genpd.power_off = vmm_power_off;
	ret = pm_genpd_init(&vmm->genpd, NULL, !enabled);
	if (ret)
		return vmm_fail(vmm, ret);
	/* A faulted ON VMM must retain MM_INFRA during child failure unwind. */
	ret = pm_genpd_add_subdomain(mm_infra, &vmm->genpd);
	if (ret)
		return vmm_fail(vmm, ret);
	vmm->initialized = true;
	return 0;
}

int mt6878_vmm_add_child(struct mt6878_vmm_supplier *vmm,
			 struct generic_pm_domain *child, struct device *guard_dev,
			 struct mt6878_vmm_guard *guard)
{
	int ret;

	if (!vmm || !child || !guard_dev || !guard || !vmm->initialized)
		return -EINVAL;
	if (vmm->first_error)
		return vmm->first_error;
	if (guard->registered || guard->linked)
		return -EBUSY;
	if (child == &vmm->genpd || guard_dev->pm_domain != &child->domain ||
	    child->status != GENPD_STATE_OFF || (child->flags & GENPD_FLAG_IRQ_SAFE))
		return -EINVAL;

	guard->supplier = vmm;
	guard->nb.notifier_call = vmm_child_notify;
	ret = dev_pm_genpd_add_notifier(guard_dev, &guard->nb);
	if (ret)
		return ret;
	guard->registered = true;
	ret = pm_genpd_add_subdomain(&vmm->genpd, child);
	if (ret)
		return vmm_fail(vmm, ret);
	guard->linked = true;
	return 0;
}
