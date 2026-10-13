/* SPDX-License-Identifier: GPL-2.0-only */
/* Native pad callbacks run with the sensor's existing active-state mutex held. */
static int imx882_enable_streams(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask)
{
	if (pad || mask != 1)
		return -EINVAL;
	return imx882_stream_locked(sd, 1);
}

static int imx882_disable_streams(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask)
{
	if (pad || mask != 1)
		return -EINVAL;
	return imx882_stream_locked(sd, 0);
}

static int imx882_power(struct v4l2_subdev *sd, int on)
{
	struct imx882_camera *camera = to_imx882(sd);
	int ret;

	if (on)
		return -EOPNOTSUPP;
	mutex_lock(&camera->lock);
	ret = v4l2_subdev_is_streaming(sd) ? -EBUSY : imx882_stop(camera);
	mutex_unlock(&camera->lock);
	return ret;
}

static const struct v4l2_subdev_core_ops imx882_core_ops = {
	.s_power = imx882_power,
};
