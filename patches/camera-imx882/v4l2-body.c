/* SPDX-License-Identifier: GPL-2.0-only */
/* Appended to the existing, checked IMX882 board power helpers by generate.py. */

struct imx882_camera {
	struct imx882_identity power;
	struct v4l2_subdev sd;
	struct media_pad pad;
	struct v4l2_ctrl_handler controls;
	struct v4l2_ctrl *vblank;
	struct v4l2_ctrl *exposure;
	struct v4l2_ctrl *gain;
	struct v4l2_ctrl *hblank;
	struct v4l2_mbus_config_mipi_csi2 cphy;
	/* Shared with active-state and control locks; serializes power and I2C. */
	struct mutex lock;
	struct i2c_client *client;
	const struct imx882_mode *mode;
	unsigned long enabled_supplies;
	bool clock_enabled;
	bool streaming;
	bool faulted;
};

static struct imx882_camera *to_imx882(struct v4l2_subdev *sd)
{
	return container_of(sd, struct imx882_camera, sd);
}

static int imx882_write(void *context, unsigned short address,
			unsigned char value)
{
	struct imx882_camera *camera = context;
	u8 data[] = { address >> 8, address & 0xff, value };
	int ret = i2c_master_send(camera->client, data, sizeof(data));

	return ret < 0 ? ret : ret == sizeof(data) ? 0 : -EIO;
}

static struct imx882_bus imx882_bus(struct imx882_camera *camera)
{
	return (struct imx882_bus) { .write = imx882_write, .context = camera };
}

static int imx882_apply_controls(struct imx882_camera *camera)
{
	struct imx882_bus bus = imx882_bus(camera);

	return imx882_write_controls(&bus,
		camera->mode->height + camera->vblank->val,
		camera->exposure->val, camera->gain->val);
}

static int imx882_set_control(struct v4l2_ctrl *ctrl)
{
	struct imx882_camera *camera = container_of(ctrl->handler,
		struct imx882_camera, controls);
	int ret = 0;

	if (ctrl->id == V4L2_CID_VBLANK) {
		int maximum = camera->mode->height + ctrl->val - 64;

		__v4l2_ctrl_modify_range(camera->exposure, 6, maximum, 1,
					min(1000, maximum));
	}
	if (camera->faulted)
		return -EIO;
	if (camera->streaming)
		ret = imx882_apply_controls(camera);
	if (ret)
		camera->faulted = true;
	return ret;
}

static const struct v4l2_ctrl_ops imx882_control_ops = {
	.s_ctrl = imx882_set_control,
};

static void imx882_fill_format(const struct imx882_mode *mode,
			       struct v4l2_mbus_framefmt *format)
{
	*format = (struct v4l2_mbus_framefmt) {
		.width = mode->width, .height = mode->height,
		.code = MEDIA_BUS_FMT_SRGGB10_1X10,
		.field = V4L2_FIELD_NONE, .colorspace = V4L2_COLORSPACE_RAW,
	};
}

static int imx882_init_state(struct v4l2_subdev *sd,
			     struct v4l2_subdev_state *state)
{
	imx882_fill_format(&imx882_modes[0],
			   v4l2_subdev_state_get_format(state, 0));
	return 0;
}

static int imx882_enum_code(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, struct v4l2_subdev_mbus_code_enum *code)
{
	if (code->pad || code->index || code->stream)
		return -EINVAL;
	code->code = MEDIA_BUS_FMT_SRGGB10_1X10;
	return 0;
}

static int imx882_enum_size(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, struct v4l2_subdev_frame_size_enum *size)
{
	if (size->pad || size->stream || size->index >= ARRAY_SIZE(imx882_modes) ||
	    size->code != MEDIA_BUS_FMT_SRGGB10_1X10)
		return -EINVAL;
	size->min_width = size->max_width = imx882_modes[size->index].width;
	size->min_height = size->max_height = imx882_modes[size->index].height;
	return 0;
}

