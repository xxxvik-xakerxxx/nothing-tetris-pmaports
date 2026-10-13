/* SPDX-License-Identifier: GPL-2.0-only */
/* Additive to the packaged minimal MT6363 provider, not the vendor driver. */
#include <linux/delay.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/regulator/machine.h>
#include <linux/regulator/of_regulator.h>

struct mt6363_md_info {
	struct regulator_desc desc;
	u16 op_en, sshub_en, fccm, hw_lp, lp;
	u8 fccm_mask, hw_lp_mask, lp_mask;
};

struct mt6363_md_state {
	const struct mt6363_md_info *info;
	struct regulator_desc desc;
	struct mutex *lock;
	int first_write_error;
	bool registering, owns_enable;
};

static const struct linear_range mt6363_md_buck_ranges[] = {
	REGULATOR_LINEAR_RANGE(0, 0, 191, 6250),
};

static const struct linear_range mt6363_md_sram_ranges[] = {
	REGULATOR_LINEAR_RANGE(400000, 0, 127, 6250),
};

/* ee2 MT6363 normal AP control: preserve, never rewrite these ownership banks.
 * VBUCK1/2 have separate SSHUB controls; their selectors are not interchangeable.
 * This checks a source-defined control profile, not a global secure-actor lock.
 */
static int mt6363_md_control(struct regmap *map, const struct mt6363_md_info *info)
{
	unsigned int value, i;
	int ret;

	for (i = 0; i < 3; i++) {
		ret = regmap_read(map, info->op_en + i, &value);
		if (ret)
			return ret;
		if (value != (i == 2 ? 0x80 : 0))
			return -EBUSY;
	}
	ret = regmap_read(map, info->op_en + 5, &value);
	if (ret)
		return ret;
	if (value != 0x10)
		return -EBUSY;
	if (info->sshub_en) {
		ret = regmap_read(map, info->sshub_en, &value);
		if (ret)
			return ret;
		if (value & BIT(0))
			return -EBUSY;
	}
	return 0;
}

static int mt6363_md_selector(struct regmap *map, const struct mt6363_md_info *info)
{
	unsigned int value;
	int ret;

	ret = mt6363_md_control(map, info);
	if (ret)
		return ret;
	ret = regmap_read(map, info->desc.vsel_reg, &value);
	if (ret)
		return ret;
	value &= info->desc.vsel_mask;
	if (value >= info->desc.n_voltages)
		return -ERANGE;
	ret = mt6363_md_control(map, info);
	if (ret)
		return ret;
	return value;
}

static int mt6363_md_get_voltage_sel(struct regulator_dev *rdev)
{
	struct mt6363_md_state *state = rdev_get_drvdata(rdev);
	int ret;

	mutex_lock(state->lock);
	ret = mt6363_md_selector(rdev->regmap, state->info);
	mutex_unlock(state->lock);
	return ret;
}

static int mt6363_md_is_enabled(struct regulator_dev *rdev)
{
	struct mt6363_md_state *state = rdev_get_drvdata(rdev);
	int ret, enabled;

	mutex_lock(state->lock);
	ret = mt6363_md_control(rdev->regmap, state->info);
	if (ret)
		goto out;
	enabled = regulator_is_enabled_regmap(rdev);
	if (enabled < 0) {
		ret = enabled;
		goto out;
	}
	ret = mt6363_md_control(rdev->regmap, state->info);
	if (!ret)
		ret = enabled;
out:
	mutex_unlock(state->lock);
	return ret;
}

static int mt6363_md_write_admit(struct regulator_dev *rdev)
{
	struct mt6363_md_state *state = rdev_get_drvdata(rdev);

	if (state->first_write_error)
		return state->first_write_error;
	if (state->registering)
		return -EOPNOTSUPP;
	return mt6363_md_control(rdev->regmap, state->info);
}

static int mt6363_md_write_fault(struct mt6363_md_state *state, int error)
{
	if (!state->first_write_error)
		state->first_write_error = error < 0 ? error : -EPROTO;
	return state->first_write_error;
}

