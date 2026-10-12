/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the native bus helpers; shares their real provider handles. */
#if IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM)
#include <dt-bindings/spmi/spmi.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include "native-vmm/mt6878-native-vmm.h"

struct scpsys_vmm {
	struct mt6878_vmm_supplier supplier;
	struct device guard_dev[2];
	struct mt6878_vmm_guard guard[2];
	int first_error;
	bool retained;
};

static const unsigned int scpsys_vmm_ids[] = {
	MT6878_POWER_DOMAIN_CAM_VCORE,
	MT6878_POWER_DOMAIN_CAM_MAIN,
	MT6878_POWER_DOMAIN_ISP_VCORE,
};

static bool scpsys_vmm_domain(struct scpsys *scpsys, unsigned int id)
{
	if (!scpsys->vmm)
		return false;
	for (int i = 0; i < ARRAY_SIZE(scpsys_vmm_ids); i++)
		if (scpsys_vmm_ids[i] == id)
			return true;
	return false;
}

static int scpsys_vmm_fault(struct scpsys_domain *pd, int ret)
{
	return mt6878_vmm_fail_child(&pd->scpsys->vmm->supplier, ret);
}

static int scpsys_vmm_start(struct device *dev)
{
	struct scpsys_domain *pd = to_scpsys_domain(pd_to_genpd(dev->pm_domain));

	/* genpd calls start even for cached-ON domains, before driver resume. */
	return mt6878_vmm_check(&pd->scpsys->vmm->supplier);
}

static int scpsys_vmm_stop(struct device *dev)
{
	/* Pair start/stop so genpd also guards system resume before driver access. */
	return scpsys_vmm_start(dev);
}

static int scpsys_vmm_resume(struct device *dev)
{
	struct scpsys_domain *pd = to_scpsys_domain(pd_to_genpd(dev->pm_domain));
	struct mt6878_vmm_supplier *vmm = &pd->scpsys->vmm->supplier;
	int ret;

	if (READ_ONCE(vmm->first_error))
		return mt6878_vmm_check(vmm);
	ret = pd->native_runtime_resume(dev);
	/* Native genpd reduces a start failure to -1; expose our latched errno. */
	if (READ_ONCE(vmm->first_error))
		return mt6878_vmm_check(vmm);
	return ret;
}

static int scpsys_vmm_bus(struct scpsys_domain *pd, bool protect)
{
	for (int n = 0; n < SPM_MAX_BUS_PROT_DATA; n++) {
		int i = protect ? n : SPM_MAX_BUS_PROT_DATA - 1 - n;
		const struct scpsys_bus_prot_data *bpd = &pd->data->bp_cfg[i];
		struct regmap *map, *sta;
		u32 value;
		int ret;

		if (!bpd->bus_prot_set_clr_mask)
			continue;
		/* These three B4.1 descriptors use only W1S/W1C, ignored CLR ACK. */
		if (bpd->flags != BUS_PROT_IGNORE_CLR_ACK)
			return -EINVAL;
		map = scpsys_bus_protect_get_regmap(pd, bpd);
		sta = scpsys_bus_protect_get_sta_regmap(pd, bpd);
		ret = regmap_write(map, protect ? bpd->bus_prot_set : bpd->bus_prot_clr,
				   bpd->bus_prot_set_clr_mask);
		if (ret)
			return ret;
		if (!protect)
			continue;
		ret = regmap_read_poll_timeout(sta, bpd->bus_prot_sta, value,
				(value & bpd->bus_prot_sta_mask) == bpd->bus_prot_sta_mask,
				MTK_POLL_DELAY_US, MTK_POLL_TIMEOUT);
		if (ret)
			return ret;
	}
	return 0;
}

static int scpsys_vmm_sram(struct scpsys_domain *pd, bool on)
{
	u32 value, mask = pd->data->sram_pdn_bits;
	u32 ack = pd->data->sram_pdn_ack_bits;
	int ret;

	if (!mask)
		return 0;
	ret = regmap_update_bits(pd->scpsys->base, pd->data->ctl_offs,
				 mask, on ? 0 : mask);
	if (ret)
		return ret;
	return regmap_read_poll_timeout(pd->scpsys->base, pd->data->ctl_offs,
			value, (value & ack) == (on ? 0 : ack),
			MTK_POLL_DELAY_US, MTK_POLL_TIMEOUT);
}

