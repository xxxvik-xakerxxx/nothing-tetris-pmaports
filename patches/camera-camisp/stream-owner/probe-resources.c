/* SPDX-License-Identifier: GPL-2.0-only */

static int imx882_resources_get(struct imx882_camera *camera)
{
	struct device *dev = &camera->client->dev;
	struct imx882_identity *power = &camera->power;
	int ret, i;

	for (i = 0; i < IMX882_NUM_SUPPLIES; i++) {
		char property[32];

		snprintf(property, sizeof(property), "%s-supply", imx882_supply_names[i]);
		if (!device_property_present(dev, property))
			return -EINVAL;
		power->supplies[i].supply = imx882_supply_names[i];
	}
	ret = regulator_bulk_get(dev, IMX882_NUM_SUPPLIES, power->supplies);
	if (ret)
		return ret;
	camera->supplies_acquired = true;
	power->xclk = clk_get(dev, "xclk");
	if (IS_ERR(power->xclk))
		return PTR_ERR(power->xclk);
	power->xclk_source = clk_get(dev, "xclk-source");
	if (IS_ERR(power->xclk_source))
		return PTR_ERR(power->xclk_source);
	power->pinctrl = pinctrl_get(dev);
	if (IS_ERR(power->pinctrl))
		return PTR_ERR(power->pinctrl);
	power->mclk_off = pinctrl_lookup_state(power->pinctrl, "mclk-off");
	if (IS_ERR(power->mclk_off))
		return PTR_ERR(power->mclk_off);
	power->mclk_4ma = pinctrl_lookup_state(power->pinctrl, "mclk-4ma");
	if (IS_ERR(power->mclk_4ma))
		return PTR_ERR(power->mclk_4ma);
	/* ASIS still has a mux-writing request callback; this is not handoff proof. */
	ret = imx882_idle_check(power);
	if (ret)
		return ret;
	power->reset = gpiod_get(dev, "reset", GPIOD_ASIS);
	if (IS_ERR(power->reset))
		return PTR_ERR(power->reset);
	if (!gpiod_is_active_low(power->reset))
		return -EINVAL;
	return 0;
}
