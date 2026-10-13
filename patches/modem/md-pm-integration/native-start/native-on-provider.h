/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after real_boot_power_on in the actual scpsys translation unit. */
#if IS_ENABLED(CONFIG_MTK_MT6878_MODEM_NATIVE_START_STAGING)
#include <linux/soc/mediatek/mt6878_md_native_on.h>

static int mt6878_md_native_on_locked(struct device *dev)
{
	struct scpsys_domain *pd = mt6878_md_real_boot_tail.pd;
	struct mt6878_md_adoption *owner = mt6878_md_first_off_owner;
	u32 top, on[5];
	unsigned int i;
	int ret;

	if (!pd || !owner || !dev || owner != mt6878_md_real_boot_tail.owner ||
	    pd->md_adoption != owner || owner->attached != dev ||
	    dev->bus != &platform_bus_type || dev->of_node != owner->modem ||
	    dev->pm_domain != &pd->genpd.domain ||
	    pd->genpd.power_on != mt6878_md_real_boot_power_on ||
	    pd->genpd.attach_dev != mt6878_md_real_boot_attach)
		return -EXDEV;
	if (owner->first_error)
		return owner->first_error;
	if (owner->state != MT6878_MD_ATTACHED_ON ||
	    mt6878_md_real_boot_tail.step != MT6878_MD_REAL_BOOT_ON_COMPLETE)
		return -EHOSTDOWN;
	ret = mt6878_md_adopt_binding(pd, owner->modem, true);
	if (!ret)
		ret = mt6878_md_adopt_revalidate_resources(pd, owner);
	if (!ret)
		ret = mt6878_md_adopt_on(pd, on);
	if (!ret)
		ret = regmap_read(mt6878_md_real_boot_tail.top.map, 0, &top);
	if (!ret && (top & MT6878_MD_POST_OFF_TOP_MASK))
		ret = -EHOSTDOWN;
	for (i = 0; !ret && i < ARRAY_SIZE(mt6878_md_real_boot_rails); i++) {
		struct regulator *rail = mt6878_md_real_boot_tail.rails[i];
		int value;

		if (IS_ERR_OR_NULL(rail)) {
			ret = -ENODEV;
			break;
		}
		value = regulator_is_enabled(rail);
		if (value <= 0) {
			ret = value < 0 ? value : -EHOSTDOWN;
			break;
		}
		value = regulator_get_voltage(rail);
		if (value < 0)
			ret = value;
		else if ((u32)value != mt6878_md_real_boot_rails[i].uv)
			ret = -EIO;
	}
	return ret ? mt6878_md_adopt_fault(owner, ret) : 0;
}

int mt6878_md_native_on_validate(struct device *consumer)
{
	struct mt6878_md_adoption *owner;
	int ret;

	mutex_lock(&mt6878_md_first_off_lock);
	owner = mt6878_md_first_off_owner;
	if (!owner) {
		ret = -ENODEV;
		goto out;
	}
	mutex_lock(&owner->lock);
	ret = mt6878_md_native_on_locked(consumer);
	mutex_unlock(&owner->lock);
out:
	mutex_unlock(&mt6878_md_first_off_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_native_on_validate);

int mt6878_md_native_on_latch(struct device *consumer, int error)
{
	struct mt6878_md_adoption *owner;
	int ret = -EXDEV;

	mutex_lock(&mt6878_md_first_off_lock);
	owner = mt6878_md_first_off_owner;
	if (owner && owner->attached == consumer) {
		mutex_lock(&owner->lock);
		ret = mt6878_md_adopt_fault(owner, error);
		mutex_unlock(&owner->lock);
	}
	mutex_unlock(&mt6878_md_first_off_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_native_on_latch);
#endif