static int mt6363_md_set_voltage_sel(struct regulator_dev *rdev, unsigned int selector)
{
	struct mt6363_md_state *state = rdev_get_drvdata(rdev);
	int ret;

	mutex_lock(state->lock);
	ret = mt6363_md_write_admit(rdev);
	if (ret)
		goto out;
	if (selector >= rdev->desc->n_voltages) {
		ret = -EINVAL;
		goto out;
	}
	ret = regulator_set_voltage_sel_regmap(rdev, selector);
	if (ret)
		goto fault;
	ret = mt6363_md_selector(rdev->regmap, state->info);
	if (ret < 0)
		goto fault;
	if ((unsigned int)ret != selector) {
		ret = -EIO;
		goto fault;
	}
	ret = 0;
	goto out;
fault:
	ret = mt6363_md_write_fault(state, ret);
out:
	mutex_unlock(state->lock);
	return ret;
}

static int mt6363_md_enable_request(struct regulator_dev *rdev, bool enable)
{
	struct mt6363_md_state *state = rdev_get_drvdata(rdev);
	int ret, enabled;

	mutex_lock(state->lock);
	ret = mt6363_md_write_admit(rdev);
	if (ret)
		goto out;
	enabled = regulator_is_enabled_regmap(rdev);
	if (enabled < 0) {
		ret = enabled;
		goto out;
	}
	/* Do not turn an inherited enable request into our disable permission. */
	if (enabled == enable) {
		if (!enabled)
			state->owns_enable = false;
		ret = 0;
		goto out;
	}
	if (!enable && !state->owns_enable) {
		ret = -EBUSY;
		goto out;
	}
	/* Vendor buck_ops also supplies VSRAM_MODEM: use exact SET/CLR aliases. */
	ret = regmap_write(rdev->regmap, rdev->desc->enable_reg + (enable ? 1 : 2),
			   rdev->desc->enable_mask);
	if (ret)
		goto fault;
	ret = mt6363_md_control(rdev->regmap, state->info);
	if (ret)
		goto fault;
	ret = regulator_is_enabled_regmap(rdev);
	if (ret < 0)
		goto fault;
	if (ret != enable) {
		ret = -EIO;
		goto fault;
	}
	state->owns_enable = enable;
	ret = 0;
	goto out;
fault:
	ret = mt6363_md_write_fault(state, ret);
out:
	mutex_unlock(state->lock);
	return ret;
}

static int mt6363_md_enable(struct regulator_dev *rdev)
{
	return mt6363_md_enable_request(rdev, true);
}

static int mt6363_md_disable(struct regulator_dev *rdev)
{
	return mt6363_md_enable_request(rdev, false);
}

static int mt6363_md_read_mode(struct regmap *map, const struct mt6363_md_info *info,
			       unsigned int *mode)
{
	unsigned int value;
	int ret;

	/* Linear VSRAM_MODEM has no FCCM field: never access vendor's zero default. */
	if (info->fccm) {
		ret = regmap_read(map, info->fccm, &value);
		if (ret)
			return ret;
		if (value & info->fccm_mask) {
			*mode = REGULATOR_MODE_FAST;
			return 0;
		}
	}
	ret = regmap_read(map, info->hw_lp, &value);
	if (ret)
		return ret;
	*mode = value & info->hw_lp_mask ? REGULATOR_MODE_IDLE : REGULATOR_MODE_NORMAL;
	return 0;
}

static unsigned int mt6363_md_get_mode(struct regulator_dev *rdev)
{
	struct mt6363_md_state *state = rdev_get_drvdata(rdev);
	unsigned int mode;
	int ret;

	mutex_lock(state->lock);
	ret = mt6363_md_read_mode(rdev->regmap, state->info, &mode);
	mutex_unlock(state->lock);
	/* get_mode has an unsigned API; retain the negative errno representation. */
	return ret ? (unsigned int)ret : mode;
}

static unsigned int mt6363_md_map_mode(unsigned int mode)
{
	if (mode == 0)
		return REGULATOR_MODE_NORMAL;
	if (mode == 2)
		return REGULATOR_MODE_IDLE;
	return REGULATOR_MODE_INVALID;
}

