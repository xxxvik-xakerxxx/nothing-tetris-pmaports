/* SPDX-License-Identifier: GPL-2.0-only */
/* Real resource lifetime, including remove after an unsuccessful shutdown. */

static bool imx882_power_active(struct imx882_camera *camera)
{
	return camera->enabled_supplies || camera->clock_enabled ||
		camera->power.rate_exclusive || camera->power.source_rate_exclusive ||
		camera->power.mclk_selected;
}

static int imx882_camera_fault(struct imx882_camera *camera, int error)
{
	if (!camera->first_error)
		camera->first_error = error;
	camera->faulted = true;
	return camera->first_error;
}

static void imx882_resources_put(struct imx882_camera *camera)
{
	struct imx882_identity *power = &camera->power;
	struct device *dev = &camera->client->dev;

	if (!IS_ERR_OR_NULL(power->reset))
		gpiod_put(power->reset);
	if (!IS_ERR_OR_NULL(power->pinctrl))
		pinctrl_put(power->pinctrl);
	if (!IS_ERR_OR_NULL(power->xclk_source))
		clk_put(power->xclk_source);
	if (!IS_ERR_OR_NULL(power->xclk))
		clk_put(power->xclk);
	if (camera->supplies_acquired)
		regulator_bulk_free(IMX882_NUM_SUPPLIES, power->supplies);
	kfree(camera);
	put_device(dev);
}

static int imx882_stop(struct imx882_camera *camera)
{
	int ret = 0, cleanup;

	if (camera->power.first_error)
		return imx882_camera_fault(camera, camera->power.first_error);
	if (camera->streaming) {
		ret = imx882_write(camera, 0x0100, 0);
		if (ret)
			imx882_camera_fault(camera, ret);
	}
	cleanup = imx882_power_off(&camera->power, &camera->enabled_supplies,
				 &camera->clock_enabled);
	if (cleanup)
		return imx882_camera_fault(camera, cleanup);
	/* Reset containment and successful reference releases permit a fresh start. */
	camera->streaming = false;
	camera->faulted = false;
	camera->first_error = 0;
	return ret;
}
