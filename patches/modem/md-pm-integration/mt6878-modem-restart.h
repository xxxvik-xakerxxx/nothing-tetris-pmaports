/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the native first-OFF owner and checked observation helpers. */

static int mt6878_md_restart_requested(struct scpsys_domain *pd, bool *requested)
{
	struct device_node *supplier = pd->scpsys->dev->of_node;
	struct device_node *chosen = of_find_node_by_path("/chosen");
	int ret = 0;

	*requested = of_property_present(supplier, "nothing,modem-inhibited-restart-staging") ||
		(chosen && of_property_present(chosen, "tetris,modem-inhibited-restart-staging"));
	if (*requested) {
		ret = mt6878_md_adopt_empty(supplier, "nothing,modem-inhibited-restart-staging");
		if (!ret)
			ret = chosen ? mt6878_md_adopt_empty(chosen,
				"tetris,modem-inhibited-restart-staging") : -ENODATA;
		if (!ret)
			ret = mt6878_md_first_off_profile(pd);
	}
	of_node_put(chosen);
	return ret;
}

/* Caller holds the boot takeover lock and then the retained owner lock. */
static int mt6878_md_restart_begin(struct mt6878_md_adoption *owner,
				  struct mt6878_md_adoption *retained,
				  struct device *supplier)
{
	if (owner->first_error)
		return owner->first_error;
	if (owner != retained || !supplier || owner->supplier != supplier)
		return -EXDEV;
	if (owner->restart.attempted)
		return -EALREADY;
	if (owner->state != MT6878_MD_FIRST_OFF_COMPLETE || owner->attached)
		return -EBUSY;
	owner->restart.attempted = true;
	owner->restart.step = MT6878_MD_RESTART_HANDOFF;
	return 0;
}

static int mt6878_md_restart_stop(struct mt6878_md_adoption *owner, int error)
{
	/* Even probe deferral becomes terminal after the retained OFF takeover. */
	return mt6878_md_adopt_fault(owner, error);
}

static int mt6878_md_restart_resources(struct mt6878_md_adoption *owner)
{
	static const char * const supplies[] = {
		"md-vmodem-supply", "md-vsram-supply", "md-vdigrf-supply",
	};
	static const char * const names[] = { "md-vmodem", "md-vsram", "md-vdigrf" };
	static const u32 voltage[] = { 800000, 800000, 700000 };
	struct mt6878_md_restart *restart = &owner->restart;
	struct device_node *modem = owner->modem;
	unsigned int i, j;
	int ret;

	/* Exact ee2be53 MT6878 profile: no SRC/O1/PLL/sequencer steps selected. */
	if (of_property_present(modem, "mediatek,power-flow-config")) {
		ret = mt6878_md_adopt_scalar(modem, "mediatek,power-flow-config", 0);
		if (ret)
			return ret;
	}
	if (of_property_present(modem, "mediatek,srclken-o1") ||
	    of_property_present(modem, "md-vnr-supply") ||
	    of_property_present(modem, "md-vmdfe-supply"))
		return -EOPNOTSUPP;
	if (of_count_phandle_with_args(modem, "ccci-topckgen", NULL) != 1)
		return -EINVAL;
	restart->top_node = of_parse_phandle(modem, "ccci-topckgen", 0);
	ret = mt6878_md_adopt_map_node(restart->top_node,
				      "mediatek,mt6878-topckgen", 0x10000000);
	if (ret)
		return ret;
	restart->top = device_node_to_regmap(restart->top_node);
	if (IS_ERR_OR_NULL(restart->top))
		return restart->top ? PTR_ERR(restart->top) : -ENODEV;
	for (i = 0; i < ARRAY_SIZE(supplies); i++) {
		if (of_count_phandle_with_args(modem, supplies[i], NULL) != 1 ||
		    of_property_count_u32_elems(modem, names[i]) != 2)
			return -EINVAL;
		restart->rail_nodes[i] = of_parse_phandle(modem, supplies[i], 0);
		if (!restart->rail_nodes[i] || !of_device_is_available(restart->rail_nodes[i]))
			return -ENODEV;
		for (j = 0; j < i; j++)
			if (restart->rail_nodes[i] == restart->rail_nodes[j])
				return -EINVAL;
		ret = of_property_read_u32_array(modem, names[i], restart->voltage[i], 2);
		if (ret)
			return ret;
		if (restart->voltage[i][0] != voltage[i] || restart->voltage[i][1] != voltage[i])
			return -EOPNOTSUPP;
	}
	return 0;
}

static int mt6878_md_inhibited_restart(struct scpsys_domain *pd,
				     struct mt6878_md_adoption *owner)
{
	char status[9];
	bool requested;
	int ret;

	mutex_lock(&mt6878_md_first_off_lock);
	mutex_lock(&owner->lock);
	ret = mt6878_md_restart_begin(owner, mt6878_md_first_off_owner, pd->scpsys->dev);
	if (ret)
		goto out;
	ret = mt6878_md_restart_requested(pd, &requested);
	if (!ret && !requested)
		ret = -ENODATA;
	if (!ret)
		ret = mt6878_md_adopt_property(owner->modem, "status", status, sizeof(status));
	if (!ret && memcmp(status, "disabled", sizeof(status)))
		ret = -EBUSY;
	if (!ret)
		ret = mt6878_md_adopt_binding(pd, owner->modem, false);
	if (!ret)
		ret = mt6878_md_adopt_revalidate_resources(pd, owner);
	if (ret)
		goto fault;
	owner->restart.step = MT6878_MD_RESTART_OFF;
	ret = mt6878_md_first_off_readback(pd, owner->restart.off);
	if (ret)
		goto fault;
	owner->restart.step = MT6878_MD_RESTART_RESOURCES;
	ret = mt6878_md_restart_resources(owner);
	if (ret)
		goto fault;
	owner->restart.step = MT6878_MD_RESTART_INHIBIT_BOUNDARY;
	/* No active inhibit owner/readback exists in this pinned gen6299 chain.
	 * Stop BEFORE regulator_get (supply resolution can enable a parent rail),
	 * PMIC voltage/sync, TOP ungate, FLIGHT, MTCMOS or POWER/0 release.
	 * A DT selector, OFF readback, skipped reset bit or old BROM is no grant.
	 */
	ret = -EOPNOTSUPP;
fault:
	ret = mt6878_md_restart_stop(owner, ret);
	dev_err(pd->scpsys->dev,
		"MD inhibited restart stopped at step %u: %d; owner retained, reboot required\n",
		owner->restart.step, ret);
out:
	mutex_unlock(&owner->lock);
	mutex_unlock(&mt6878_md_first_off_lock);
	return ret;
}