static int mt6363_md_set_mode(struct regulator_dev *rdev, unsigned int mode)
{
	struct mt6363_md_state *state = rdev_get_drvdata(rdev);
	const struct mt6363_md_info *info = state->info;
	unsigned int current_mode, lp;
	int ret;

	mutex_lock(state->lock);
	ret = mt6363_md_write_admit(rdev);
	if (ret)
		goto out;
	if (mode != REGULATOR_MODE_NORMAL && mode != REGULATOR_MODE_IDLE) {
		ret = -EOPNOTSUPP;
		goto out;
	}
	ret = mt6363_md_read_mode(rdev->regmap, info, &current_mode);
	if (ret)
		goto out;
	/* FCCM needs the shared BUCK key. Do not unlock/relock it without its owner. */
	if (current_mode == REGULATOR_MODE_FAST) {
		ret = -EOPNOTSUPP;
		goto out;
	}
	ret = regmap_read(rdev->regmap, info->lp, &lp);
	if (ret)
		goto out;
	if (!!(lp & info->lp_mask) != (current_mode == REGULATOR_MODE_IDLE)) {
		ret = -EBUSY;
		goto out;
	}
	ret = regmap_update_bits(rdev->regmap, info->lp, info->lp_mask,
				mode == REGULATOR_MODE_IDLE ? info->lp_mask : 0);
	if (ret)
		goto fault;
	if (current_mode == REGULATOR_MODE_IDLE && mode == REGULATOR_MODE_NORMAL)
		udelay(100);
	ret = mt6363_md_control(rdev->regmap, info);
	if (ret)
		goto fault;
	ret = regmap_read(rdev->regmap, info->lp, &lp);
	if (ret)
		goto fault;
	if (!!(lp & info->lp_mask) != (mode == REGULATOR_MODE_IDLE)) {
		ret = -EIO;
		goto fault;
	}
	ret = 0;
	goto out;
fault:
	ret = mt6363_md_write_fault(state, ret);
out:
	mutex_unlock(state->lock);
	return ret;
}

static int mt6363_md_set_load(struct regulator_dev *rdev, int load_uA)
{
	/* Vendor load switching rewrites hardware voters; no takeover is implemented. */
	(void)rdev;
	(void)load_uA;
	return -EOPNOTSUPP;
}

static const struct regulator_ops mt6363_md_ops = {
	.list_voltage = regulator_list_voltage_linear_range,
	.map_voltage = regulator_map_voltage_linear_range,
	.get_voltage_sel = mt6363_md_get_voltage_sel,
	.set_voltage_sel = mt6363_md_set_voltage_sel,
	.enable = mt6363_md_enable,
	.disable = mt6363_md_disable,
	.is_enabled = mt6363_md_is_enabled,
	.get_mode = mt6363_md_get_mode,
	.set_mode = mt6363_md_set_mode,
	.set_load = mt6363_md_set_load,
};

#define MT6363_MD_DESC(_name, _id, _ranges, _count, _en, _bit, _sel, _mask) \
	{ .name = _name, .of_match = _name, .id = _id, .owner = THIS_MODULE, \
	  .type = REGULATOR_VOLTAGE, .ops = &mt6363_md_ops, \
	  .linear_ranges = _ranges, .n_linear_ranges = ARRAY_SIZE(_ranges), \
	  .n_voltages = _count, .enable_reg = _en, .enable_mask = BIT(_bit), \
	  .vsel_reg = _sel, .vsel_mask = _mask, .enable_time = 180, \
	  .of_map_mode = mt6363_md_map_mode }

static const struct mt6363_md_info mt6363_md_rails[] = {
	{
		.desc = MT6363_MD_DESC("vbuck1", 1, mt6363_md_buck_ranges, 192,
				      0x240, 1, 0x24d, 0xff),
		.op_en = 0x150d, .sshub_en = 0x151a,
		.fccm = 0x1a32, .fccm_mask = BIT(0),
		.hw_lp = 0x1518, .hw_lp_mask = 0xc,
		.lp = 0x246, .lp_mask = BIT(1),
	},
	{
		.desc = MT6363_MD_DESC("vbuck2", 2, mt6363_md_buck_ranges, 192,
				      0x240, 2, 0x24e, 0xff),
		.op_en = 0x158d, .sshub_en = 0x159a,
		.fccm = 0x1a32, .fccm_mask = BIT(1),
		.hw_lp = 0x1598, .hw_lp_mask = 0xc,
		.lp = 0x246, .lp_mask = BIT(2),
	},
	{
		.desc = MT6363_MD_DESC("vsram-modem", 15, mt6363_md_sram_ranges, 128,
				      0x243, 6, 0x25a, 0x7f),
		.op_en = 0x1daf,
		.hw_lp = 0x1da6, .hw_lp_mask = 0x4,
		.lp = 0x249, .lp_mask = BIT(6),
	},
};
#undef MT6363_MD_DESC

