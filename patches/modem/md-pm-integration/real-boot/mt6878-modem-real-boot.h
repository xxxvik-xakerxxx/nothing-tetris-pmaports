/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the retained native first-OFF helpers, before adopt_init. */
#ifndef MT6878_MODEM_REAL_BOOT_H
#define MT6878_MODEM_REAL_BOOT_H

#include <linux/arm-smccc.h>
#include <linux/soc/mediatek/mtk_sip_svc.h>
#include <linux/regulator/consumer.h>
#include <linux/suspend.h>
#include "mt6878-modem-post-off.h"

/* ee2be53 modem_secure_base.h + mtk_sip_svc.h; no upstream CCCI definition. */
#define MT6878_MD_REAL_BOOT_SMC MTK_SIP_SMC_CMD(0x505)
#define MT6878_MD_REAL_BOOT_FLIGHT 7

enum mt6878_md_real_boot_step {
	MT6878_MD_REAL_BOOT_UNUSED,
	MT6878_MD_REAL_BOOT_TOP_ACQUIRE,
	MT6878_MD_REAL_BOOT_OFF_READBACK,
	MT6878_MD_REAL_BOOT_FLIGHT_SUBMIT,
	MT6878_MD_REAL_BOOT_TOP_GATE,
	MT6878_MD_REAL_BOOT_POST_OFF_GATED,
	MT6878_MD_REAL_BOOT_ON_RAILS,
	MT6878_MD_REAL_BOOT_ON_TOP,
	MT6878_MD_REAL_BOOT_ON_FLIGHT,
	MT6878_MD_REAL_BOOT_ON_ISOLATION,
	MT6878_MD_REAL_BOOT_ON_POWER,
	MT6878_MD_REAL_BOOT_ON_BUS,
	MT6878_MD_REAL_BOOT_ON_READBACK,
	MT6878_MD_REAL_BOOT_ON_COMPLETE,
};

/* One boot-lifetime sidecar, including failure. Steps describe attempts only. */
static struct {
	struct mt6878_md_adoption *owner;
	struct mt6878_md_post_off_top top;
	unsigned long flight_off_a0, flight_on_a0;
	struct device_node *rail_nodes[3];
	struct regulator *rails[3];
	struct device *rail_consumer;
	u32 off[5], on[5], top_on;
	enum mt6878_md_real_boot_step step;
} mt6878_md_real_boot_tail;

/*
 * Matching ATF SHA05a247 kernel dispatch zero-extends the inner w0 result.
 * Only a0 is defined: a1..a3 are not an output payload. Nonzero stops this
 * operation; retain the raw value instead of casting it to a Linux errno.
 * Zero does not prove policy applied (null callback also returns zero), outer
 * admission, execution inhibition or modem readiness. ON readbacks are separate.
 */
static int mt6878_md_real_boot_flight_submit(struct device *supplier,
					   unsigned int mode,
					   unsigned long *a0)
{
	struct arm_smccc_res res;

	arm_smccc_smc(MT6878_MD_REAL_BOOT_SMC, MT6878_MD_REAL_BOOT_FLIGHT,
		      mode, 0, 0, 0, 0, 0, &res);
	*a0 = res.a0;
	dev_info(supplier,
		 "MD FLIGHT(%u) returned a0=%#lx; policy operation only, not modem readiness\n",
		 mode, *a0);
	return *a0 ? -EIO : 0;
}

/*
 * Called by native supplier probe immediately after physical first-OFF.
 * This profile has no UFS calibration provider: no hold was acquired and
 * there is no PM reference to release. Do not import the vendor release API.
 * The frozen first-OFF already waited >=4ms after MTCMOS/isolation; the final
 * readback below precedes FLIGHT and the source-ordered checked TOP gate.
 */
static int mt6878_md_real_boot_post_off(struct scpsys_domain *pd,
				      struct mt6878_md_adoption *owner)
{
	int ret;

