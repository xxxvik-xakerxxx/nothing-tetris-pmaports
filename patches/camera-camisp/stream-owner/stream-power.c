/* SPDX-License-Identifier: GPL-2.0-only */
/* Inserted into the actual streaming driver, using its existing power owner. */

static int imx882_power_fault(struct imx882_identity *power, int error)
{
	if (!power->first_error)
		power->first_error = error;
	return power->first_error;
}

static int imx882_reset_observe(struct imx882_identity *power, int asserted)
{
	int ret;

	ret = gpiod_get_direction(power->reset);
	if (ret < 0)
		return ret;
	if (ret != 0)
		return -EOPNOTSUPP;
	ret = gpiod_get_value_cansleep(power->reset);
	if (ret < 0)
		return ret;
	return ret == asserted ? 0 : -EIO;
}

static int imx882_reset_set(struct imx882_identity *power, int asserted)
{
	int ret;

	ret = gpiod_set_value_cansleep(power->reset, asserted);
	if (!ret)
		ret = imx882_reset_observe(power, asserted);
	return ret ? imx882_power_fault(power, ret) : 0;
}

static int imx882_supplies_observe(struct imx882_identity *power, int enabled)
{
	int supply, ret;

	for (supply = 0; supply < IMX882_NUM_SUPPLIES; supply++) {
		ret = regulator_is_enabled(power->supplies[supply].consumer);
		if (ret < 0)
			return ret;
		if (!!ret != enabled)
			return enabled ? -EIO : -EBUSY;
	}
	return 0;
}

static int imx882_idle_check(struct imx882_identity *power)
{
	if (__clk_is_enabled(power->xclk))
		return -EBUSY;
	return imx882_supplies_observe(power, 0);
}

static int imx882_mclk_check(struct imx882_identity *power)
{
	if (!clk_is_match(clk_get_parent(power->xclk), power->xclk_source) ||
	    clk_get_rate(power->xclk_source) != IMX882_XCLK_RATE ||
	    clk_get_rate(power->xclk) != IMX882_XCLK_RATE ||
	    !__clk_is_enabled(power->xclk))
		return -EIO;
	return 0;
}

static int imx882_power_validate(struct imx882_identity *power)
{
	int ret;

	if (power->first_error)
		return power->first_error;
	ret = imx882_mclk_check(power);
	if (!ret)
		ret = imx882_supplies_observe(power, 1);
	if (!ret)
		ret = imx882_reset_observe(power, 0);
	return ret ? imx882_power_fault(power, ret) : 0;
}

static int imx882_enable_supply(struct imx882_identity *power, int supply)
{
	int ret;

	ret = regulator_set_voltage(power->supplies[supply].consumer,
				    imx882_supply_uv[supply], imx882_supply_uv[supply]);
	if (!ret)
		ret = regulator_enable(power->supplies[supply].consumer);
	return ret ? imx882_power_fault(power, ret) : 0;
}

static int imx882_power_off(struct imx882_identity *power,
			    unsigned long *enabled_supplies, bool *clock_enabled)
{
	int ret, supply;

	/* Do not retry an uncertain transition or discard its successful inputs. */
	if (power->first_error)
		return power->first_error;
	if (!power->rate_exclusive && !power->source_rate_exclusive &&
	    !*enabled_supplies && !*clock_enabled && !power->mclk_selected)
		return 0;
	ret = imx882_reset_set(power, 1);
	if (ret)
		return ret;
	if (*clock_enabled) {
		clk_disable_unprepare(power->xclk);
		*clock_enabled = false;
	}
	/* A competing enable is not ours to force OFF by changing pad mux. */
	if (__clk_is_enabled(power->xclk))
		return imx882_power_fault(power, -EBUSY);
	if (power->mclk_selected) {
		ret = pinctrl_select_state(power->pinctrl, power->mclk_off);
		if (ret)
			return imx882_power_fault(power, ret);
		power->mclk_selected = false;
	}
	for (supply = IMX882_NUM_SUPPLIES - 1; supply >= 0; supply--) {
		if (!(*enabled_supplies & BIT(supply)))
			continue;
		ret = regulator_disable(power->supplies[supply].consumer);
		if (ret)
			return imx882_power_fault(power, ret);
		/* This clears only our successful reference, not another user's rail. */
		*enabled_supplies &= ~BIT(supply);
	}
	imx882_mclk_release(power);
	return 0;
}

static int imx882_power_on(struct imx882_identity *power,
			   unsigned long *enabled_supplies, bool *clock_enabled)
{
	int ret;

	if (power->first_error)
		return power->first_error;
	if (*enabled_supplies || *clock_enabled || power->rate_exclusive ||
	    power->source_rate_exclusive || power->mclk_selected)
		return -EBUSY;
	ret = imx882_idle_check(power);
	if (ret)
		return ret;
	ret = imx882_mclk_acquire(power);
	if (ret)
		return ret;
	/* Reobserve supplies before the first reset direction/output write. */
	ret = imx882_idle_check(power);
	if (ret) {
		imx882_mclk_release(power);
		return ret;
	}
	ret = gpiod_direction_output(power->reset, 1);
	if (!ret)
		ret = imx882_reset_observe(power, 1);
	if (ret)
		return imx882_power_fault(power, ret);

	ret = imx882_enable_supply(power, IMX882_SUPPLY_AFVDD);
	if (ret)
		return ret;
	*enabled_supplies |= BIT(IMX882_SUPPLY_AFVDD);
	usleep_range(1000, 1100);
	ret = imx882_enable_supply(power, IMX882_SUPPLY_AVDD);
	if (ret)
		return ret;
	*enabled_supplies |= BIT(IMX882_SUPPLY_AVDD);
	ret = imx882_enable_supply(power, IMX882_SUPPLY_DVDD);
	if (ret)
		return ret;
	*enabled_supplies |= BIT(IMX882_SUPPLY_DVDD);
	usleep_range(1000, 1100);
	ret = imx882_enable_supply(power, IMX882_SUPPLY_DOVDD);
	if (ret)
		return ret;
	*enabled_supplies |= BIT(IMX882_SUPPLY_DOVDD);
	usleep_range(1000, 1100);
	ret = pinctrl_select_state(power->pinctrl, power->mclk_4ma);
	if (ret)
		return imx882_power_fault(power, ret);
	power->mclk_selected = true;
	ret = clk_prepare_enable(power->xclk);
	if (ret)
		return imx882_power_fault(power, ret);
	*clock_enabled = true;
	usleep_range(5000, 5100);
	ret = imx882_mclk_check(power);
	if (!ret)
		ret = imx882_supplies_observe(power, 1);
	if (ret)
		return imx882_power_fault(power, ret);
	ret = imx882_reset_set(power, 0);
	if (ret)
		return ret;
	usleep_range(1000, 1100);
	return 0;
}