static int scpsys_vmm_ctl(struct scpsys_domain *pd, bool on)
{
	struct mt6878_vmm_supplier *vmm = &pd->scpsys->vmm->supplier;

	if (pd->vmm_id == MT6878_POWER_DOMAIN_ISP_VCORE)
		return mt6878_vmm_isp_vcore_ctl_set(vmm, pd->vmm_id, on);
	return mt6878_vmm_cam_ctl_set(vmm, pd->vmm_id, on);
}

static int scpsys_vmm_on(struct generic_pm_domain *genpd)
{
	struct scpsys_domain *pd = to_scpsys_domain(genpd);
	int ret;

	ret = mt6878_vmm_check(&pd->scpsys->vmm->supplier);
	if (ret)
		return ret;
	ret = clk_bulk_prepare_enable(pd->num_clks, pd->clks);
	if (ret)
		return scpsys_vmm_fault(pd, ret);
	ret = scpsys_vmm_ctl(pd, true);
	if (ret)
		return ret;
	ret = clk_bulk_prepare_enable(pd->num_subsys_clks, pd->subsys_clks);
	if (ret)
		return scpsys_vmm_fault(pd, ret);
	ret = scpsys_vmm_sram(pd, true);
	if (ret)
		return scpsys_vmm_fault(pd, ret);
	ret = scpsys_vmm_bus(pd, false);
	if (ret)
		return scpsys_vmm_fault(pd, ret);
	return 0;
}

static int scpsys_vmm_off(struct generic_pm_domain *genpd)
{
	struct scpsys_domain *pd = to_scpsys_domain(genpd);
	int ret;

	ret = mt6878_vmm_check(&pd->scpsys->vmm->supplier);
	if (ret)
		return ret;
	ret = scpsys_vmm_bus(pd, true);
	if (ret)
		return scpsys_vmm_fault(pd, ret);
	ret = scpsys_vmm_sram(pd, false);
	if (ret)
		return scpsys_vmm_fault(pd, ret);
	clk_bulk_disable_unprepare(pd->num_subsys_clks, pd->subsys_clks);
	ret = scpsys_vmm_ctl(pd, false);
	if (ret)
		return ret;
	clk_bulk_disable_unprepare(pd->num_clks, pd->clks);
	return 0;
}

static int scpsys_vmm_observe_off(struct scpsys_domain *pd)
{
	u32 value;
	int ret;

	ret = regmap_read(pd->scpsys->base, pd->data->ctl_offs, &value);
	if (ret)
		return ret;
	/* Reject inherited requests, either ACK, active SRAM and unsafe isolation. */
	if (value & (GENMASK(31, 30) | PWR_ON_BIT | PWR_ON_2ND_BIT | PWR_RST_B_BIT))
		return -EBUSY;
	if ((value & (PWR_ISO_BIT | PWR_CLK_DIS_BIT)) !=
	    (PWR_ISO_BIT | PWR_CLK_DIS_BIT))
		return -EIO;
	if ((value & pd->data->sram_pdn_bits) != pd->data->sram_pdn_bits ||
	    (value & pd->data->sram_pdn_ack_bits) != pd->data->sram_pdn_ack_bits)
		return -EIO;
	for (int i = 0; i < SPM_MAX_BUS_PROT_DATA; i++) {
		const struct scpsys_bus_prot_data *bpd = &pd->data->bp_cfg[i];

		if (!bpd->bus_prot_set_clr_mask)
			continue;
		ret = regmap_read(scpsys_bus_protect_get_sta_regmap(pd, bpd),
				  bpd->bus_prot_sta, &value);
		if (ret)
			return ret;
		if ((value & bpd->bus_prot_sta_mask) != bpd->bus_prot_sta_mask)
			return -EIO;
	}
	return 0;
}

static int scpsys_vmm_clocks(struct device_node *node, unsigned int id)
{
	const char *name;
	int count = of_clk_get_parent_count(node);

	if (id != MT6878_POWER_DOMAIN_CAM_MAIN)
		return count == 0 && !of_property_present(node, "clock-names") ? 0 : -EINVAL;
	if (count != 9 || of_property_count_strings(node, "clock-names") != 9)
		return -EINVAL;
	for (int i = 0; i < 9; i++) {
		char expected[16];
		int ret = of_property_read_string_index(node, "clock-names", i, &name);

		if (ret)
			return ret;
		if (i)
			snprintf(expected, sizeof(expected), "cam_main-%d", i - 1);
		else
			strscpy(expected, "cam", sizeof(expected));
		if (strcmp(name, expected))
			return -EINVAL;
	}
	return 0;
}