	if (!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING) ||
	    !IS_ENABLED(CONFIG_MTK_MT6878_MODEM_POST_OFF_TOP_STAGING) ||
	    IS_ENABLED(CONFIG_SCSI_UFS_MEDIATEK_DBG))
		return -EOPNOTSUPP;
	if (!pd || !owner)
		return -EINVAL;
	mutex_lock(&mt6878_md_first_off_lock);
	mutex_lock(&owner->lock);
	ret = mt6878_md_post_off_owner(pd, owner);
	if (ret)
		goto out;
	if (!mutex_trylock(&system_transition_mutex)) {
		ret = mt6878_md_adopt_fault(owner, -EBUSY);
		goto out;
	}
	if (mt6878_md_real_boot_tail.owner) {
		ret = mt6878_md_real_boot_tail.owner == owner ? -EALREADY : -EXDEV;
		goto transition_out;
	}
	/* Reject the obsolete inhibited-restart promise, not intentional execution. */
	if (of_property_present(pd->scpsys->dev->of_node,
				"nothing,modem-inhibited-restart-staging")) {
		ret = -EBUSY;
		goto fault;
	}
	mt6878_md_real_boot_tail.owner = owner;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_TOP_ACQUIRE;
	ret = mt6878_md_post_off_top_acquire(pd, owner, &mt6878_md_real_boot_tail.top);
	if (ret)
		goto fault;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_OFF_READBACK;
	ret = mt6878_md_first_off_readback(pd, mt6878_md_real_boot_tail.off);
	if (ret)
		goto fault;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_FLIGHT_SUBMIT;
	ret = mt6878_md_real_boot_flight_submit(owner->supplier, 1,
					     &mt6878_md_real_boot_tail.flight_off_a0);
	if (ret)
		goto fault;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_TOP_GATE;
	ret = mt6878_md_post_off_top_gate(pd, owner, &mt6878_md_real_boot_tail.top);
	if (ret)
		goto fault;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_POST_OFF_GATED;
	ret = 0;
	goto transition_out;
fault:
	ret = mt6878_md_adopt_fault(owner, ret);
	dev_err(pd->scpsys->dev,
		"MD genuine-boot continuation failed at step %u: %d; owner and FLIGHT a0 retained, reboot required\n",
		mt6878_md_real_boot_tail.step, ret);
transition_out:
	mutex_unlock(&system_transition_mutex);
out:
	mutex_unlock(&owner->lock);
	mutex_unlock(&mt6878_md_first_off_lock);
	return ret;
}

static const struct {
	const char *name, *supply, *node_name;
	u32 uv;
} mt6878_md_real_boot_rails[] = {
	{ "md-vmodem", "md-vmodem-supply", "vbuck2", 800000 },
	{ "md-vsram", "md-vsram-supply", "vsram-modem", 800000 },
	{ "md-vdigrf", "md-vdigrf-supply", "vbuck1", 700000 },
};

/* Validate all inputs before any regulator acquisition, which can affect parents. */
static int mt6878_md_real_boot_rail_profile(struct mt6878_md_adoption *owner)
{
	struct device_node *modem = owner->modem, *node;
	u32 uv[2];
	unsigned int i, j;
	int ret;

	if (of_property_present(modem, "mediatek,srclken-o1") ||
	    of_property_present(modem, "md-vnr-supply") ||
	    of_property_present(modem, "md-vmdfe-supply"))
		return -EOPNOTSUPP;
	if (of_property_present(modem, "mediatek,power-flow-config") &&
	    mt6878_md_adopt_scalar(modem, "mediatek,power-flow-config", 0))
		return -EOPNOTSUPP;
	for (i = 0; i < ARRAY_SIZE(mt6878_md_real_boot_rails); i++) {
		if (of_count_phandle_with_args(modem, mt6878_md_real_boot_rails[i].supply, NULL) != 1 ||
		    of_property_count_u32_elems(modem, mt6878_md_real_boot_rails[i].name) != 2)
			return -EINVAL;
		ret = of_property_read_u32_array(modem, mt6878_md_real_boot_rails[i].name, uv, 2);
		if (ret)
			return ret;
		if (uv[0] != mt6878_md_real_boot_rails[i].uv || uv[1] != uv[0])
			return -EOPNOTSUPP;
		node = of_parse_phandle(modem, mt6878_md_real_boot_rails[i].supply, 0);
		mt6878_md_real_boot_tail.rail_nodes[i] = node;
		if (!node || !of_device_is_available(node))
			return -ENODEV;
		if (strcmp(node->name, mt6878_md_real_boot_rails[i].node_name) ||
		    !of_device_is_compatible(node->parent, "mediatek,mt6363-regulator"))
			return -EXDEV;
		for (j = 0; j < i; j++)
			if (node == mt6878_md_real_boot_tail.rail_nodes[j])
				return -EINVAL;
	}
	return 0;
}