static int imx882_set_format(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, struct v4l2_subdev_format *format)
{
	struct imx882_camera *camera = to_imx882(sd);
	const struct imx882_mode *mode;

	if (format->pad || format->stream)
		return -EINVAL;
	mode = v4l2_find_nearest_size(imx882_modes, ARRAY_SIZE(imx882_modes),
				    width, height, format->format.width,
				    format->format.height);
	if (format->which == V4L2_SUBDEV_FORMAT_ACTIVE && camera->streaming)
		return -EBUSY;
	imx882_fill_format(mode, &format->format);
	*v4l2_subdev_state_get_format(state, 0) = format->format;
	if (format->which == V4L2_SUBDEV_FORMAT_ACTIVE) {
		camera->mode = mode;
		__v4l2_ctrl_modify_range(camera->hblank, 7500 - mode->width,
					7500 - mode->width, 1, 7500 - mode->width);
		__v4l2_ctrl_modify_range(camera->vblank, 3900 - mode->height,
			65535 - mode->height, 1, 3900 - mode->height);
		__v4l2_ctrl_s_ctrl(camera->vblank, 3900 - mode->height);
	}
	return 0;
}

static int imx882_get_interval(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, struct v4l2_subdev_frame_interval *interval)
{
	struct imx882_camera *camera = to_imx882(sd);
	unsigned int frame_length = 3900;

	if (interval->pad || interval->stream)
		return -EINVAL;
	if (interval->which == V4L2_SUBDEV_FORMAT_ACTIVE)
		frame_length = camera->mode->height + camera->vblank->val;
	interval->interval.numerator = frame_length * 7500;
	interval->interval.denominator = 878400000;
	return 0;
}

static int imx882_mbus_config(struct v4l2_subdev *sd, unsigned int pad,
			      struct v4l2_mbus_config *config)
{
	struct imx882_camera *camera = to_imx882(sd);

	if (pad)
		return -EINVAL;
	memset(config, 0, sizeof(*config));
	config->type = V4L2_MBUS_CSI2_CPHY;
	config->bus.mipi_csi2 = camera->cphy;
	/* No invented link frequency: this requires the receiver clock contract. */
	return 0;
}

static int imx882_frame_desc(struct v4l2_subdev *sd, unsigned int pad,
			     struct v4l2_mbus_frame_desc *desc)
{
	struct imx882_camera *camera = to_imx882(sd);

	if (pad)
		return -EINVAL;
	mutex_lock(&camera->lock);
	memset(desc, 0, sizeof(*desc));
	desc->type = V4L2_MBUS_FRAME_DESC_TYPE_CSI2;
	/* The unchanged vendor modes also emit PDAF on VC0, DT0x30. */
	desc->num_entries = 2;
	desc->entry[0].pixelcode = MEDIA_BUS_FMT_SRGGB10_1X10;
	desc->entry[0].flags = V4L2_MBUS_FRAME_DESC_FL_LEN_MAX;
	desc->entry[0].length = camera->mode->width * camera->mode->height * 10 / 8;
	desc->entry[0].bus.csi2.vc = 0;
	desc->entry[0].bus.csi2.dt = 0x2b;
	desc->entry[1].bus.csi2.vc = 0;
	desc->entry[1].bus.csi2.dt = 0x30;
	/* Vendor frame_desc: width x (height / 4), remapped to RAW10. */
	desc->entry[1].flags = V4L2_MBUS_FRAME_DESC_FL_BLOB |
			       V4L2_MBUS_FRAME_DESC_FL_LEN_MAX;
	desc->entry[1].length = camera->mode->width * (camera->mode->height / 4) * 10 / 8;
	mutex_unlock(&camera->lock);
	return 0;
}

