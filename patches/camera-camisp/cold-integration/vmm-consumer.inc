/* SPDX-License-Identifier: GPL-2.0-only */
/* Inside the original scpsys owner, after scpsys_vmm_on/off definitions. */
#include <linux/pm_runtime.h>

static struct scpsys_domain *scpsys_camera_domain(struct device *consumer,
	unsigned int domain)
{
	struct generic_pm_domain *genpd;
	struct scpsys_domain *pd;

	/* Identify our actual genpd wrapper BEFORE either container conversion. */
	if (!consumer || IS_ERR_OR_NULL(consumer->pm_domain))
		return ERR_PTR(-ENODEV);
	if (consumer->pm_domain->ops.runtime_resume != scpsys_vmm_resume)
		return ERR_PTR(-EOPNOTSUPP);
	genpd = pd_to_genpd(consumer->pm_domain);
	if (genpd->power_on != scpsys_vmm_on || genpd->power_off != scpsys_vmm_off)
		return ERR_PTR(-EOPNOTSUPP);
	pd = to_scpsys_domain(genpd);
	if (pd->scpsys->soc_data != &mt6878_scpsys_data || pd->vmm_id != domain ||
	    !scpsys_vmm_domain(pd->scpsys, domain))
		return ERR_PTR(-EINVAL);
	return pd;
}

/* Attachment only: initial OFF is legitimate; this is not a powered check. */
int mt6878_camera_vmm_validate_domain(struct device *consumer, unsigned int domain)
{
	return PTR_ERR_OR_ZERO(scpsys_camera_domain(consumer, domain));
}
EXPORT_SYMBOL_GPL(mt6878_camera_vmm_validate_domain);

int mt6878_camera_vmm_check(struct device *consumer, unsigned int domain)
{
	struct scpsys_domain *pd = scpsys_camera_domain(consumer, domain);

	if (IS_ERR(pd))
		return PTR_ERR(pd);
	/* Caller retains the real PM lease and provider lifetime across access. */
	if (!pm_runtime_enabled(consumer) || !pm_runtime_active(consumer))
		return -EHOSTDOWN;
	return mt6878_vmm_check(&pd->scpsys->vmm->supplier);
}
EXPORT_SYMBOL_GPL(mt6878_camera_vmm_check);