/* Source uses voltage/sync, not invented enable writes or a guessed SRAM delay. */
static int mt6878_md_real_boot_set_rails(struct mt6878_md_adoption *owner)
{
	struct regulator *rail;
	unsigned int i;
	int ret;

	ret = mt6878_md_real_boot_rail_profile(owner);
	if (ret)
		return ret;
	mt6878_md_real_boot_tail.rail_consumer = get_device(owner->attached);
	for (i = 0; i < ARRAY_SIZE(mt6878_md_real_boot_rails); i++) {
		rail = of_regulator_get_optional(mt6878_md_real_boot_tail.rail_consumer, owner->modem,
						 mt6878_md_real_boot_rails[i].name);
		mt6878_md_real_boot_tail.rails[i] = rail;
		if (IS_ERR_OR_NULL(rail))
			return rail ? PTR_ERR(rail) : -ENODEV;
		/* First-OFF did not disable these inherited rails; require real enable. */
		ret = regulator_is_enabled(rail);
		if (ret <= 0)
			return ret < 0 ? ret : -EHOSTDOWN;
		ret = regulator_set_voltage(rail, mt6878_md_real_boot_rails[i].uv,
					    mt6878_md_real_boot_rails[i].uv);
		if (ret)
			return ret;
		ret = regulator_sync_voltage(rail);
		if (ret)
			return ret;
		ret = regulator_get_voltage(rail);
		if (ret < 0)
			return ret;
		if ((u32)ret != mt6878_md_real_boot_rails[i].uv)
			return -EIO;
		ret = regulator_is_enabled(rail);
		if (ret <= 0)
			return ret < 0 ? ret : -EHOSTDOWN;
	}
	return 0;
}

/* genpd calls attach_dev before its attach-time power_on and before CCCI probe. */
static int mt6878_md_real_boot_attach(struct generic_pm_domain *genpd, struct device *dev)
{
	struct scpsys_domain *pd = to_scpsys_domain(genpd);
	struct mt6878_md_adoption *owner = pd->md_adoption;
	int ret;

	mutex_lock(&mt6878_md_first_off_lock);
	mutex_lock(&owner->lock);
	ret = mt6878_md_post_off_owner(pd, owner);
	if (ret)
		goto out;
	if (mt6878_md_real_boot_tail.owner != owner ||
	    mt6878_md_real_boot_tail.step != MT6878_MD_REAL_BOOT_POST_OFF_GATED ||
	    dev->bus != &platform_bus_type || dev->of_node != owner->modem ||
	    !of_device_is_available(owner->modem)) {
		ret = -EBUSY;
		goto out;
	}
	ret = mt6878_md_adopt_binding(pd, owner->modem, true);
	if (!ret)
		ret = mt6878_md_adopt_revalidate_resources(pd, owner);
	if (!ret)
		ret = mt6878_md_first_off_readback(pd, mt6878_md_real_boot_tail.off);
	if (ret)
		ret = mt6878_md_adopt_fault(owner, ret);
	else
		owner->attached = get_device(dev);
out:
	mutex_unlock(&owner->lock);
	mutex_unlock(&mt6878_md_first_off_lock);
	return ret;
}