static int imx882_stop(struct imx882_camera *camera)
{
	int ret = 0, cleanup;

	if (camera->streaming)
		ret = imx882_write(camera, 0x0100, 0);
	cleanup = imx882_power_off(&camera->power, camera->enabled_supplies,
				 camera->clock_enabled);
	if (!ret)
		ret = cleanup;
	camera->streaming = false;
	if (cleanup) {
		/* An uncertain supply reference must not be enabled a second time. */
		camera->faulted = true;
		return ret;
	}
	camera->enabled_supplies = 0;
	camera->clock_enabled = false;
	camera->faulted = false;
	return ret;
}

static int imx882_stream(struct v4l2_subdev *sd, int enable)
{
	struct imx882_camera *camera = to_imx882(sd);
	struct imx882_bus bus = imx882_bus(camera);
	u8 high, low;
	int ret, cleanup;

	mutex_lock(&camera->lock);
	if (!enable) {
		ret = camera->streaming ? imx882_stop(camera) : 0;
		goto unlock;
	}
	if (camera->faulted) {
		ret = -EIO;
		goto unlock;
	}
	if (camera->streaming) {
		ret = 0;
		goto unlock;
	}
	ret = imx882_power_on(&camera->power, &camera->enabled_supplies,
			      &camera->clock_enabled);
	if (ret)
		goto failed;
	ret = imx882_read_reg(camera->client, IMX882_REG_CHIP_ID_HIGH, &high);
	if (ret)
		goto failed;
	ret = imx882_read_reg(camera->client, IMX882_REG_CHIP_ID_LOW, &low);
	if (ret)
		goto failed;
	if (((high << 8) | low) != IMX882_CHIP_ID) {
		ret = -ENODEV;
		goto failed;
	}
	ret = imx882_write_table(&bus, imx882_init_regs,
				 ARRAY_SIZE(imx882_init_regs));
	if (ret)
		goto failed;
	ret = imx882_write(camera, 0x0101, 0); /* vendor IMAGE_NORMAL */
	if (ret)
		goto failed;
	/* Vendor's documented no-QSC branch; never write another unit's EEPROM. */
	ret = imx882_write(camera, 0x3206, 0);
	if (ret)
		goto failed;
	ret = imx882_write_table(&bus, camera->mode->regs, camera->mode->count);
	if (ret)
		goto failed;
	ret = imx882_apply_controls(camera);
	if (ret)
		goto failed;
	ret = imx882_write(camera, 0x0100, 1);
	if (ret)
		goto failed;
	camera->streaming = true;
	goto unlock;
failed:
	/* Reset/power-down contains even an ambiguous final stream-on write. */
	cleanup = imx882_stop(camera);
	if (cleanup)
		dev_err(&camera->client->dev, "camera cleanup failed: %d\n", cleanup);
	dev_err(&camera->client->dev, "camera start failed: %d\n", ret);
unlock:
	mutex_unlock(&camera->lock);
	return ret;
}

static const struct v4l2_subdev_video_ops imx882_video_ops = {
	.s_stream = imx882_stream,
};

static const struct v4l2_subdev_pad_ops imx882_pad_ops = {
	.enum_mbus_code = imx882_enum_code,
	.enum_frame_size = imx882_enum_size,
	.get_fmt = v4l2_subdev_get_fmt,
	.set_fmt = imx882_set_format,
	.get_frame_desc = imx882_frame_desc,
	.get_frame_interval = imx882_get_interval,
	.get_mbus_config = imx882_mbus_config,
};

static const struct v4l2_subdev_ops imx882_subdev_ops = {
	.video = &imx882_video_ops,
	.pad = &imx882_pad_ops,
};

static const struct v4l2_subdev_internal_ops imx882_internal_ops = {
	.init_state = imx882_init_state,
};