static int scpsys_vmm_topology(struct device_node *parent, unsigned int parent_id,
			       unsigned int *seen)
{
	struct device_node *child;
	int ret;

	for_each_available_child_of_node(parent, child) {
		u32 id;

		ret = of_property_read_u32(child, "reg", &id);
		if (ret)
			goto error;
		for (int i = 0; i < ARRAY_SIZE(scpsys_vmm_ids); i++) {
			if (id != scpsys_vmm_ids[i])
				continue;
			ret = -EINVAL;
			if (*seen & BIT(i))
				goto error;
			if (parent_id != (id == MT6878_POWER_DOMAIN_CAM_MAIN ?
				MT6878_POWER_DOMAIN_CAM_VCORE : MT6878_POWER_DOMAIN_MM_INFRA))
				goto error;
			if (of_property_present(child, "domain-supply"))
				goto error;
			ret = scpsys_vmm_clocks(child, id);
			if (ret)
				goto error;
			*seen |= BIT(i);
		}
		/* No uncovered sibling/descendant may acquire the common rail. */
		if ((parent_id == MT6878_POWER_DOMAIN_CAM_VCORE &&
		     id != MT6878_POWER_DOMAIN_CAM_MAIN) ||
		    parent_id == MT6878_POWER_DOMAIN_CAM_MAIN ||
		    parent_id == MT6878_POWER_DOMAIN_ISP_VCORE) {
			ret = -EOPNOTSUPP;
			goto error;
		}
		ret = scpsys_vmm_topology(child, id, seen);
		if (ret)
			goto error;
	}
	return 0;
error:
	of_node_put(child);
	return ret;
}

static int scpsys_vmm_rail_identity(struct device_node *rail)
{
	struct device_node *regulators = of_get_parent(rail);
	struct device_node *pmic = of_get_parent(regulators);
	u32 address[2], mask;
	int ret = -EINVAL;

	/* Native direct SPMI binding for B4.1 USID-6 VBUCK1, not vendor MFD nesting. */
	if (!of_node_name_eq(rail, "vbuck1") || !of_node_name_eq(regulators, "regulators") ||
	    !of_device_is_compatible(pmic, "mediatek,mt6315-regulator"))
		goto out;
	if (!of_device_is_available(rail) || !of_device_is_available(regulators) ||
	    !of_device_is_available(pmic)) {
		ret = -ENODEV;
		goto out;
	}
	ret = of_property_read_u32_array(pmic, "reg", address, ARRAY_SIZE(address));
	if (ret)
		goto out;
	if (address[0] != 6 || address[1] != SPMI_USID) {
		ret = -EINVAL;
		goto out;
	}
	ret = of_property_read_u32(pmic, "mediatek,buck1-mode-mask", &mask);
	if (ret)
		goto out;
	if (mask != BIT(0))
		ret = -EINVAL;
out:
	of_node_put(pmic);
	of_node_put(regulators);
	return ret;
}

static int scpsys_vmm_prepare(struct scpsys *scpsys)
{
	struct device_node *np = scpsys->dev->of_node;
	struct device_node *cam, *isp, *node;
	unsigned int seen = 0;
	int ret;

	if (!IS_ENABLED(CONFIG_MTK_MT6878_NATIVE_VMM) ||
	    scpsys->soc_data != &mt6878_scpsys_data)
		return 0;
	if (!of_property_present(np, "cam-vcore-supply") &&
	    !of_property_present(np, "isp-vcore-supply"))
		return 0;
	cam = of_parse_phandle(np, "cam-vcore-supply", 0);
	isp = of_parse_phandle(np, "isp-vcore-supply", 0);
	ret = -EINVAL;
	if (!cam || !isp || cam != isp)
		goto put_rails;
	ret = scpsys_vmm_rail_identity(cam);
	if (ret)
		goto put_rails;
	/* Reject described independent owners, including B4.1 VMM/MMDVFS. */
	for_each_of_allnodes(node) {
		struct property *prop;

		if (!of_device_is_available(node))
			continue;
		for_each_property_of_node(node, prop) {
			struct device_node *rail;
			size_t len = strlen(prop->name);
			bool shared;

			if (len < 7 || strcmp(prop->name + len - 7, "-supply"))
				continue;
			if (node == np && (!strcmp(prop->name, "cam-vcore-supply") ||
					   !strcmp(prop->name, "isp-vcore-supply")))
				continue;
			rail = of_parse_phandle(node, prop->name, 0);
			shared = rail == cam;
			of_node_put(rail);
			if (shared) {
				dev_err(scpsys->dev, "%pOF:%s still owns the VMM rail\n",
					node, prop->name);
				of_node_put(node);
				ret = -EBUSY;
				goto put_rails;
			}
		}
	}
	ret = scpsys_vmm_topology(np, U32_MAX, &seen);
	if (ret)
		goto put_rails;
	if (seen != GENMASK(2, 0)) {
		ret = -EINVAL;
		goto put_rails;
	}
	scpsys->vmm = devm_kzalloc(scpsys->dev, sizeof(*scpsys->vmm), GFP_KERNEL);
	ret = scpsys->vmm ? 0 : -ENOMEM;
put_rails:
	of_node_put(cam);
	of_node_put(isp);
	return ret;
}