/* Real genpd callback. Intentional execution; no artificial reset/inhibit owner. */
static int mt6878_md_real_boot_power_on(struct generic_pm_domain *genpd)
{
	struct scpsys_domain *pd = to_scpsys_domain(genpd);
	struct mt6878_md_adoption *owner = pd->md_adoption;
	struct regmap *base = pd->scpsys->base;
	u32 value;
	int i, ret;

	if (!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING) ||
	    IS_ENABLED(CONFIG_SCSI_UFS_MEDIATEK_DBG))
		return -EOPNOTSUPP;
	mutex_lock(&mt6878_md_first_off_lock);
	mutex_lock(&owner->lock);
	if (owner->first_error) {
		ret = owner->first_error;
		goto out;
	}
	if (owner != mt6878_md_first_off_owner || owner != mt6878_md_real_boot_tail.owner ||
	    owner->supplier != pd->scpsys->dev || !owner->attached ||
	    owner->attached->of_node != owner->modem ||
	    owner->state != MT6878_MD_FIRST_OFF_COMPLETE ||
	    mt6878_md_real_boot_tail.step != MT6878_MD_REAL_BOOT_POST_OFF_GATED) {
		ret = -EBUSY;
		goto out;
	}
	if (!mutex_trylock(&system_transition_mutex)) {
		ret = mt6878_md_adopt_fault(owner, -EBUSY);
		goto out;
	}
	ret = mt6878_md_first_off_profile(pd);
	if (!ret)
		ret = mt6878_md_adopt_binding(pd, owner->modem, true);
	if (!ret)
		ret = mt6878_md_adopt_revalidate_resources(pd, owner);
	if (!ret)
		ret = mt6878_md_first_off_readback(pd, mt6878_md_real_boot_tail.off);
	if (ret)
		goto fault;
	/* Re-read actual TOP gating, not the earlier completion field. */
	ret = regmap_read(mt6878_md_real_boot_tail.top.map, 0, &value);
	if (ret)
		goto fault;
	if ((value & MT6878_MD_POST_OFF_TOP_MASK) != MT6878_MD_POST_OFF_TOP_MASK) {
		ret = -EBUSY;
		goto fault;
	}
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_RAILS;
	ret = mt6878_md_real_boot_set_rails(owner);
	if (ret)
		goto fault;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_TOP;
	ret = regmap_clear_bits(mt6878_md_real_boot_tail.top.map, 0,
				MT6878_MD_POST_OFF_TOP_MASK);
	if (ret)
		goto fault;
	ret = regmap_read(mt6878_md_real_boot_tail.top.map, 0, &mt6878_md_real_boot_tail.top_on);
	if (ret)
		goto fault;
	if (mt6878_md_real_boot_tail.top_on & MT6878_MD_POST_OFF_TOP_MASK) {
		ret = -EIO;
		goto fault;
	}
	/* The pinned flow0 profile selects no SRC/O1/PLL/sequencer operations. */
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_FLIGHT;
	ret = mt6878_md_real_boot_flight_submit(owner->supplier, 0,
					     &mt6878_md_real_boot_tail.flight_on_a0);
	if (ret)
		goto fault;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_ISOLATION;
	ret = regmap_clear_bits(base, MT6878_MD_ISO, MT6878_MD_ISO_MASK);
	if (ret)
		goto fault;
	ret = regmap_read(base, MT6878_MD_ISO, &value);
	if (ret)
		goto fault;
	if (value & MT6878_MD_ISO_MASK) {
		ret = -EIO;
		goto fault;
	}
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_POWER;
	ret = regmap_set_bits(base, MT6878_MD_CTL, PWR_ON_BIT);
	if (ret)
		goto fault;
	ret = regmap_read_poll_timeout(base, MT6878_MD_CTL, value,
		(value & (MT6878_MD_ACK | PWR_ON_BIT)) == (MT6878_MD_ACK | PWR_ON_BIT),
		MTK_POLL_DELAY_US, MTK_POLL_TIMEOUT);
	if (ret)
		goto fault;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_BUS;
	for (i = 2; i >= 0; i--) {
		const struct scpsys_bus_prot_data *bp = &pd->data->bp_cfg[i];
		struct regmap *map = owner->maps[i + 1];

		ret = regmap_write(map, bp->bus_prot_clr, bp->bus_prot_set_clr_mask);
		if (ret)
			goto fault;
		ret = regmap_read_poll_timeout(map, bp->bus_prot_sta, value,
			!(value & bp->bus_prot_sta_mask), MTK_POLL_DELAY_US, MTK_POLL_TIMEOUT);
		if (ret)
			goto fault;
	}
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_READBACK;
	ret = mt6878_md_adopt_on(pd, mt6878_md_real_boot_tail.on);
	if (ret)
		goto fault;
	owner->state = MT6878_MD_ATTACHED_ON;
	mt6878_md_real_boot_tail.step = MT6878_MD_REAL_BOOT_ON_COMPLETE;
	dev_info(owner->supplier,
		 "MD native physical ON verified: ctl=%#x iso=%#x ifr9=%#x ifr11=%#x nemi=%#x; FLIGHT does not prove readiness\n",
		 mt6878_md_real_boot_tail.on[0], mt6878_md_real_boot_tail.on[1],
		 mt6878_md_real_boot_tail.on[2], mt6878_md_real_boot_tail.on[3],
		 mt6878_md_real_boot_tail.on[4]);
	goto transition_out;
fault:
	ret = mt6878_md_adopt_fault(owner, ret);
	dev_err(owner->supplier, "MD native ON failed at step %u: %d; resources retained, reboot required\n",
		mt6878_md_real_boot_tail.step, ret);
transition_out:
	mutex_unlock(&system_transition_mutex);
out:
	mutex_unlock(&owner->lock);
	mutex_unlock(&mt6878_md_first_off_lock);
	return ret;
}

#endif