static int imx882_camera_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct v4l2_fwnode_endpoint endpoint = {
		.bus_type = V4L2_MBUS_CSI2_CPHY,
	};
	struct fwnode_handle *ep;
	struct imx882_camera *camera;
	struct imx882_identity *power;
	struct v4l2_ctrl *pixel_rate;
	u32 lanes[3], xclk_rate;
	int ret, i;

	ep = fwnode_graph_get_next_endpoint(dev_fwnode(dev), NULL);
	if (!ep)
		return dev_err_probe(dev, -EINVAL, "missing C-PHY endpoint\n");
	/* Parser otherwise silently replaces duplicate mappings with defaults. */
	ret = fwnode_property_count_u32(ep, "data-lanes");
	if (ret != ARRAY_SIZE(lanes)) {
		fwnode_handle_put(ep);
		return dev_err_probe(dev, -EINVAL, "requires explicit three-trio mapping\n");
	}
	ret = fwnode_property_read_u32_array(ep, "data-lanes", lanes,
					   ARRAY_SIZE(lanes));
	if (!ret && (lanes[0] != 0 || lanes[1] != 1 || lanes[2] != 2))
		ret = -EINVAL;
	if (ret) {
		fwnode_handle_put(ep);
		return dev_err_probe(dev, ret, "unsupported sensor C-PHY trio mapping\n");
	}
	ret = v4l2_fwnode_endpoint_parse(ep, &endpoint);
	fwnode_handle_put(ep);
	if (ret)
		return ret;
	if (endpoint.bus_type != V4L2_MBUS_CSI2_CPHY ||
	    endpoint.bus.mipi_csi2.num_data_lanes != 3)
		return dev_err_probe(dev, -EINVAL, "requires three C-PHY trios\n");
	ret = device_property_read_u32(dev, "clock-frequency", &xclk_rate);
	if (ret || xclk_rate != IMX882_XCLK_RATE)
		return dev_err_probe(dev, -EINVAL, "requires explicit 24 MHz xclk claim\n");
	camera = devm_kzalloc(dev, sizeof(*camera), GFP_KERNEL);
	if (!camera)
		return -ENOMEM;
	power = &camera->power;
	camera->client = client;
	camera->mode = &imx882_modes[0];
	camera->cphy = endpoint.bus.mipi_csi2;
	for (i = 0; i < IMX882_NUM_SUPPLIES; i++)
		power->supplies[i].supply = imx882_supply_names[i];
	ret = devm_regulator_bulk_get(dev, IMX882_NUM_SUPPLIES, power->supplies);
	if (ret)
		return dev_err_probe(dev, ret, "camera supplies unavailable\n");
	power->xclk = devm_clk_get(dev, "xclk");
	if (IS_ERR(power->xclk))
		return PTR_ERR(power->xclk);
	power->reset = devm_gpiod_get(dev, "reset", GPIOD_ASIS);
	if (IS_ERR(power->reset))
		return PTR_ERR(power->reset);
	if (!gpiod_is_active_low(power->reset))
		return dev_err_probe(dev, -EINVAL, "reset must be active-low\n");
	ret = gpiod_direction_output(power->reset, 1);
	if (ret)
		return ret;
	power->pinctrl = devm_pinctrl_get(dev);
	if (IS_ERR(power->pinctrl))
		return PTR_ERR(power->pinctrl);
	power->mclk_off = pinctrl_lookup_state(power->pinctrl, "mclk-off");
	if (IS_ERR(power->mclk_off))
		return PTR_ERR(power->mclk_off);
	power->mclk_4ma = pinctrl_lookup_state(power->pinctrl, "mclk-4ma");
	if (IS_ERR(power->mclk_4ma))
		return PTR_ERR(power->mclk_4ma);
	mutex_init(&camera->lock);
	v4l2_i2c_subdev_init(&camera->sd, client, &imx882_subdev_ops);
	camera->sd.internal_ops = &imx882_internal_ops;
	camera->sd.flags |= V4L2_SUBDEV_FL_HAS_DEVNODE;
	camera->sd.entity.function = MEDIA_ENT_F_CAM_SENSOR;
	camera->sd.state_lock = &camera->lock;
	v4l2_ctrl_handler_init(&camera->controls, 5);
	camera->controls.lock = &camera->lock;
	camera->vblank = v4l2_ctrl_new_std(&camera->controls, &imx882_control_ops,
		V4L2_CID_VBLANK, 900, 62535, 1, 900);
	camera->exposure = v4l2_ctrl_new_std(&camera->controls, &imx882_control_ops,
		V4L2_CID_EXPOSURE, 6, 3836, 1, 1000);
	camera->gain = v4l2_ctrl_new_std(&camera->controls, &imx882_control_ops,
		V4L2_CID_ANALOGUE_GAIN, 1463, 65536, 1, 4096);
	camera->hblank = v4l2_ctrl_new_std(&camera->controls, NULL,
		V4L2_CID_HBLANK, 3500, 3500, 1, 3500);
	if (camera->hblank)
		camera->hblank->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	/* Upstream PIXEL_RATE describes the pixel-array sampling clock, not
	 * the vendor MIPI transport rate. This preserves frame timing with
	 * the source-grounded 7500-pixel line length and VBLANK contract.
	 */
	pixel_rate = v4l2_ctrl_new_std(&camera->controls, NULL,
		V4L2_CID_PIXEL_RATE, 878400000, 878400000, 1, 878400000);
	if (pixel_rate)
		pixel_rate->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	ret = camera->controls.error;
	if (ret)
		goto free_controls;
	camera->sd.ctrl_handler = &camera->controls;
	camera->pad.flags = MEDIA_PAD_FL_SOURCE;
	ret = media_entity_pads_init(&camera->sd.entity, 1, &camera->pad);
	if (ret)
		goto free_controls;
	ret = v4l2_subdev_init_finalize(&camera->sd);
	if (ret)
		goto clean_entity;
	ret = v4l2_async_register_subdev_sensor(&camera->sd);
	if (!ret)
		return 0;
	v4l2_subdev_cleanup(&camera->sd);