static void scpsys_vmm_guard_release(struct device *dev)
{
	/* Embedded guard storage belongs to the permanently bound provider. */
}

static int scpsys_vmm_construct(struct scpsys *scpsys)
{
	struct scpsys_vmm *owner = scpsys->vmm;
	const unsigned int roots[] = {
		MT6878_POWER_DOMAIN_CAM_VCORE, MT6878_POWER_DOMAIN_ISP_VCORE,
	};
	struct generic_pm_domain *mm;
	int ret;

	if (!owner)
		return 0;
	mm = scpsys->domains[MT6878_POWER_DOMAIN_MM_INFRA];
	if (!mm)
		return -ENODEV;
	for (int i = 0; i < ARRAY_SIZE(scpsys_vmm_ids); i++) {
		struct generic_pm_domain *gpd = scpsys->domains[scpsys_vmm_ids[i]];

		if (!gpd || gpd->status != GENPD_STATE_OFF)
			return -EBUSY;
	}
	/* The validated B4.1 pair selects one exclusive handle on this device. */
	ret = mt6878_vmm_supplier_init(&owner->supplier, scpsys->dev, "cam-vcore",
				     scpsys->base, mm);
	if (ret)
		return ret;
	for (int i = 0; i < ARRAY_SIZE(roots); i++) {
		struct generic_pm_domain *gpd = scpsys->domains[roots[i]];
		struct device *dev = &owner->guard_dev[i];

		device_initialize(dev);
		dev->parent = scpsys->dev;
		dev->release = scpsys_vmm_guard_release;
		ret = dev_set_name(dev, "mt6878-vmm-guard-%u", roots[i]);
		if (ret)
			goto fault;
		ret = pm_genpd_add_device(gpd, dev);
		if (ret)
			goto fault;
		ret = mt6878_vmm_add_child(&owner->supplier, gpd, dev, &owner->guard[i]);
		if (ret)
			goto fault;
	}
	return 0;
fault:
	return mt6878_vmm_fail_child(&owner->supplier, ret);
}

static bool scpsys_vmm_retain(struct scpsys *scpsys, int ret)
{
	struct scpsys_vmm *owner = scpsys->vmm;

	if (!owner || (!owner->supplier.buck && !owner->retained))
		return false;
	if (!owner->first_error)
		owner->first_error = ret;
	if (owner->supplier.initialized)
		mt6878_vmm_fail_child(&owner->supplier, ret);
	/* Bind without publishing on partial ownership: devres and guards persist. */
	dev_err(scpsys->dev, "VMM provider withheld: %d; retained until recovery\n",
		owner->first_error);
	return true;
}

static int scpsys_vmm_unlink(struct scpsys *scpsys)
{
	int ret;

	if (!scpsys->vmm)
		return 0;
	/* Before exclusive get there are no guards; remove edges before domains. */
	for (int i = 0; i < scpsys->pd_data.num_domains; i++) {
		struct generic_pm_domain *gpd = scpsys->domains[i];
		struct gpd_link *link, *next;

		if (!gpd)
			continue;
		list_for_each_entry_safe(link, next, &gpd->parent_links, parent_node) {
			ret = pm_genpd_remove_subdomain(gpd, link->child);
			if (ret) {
				scpsys->vmm->retained = true;
				return ret;
			}
		}
	}
	return 0;
}

#else
static int scpsys_vmm_prepare(struct scpsys *scpsys) { return 0; }
static int scpsys_vmm_construct(struct scpsys *scpsys) { return 0; }
static bool scpsys_vmm_retain(struct scpsys *scpsys, int ret) { return false; }
static int scpsys_vmm_unlink(struct scpsys *scpsys) { return 0; }
#endif