static int mt6363_md_dt(struct device_node *node, const char *name)
{
	static const char * const properties[] = {
		"status", "regulator-name", "regulator-compatible", "phandle", "linux,phandle",
		"regulator-min-microvolt", "regulator-max-microvolt",
		"regulator-enable-ramp-delay", "regulator-allowed-modes",
	};
	struct property *property;
	const char *match;
	unsigned int i;
	u32 mode, delay;
	int ret, count;

	if (of_get_child_count(node))
		return -EOPNOTSUPP;
	for_each_property_of_node(node, property) {
		for (i = 0; i < ARRAY_SIZE(properties); i++)
			if (!strcmp(property->name, properties[i]))
				break;
		if (i == ARRAY_SIZE(properties))
			return -EOPNOTSUPP;
	}
	if (of_property_present(node, "regulator-compatible")) {
		ret = of_property_read_string(node, "regulator-compatible", &match);
		if (ret)
			return ret;
		if (strcmp(match, name))
			return -EINVAL;
	}
	for (i = 0; i < 2; i++)
		if (of_property_count_u32_elems(node, i ? "regulator-max-microvolt" :
					      "regulator-min-microvolt") != 1)
			return -EINVAL;
	if (of_property_present(node, "regulator-enable-ramp-delay")) {
		if (of_property_count_u32_elems(node, "regulator-enable-ramp-delay") != 1)
			return -EINVAL;
		ret = of_property_read_u32(node, "regulator-enable-ramp-delay", &delay);
		if (ret)
			return ret;
		if (delay != 180)
			return -EOPNOTSUPP;
	}
	if (of_property_present(node, "regulator-allowed-modes")) {
		count = of_property_count_u32_elems(node, "regulator-allowed-modes");
		if (count < 1 || count > 2)
			return -EINVAL;
		for (i = 0; i < count; i++) {
			ret = of_property_read_u32_index(node, "regulator-allowed-modes", i, &mode);
			if (ret)
				return ret;
			if (mt6363_md_map_mode(mode) == REGULATOR_MODE_INVALID)
				return -EOPNOTSUPP;
		}
	}
	return 0;
}

static int mt6363_md_register(struct platform_device *pdev, struct regmap *map)
{
	struct device *dev = &pdev->dev;
	struct device_node *nodes[ARRAY_SIZE(mt6363_md_rails)] = { 0 }, *child;
	struct mt6363_md_state *states;
	struct mutex *lock;
	unsigned int i, count = 0;
	int ret = 0;

	/* No new allocation or PMIC access when the opt-in children are unavailable. */
	for_each_available_child_of_node(dev->of_node, child) {
		for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
			if (!of_node_name_eq(child, mt6363_md_rails[i].desc.of_match))
				continue;
			if (nodes[i]) {
				of_node_put(child);
				ret = -EEXIST;
				goto out;
			}
			ret = mt6363_md_dt(child, mt6363_md_rails[i].desc.of_match);
			if (ret) {
				of_node_put(child);
				goto out;
			}
			nodes[i] = of_node_get(child);
			count++;
		}
	}
	if (!count)
		return 0;
	states = devm_kcalloc(dev, ARRAY_SIZE(mt6363_md_rails), sizeof(*states), GFP_KERNEL);
	lock = devm_kzalloc(dev, sizeof(*lock), GFP_KERNEL);
	if (!states || !lock) {
		ret = -ENOMEM;
		goto out;
	}
	mutex_init(lock);
	for (i = 0; i < ARRAY_SIZE(mt6363_md_rails); i++) {
		const struct mt6363_md_info *info = &mt6363_md_rails[i];
		struct regulator_config config = { .dev = dev, .regmap = map };
		struct regulator_dev *rdev;

		if (!nodes[i])
			continue;
		states[i].info = info;
		states[i].desc = info->desc;
		/* Bind the exact validated node/init data. Core DT parse errors can otherwise
		 * fall back to an unconstrained regulator instead of returning an errno.
		 */
		states[i].desc.of_match = NULL;
		states[i].lock = lock;
		states[i].registering = true;
		config.driver_data = &states[i];
		config.of_node = nodes[i];
		config.init_data = of_get_regulator_init_data(dev, nodes[i], &info->desc);
		if (!config.init_data) {
			ret = -EINVAL;
			goto out;
		}
		rdev = devm_regulator_register(dev, &states[i].desc, &config);
		if (IS_ERR(rdev)) {
			ret = dev_err_probe(dev, PTR_ERR(rdev), "failed to register %s\n",
					    info->desc.name);
			goto out;
		}
		states[i].registering = false;
	}
out:
	for (i = 0; i < ARRAY_SIZE(nodes); i++)
		of_node_put(nodes[i]);
	return ret;
}