clean_entity:
	media_entity_cleanup(&camera->sd.entity);
free_controls:
	v4l2_ctrl_handler_free(&camera->controls);
	mutex_destroy(&camera->lock);
	return ret;
}

static void imx882_camera_remove(struct i2c_client *client)
{
	struct v4l2_subdev *sd = i2c_get_clientdata(client);
	struct imx882_camera *camera = to_imx882(sd);
	int ret;

	v4l2_async_unregister_subdev(sd);
	mutex_lock(&camera->lock);
	ret = camera->streaming ? imx882_stop(camera) : 0;
	mutex_unlock(&camera->lock);
	if (ret)
		dev_err(&client->dev, "camera removal shutdown failed: %d\n", ret);
	v4l2_subdev_cleanup(sd);
	media_entity_cleanup(&sd->entity);
	v4l2_ctrl_handler_free(&camera->controls);
	mutex_destroy(&camera->lock);
}

static int imx882_camera_suspend(struct device *dev)
{
	struct v4l2_subdev *sd = dev_get_drvdata(dev);
	struct imx882_camera *camera = to_imx882(sd);
	int ret;

	mutex_lock(&camera->lock);
	/* The receiver must stop the stream first; do not silently lose frames. */
	ret = camera->streaming || camera->faulted ? -EBUSY : 0;
	mutex_unlock(&camera->lock);
	return ret;
}

static DEFINE_SIMPLE_DEV_PM_OPS(imx882_camera_pm, imx882_camera_suspend, NULL);

static const struct of_device_id imx882_camera_of_match[] = {
	{ .compatible = "nothing,tetris-imx882-stream" },
	{ }
};
MODULE_DEVICE_TABLE(of, imx882_camera_of_match);

static struct i2c_driver imx882_camera_driver = {
	.probe = imx882_camera_probe,
	.remove = imx882_camera_remove,
	.driver = {
		.name = "tetris-imx882-stream",
		.of_match_table = imx882_camera_of_match,
		.pm = pm_sleep_ptr(&imx882_camera_pm),
	},
};
module_i2c_driver(imx882_camera_driver);

MODULE_DESCRIPTION("Nothing Tetris IMX882 C-PHY sensor");
MODULE_LICENSE("GPL");
