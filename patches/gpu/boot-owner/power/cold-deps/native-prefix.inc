/* SPDX-License-Identifier: GPL-2.0-only */
/* Native MFG0 acquisition prefix, not a GPUEB rail/boot-clock producer.
 * Zero optional supplier clocks and an absent optional regulator are permitted
 * by the matching NOS domain. Neither absence nor presence proves GPUEB power.
 */
static struct scpsys_domain *mt6878_cold_mfg0(struct device *dev)
{
	struct generic_pm_domain *genpd;
	struct scpsys_domain *pd;

	if (!dev || !dev->pm_domain || !dev_gpd_data(dev))
		return ERR_PTR(-ENODEV);
	lockdep_assert_held(&dev->mutex);
	genpd = pd_to_genpd(dev->pm_domain);
	if (genpd->power_on != scpsys_power_on || genpd->power_off != scpsys_power_off ||
	    (genpd->flags & GENPD_FLAG_IRQ_SAFE))
		return ERR_PTR(-ENODEV);
	pd = to_scpsys_domain(genpd);
	if (pd->scpsys->soc_data != &mt6878_scpsys_data ||
	    pd->data != &scpsys_domain_data_mt6878[MT6878_POWER_DOMAIN_MFG0_SHUTDOWN])
		return ERR_PTR(-ENODEV);
	return pd;
}

int mt6878_cold_mfg0_preflight(struct device *dev)
{
	struct scpsys_domain *pd = mt6878_cold_mfg0(dev);

	return IS_ERR(pd) ? PTR_ERR(pd) : 0;
}
EXPORT_SYMBOL_GPL(mt6878_cold_mfg0_preflight);

int mt6878_cold_mfg0_readback(struct device *dev)
{
	struct scpsys_domain *pd = mt6878_cold_mfg0(dev);
	static const u32 en_offsets[] = { 0x0ca0, 0x0c40 };
	u32 ctl, enabled;
	unsigned int i;
	int ret;

	if (IS_ERR(pd))
		return PTR_ERR(pd);
	mutex_lock(&pd->genpd.mlock);
	if (pd->genpd.status != GENPD_STATE_ON) {
		ret = -EHOSTDOWN;
		goto out;
	}
	ret = regmap_read(pd->scpsys->base, pd->data->ctl_offs, &ctl);
	if (ret)
		goto out;
	/* Signed B4.1 LK 1ebc8..1ebe0: ACK[31:30]=3, PDN_ACK[12]=0,
	 * and bit13 MUST BE SET to branch to 1ec54. Never guess its producer.
	 */
	if ((ctl & (GENMASK(31, 30) | BIT(12) | BIT(13))) !=
	    (GENMASK(31, 30) | BIT(13))) {
		dev_err(dev, "MFG0 prefix: SPM=%#x lacks LK pre-RPC SRAM state\n", ctl);
		ret = -EHOSTDOWN;
		goto out;
	}
	/* Check native control effects separately from the LK ACK admission. */
	if ((ctl & (BIT(0) | BIT(2) | BIT(3) | BIT(6))) !=
	    (BIT(0) | BIT(2) | BIT(3) | BIT(6)) ||
	    (ctl & (BIT(1) | BIT(4) | BIT(5) | BIT(8)))) {
		ret = -EHOSTDOWN;
		goto out;
	}
	for (i = 0; i < ARRAY_SIZE(en_offsets); i++) {
		const struct scpsys_bus_prot_data *bpd = &pd->data->bp_cfg[i];
		struct regmap *map = scpsys_bus_protect_get_regmap(pd, bpd);

		if (IS_ERR_OR_NULL(map)) {
			ret = -ENODEV;
			goto out;
		}
		ret = regmap_read(map, en_offsets[i], &enabled);
		if (ret)
			goto out;
		/* NOS ignores clear ACK; read the actual enable register instead.
		 * No guessed ACK poll or second bus-protection writer is added.
		 */
		if (enabled & bpd->bus_prot_set_clr_mask) {
			dev_err(dev, "MFG0 prefix: bus enable %#x=%#x remains protected\n",
				en_offsets[i], enabled);
			ret = -EHOSTDOWN;
			goto out;
		}
	}
	ret = 0;
out:
	mutex_unlock(&pd->genpd.mlock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_cold_mfg0_readback);
