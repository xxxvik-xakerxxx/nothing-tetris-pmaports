// SPDX-License-Identifier: GPL-2.0-only
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/pm_runtime.h>
#include <linux/of.h>
#include <linux/property.h>
#include <media/media-entity.h>
#include "mt6878-camsv-hardware.h"
#include "mt6878-seninf-contract.h"
#include "mt6878-seninf-route.h"

static int route_error(struct mt6878_seninf_route *r, int ret)
{
	if (ret && !r->first_error)
		r->first_error = ret;
	return ret;
}

static int route_resources(struct mt6878_seninf_route *r)
{
	struct media_link *link;

	if (!r || !r->core_lock || !r->sensor || !r->receiver || !r->sensor->dev ||
	    !r->receiver->dev || IS_ERR_OR_NULL(r->csi_clock) ||
	    r->sensor_pad >= r->sensor->entity.num_pads || !r->receiver->entity.num_pads)
		return -EINVAL;
	lockdep_assert_held(r->core_lock);
	if (!of_device_is_compatible(r->sensor->dev->of_node, "nothing,tetris-imx882-stream"))
		return -EOPNOTSUPP;
	link = media_entity_find_link(&r->sensor->entity.pads[r->sensor_pad],
		&r->receiver->entity.pads[0]);
	if (!link || !(link->flags & MEDIA_LNK_FL_ENABLED) || (link->flags & MEDIA_LNK_FL_DYNAMIC) ||
	    !media_entity_pipeline(&r->receiver->entity) ||
	    media_entity_pipeline(&r->receiver->entity) != media_entity_pipeline(&r->sensor->entity))
		return -ENOLINK;
	if (!pm_runtime_active(r->receiver->dev) || !__clk_is_enabled(r->csi_clock))
		return -EHOSTDOWN;
	return 0;
}

static int route_sensor(struct mt6878_seninf_route *r, const struct mt6878_route_plan *p)
{
	struct v4l2_subdev_format fmt = {
		.which = V4L2_SUBDEV_FORMAT_ACTIVE, .pad = r->sensor_pad,
	};
	struct v4l2_mbus_frame_desc desc = { 0 };
	struct v4l2_mbus_config bus = { 0 };
	struct mt6878_seninf_packet packets[2];
	unsigned int lanes[3], i;
	int ret;

	ret = v4l2_subdev_call(r->sensor, pad, get_fmt, NULL, &fmt);
	if (ret)
		return ret;
	if (fmt.format.code != MEDIA_BUS_FMT_SRGGB10_1X10 ||
	    fmt.format.width != p->width || fmt.format.height != p->height)
		return -EINVAL;
	ret = v4l2_subdev_call(r->sensor, pad, get_mbus_config, r->sensor_pad, &bus);
	if (ret)
		return ret;
	if (bus.type != V4L2_MBUS_CSI2_CPHY || bus.bus.mipi_csi2.num_data_lanes != 3 ||
	    r->endpoint.num_data_lanes != 3 || bus.bus.mipi_csi2.flags != r->endpoint.flags ||
	    bus.bus.mipi_csi2.lane_polarities[0] || r->endpoint.lane_polarities[0])
		return -EINVAL;
	for (i = 0; i < 3; i++) {
		lanes[i] = bus.bus.mipi_csi2.data_lanes[i];
		if (lanes[i] != r->endpoint.data_lanes[i] ||
		    bus.bus.mipi_csi2.line_orders[i] != r->endpoint.line_orders[i] ||
		    bus.bus.mipi_csi2.lane_polarities[i + 1] || r->endpoint.lane_polarities[i + 1])
			return -EINVAL;
	}
	ret = mt6878_seninf_check_trios(3, lanes);
	if (!ret)
		ret = v4l2_subdev_call(r->sensor, pad, get_frame_desc, r->sensor_pad, &desc);
	if (ret)
		return ret;
	if (desc.type != V4L2_MBUS_FRAME_DESC_TYPE_CSI2 || desc.num_entries != 2)
		return -EINVAL;
	for (i = 0; i < 2; i++)
		packets[i] = (struct mt6878_seninf_packet) {
			desc.entry[i].bus.csi2.vc, desc.entry[i].bus.csi2.dt, desc.entry[i].length,
		};
	return mt6878_seninf_check_packets(p->width, p->height, 2, packets);
}

static int route_mapping(struct device *dev)
{
	static const char * const names[] = {
		"mux-camsv-sat-range", "muxvr-camsv-sat-range", "cammux-camsv-sat-range",
	};
	static const u32 expected[][2] = { { 0, 2 }, { 0, 23 }, { 0, 15 } };
	u32 range[2];
	unsigned int i;
	int ret;

	/* Reject absent/different supplier mapping, never assume physical mux
	 * numbers are CAMMUX source codes. Exact ee2 MT6878 SAT mapping only.
	 */
	for (i = 0; i < ARRAY_SIZE(names); i++) {
		ret = device_property_count_u32(dev, names[i]);
		if (ret != 2)
			return ret < 0 ? ret : -EINVAL;
		ret = device_property_read_u32_array(dev, names[i], range, 2);
		if (ret)
			return ret;
		if (range[0] != expected[i][0] || range[1] != expected[i][1])
			return -EOPNOTSUPP;
	}
	return 0;
}

int mt6878_seninf_route_prepare(struct mt6878_seninf_route *r,
	const struct mt6878_route_plan *p)
{
	struct mt6878_phy_inputs in = { 0 };
	unsigned int i;
	enum mt6878_phy_owner owner;
	int ret;

	ret = route_resources(r);
	if (ret)
		return ret;
	if (r->phy.attempted || r->route.attempted || r->source_attempted || r->first_error)
		return -EBUSY;
	ret = mt6878_route_validate(&r->backend.io, p);
	if (!ret)
		ret = route_mapping(r->receiver->dev);
	if (!ret)
		ret = route_sensor(r, p);
	if (ret)
		return ret;
	ret = v4l2_subdev_call(r->sensor, video, s_stream, 0);
	if (ret)
		return route_error(r, ret);
	r->source_stopped = true;
	in.mode = p->width == 4096;
	in.mipi_pixel_rate = 700800000;
	in.dphy_trail_ns = in.mode ? 0x31 : 0x47;
	for (i = 0; i < 3; i++)
		in.lanes[i] = r->endpoint.data_lanes[i];
	ret = mt6878_seninf_calibration_read(r->receiver->dev, r->csi_clock,
		p->outputs[0].port, &in);
	/* Validate BOTH allocated destinations before PHY can write. */
	if (!ret)
		ret = mt6878_phy_validate(&r->backend, &p->outputs[0], &in);
	for (owner = MT6878_PHY_POWER; !ret && owner <= MT6878_PHY_TSREC; owner++)
		ret = r->backend.verify(r->backend.io.context, owner, &p->outputs[0], &in);
	for (i = 0; !ret && i < 2; i++)
		ret = r->backend.verify(r->backend.io.context, MT6878_PHY_ROUTE,
			&p->outputs[i], &in);
	if (!ret)
		ret = mt6878_route_preflight(&r->backend.io, p);
	if (!ret)
		ret = mt6878_phy_setup(&r->backend, &r->phy, &p->outputs[0], &in);
	if (!ret)
		ret = mt6878_route_setup(&r->backend.io, p, &r->route);
	return route_error(r, ret);
}

int mt6878_seninf_route_matches(struct mt6878_seninf_route *r,
	const struct mt6878_camsv_job *j)
{
	const struct mt6878_route_plan *p;

	if (!r || !j || !r->core_lock)
		return -EINVAL;
	lockdep_assert_held(r->core_lock);
	if (!r->route.configured || !r->phy.configured || r->first_error ||
	    r->route.bus.first_error || r->phy.bus.first_error)
		return -EPIPE;
	p = &r->route.plan;
	if (j->width != p->width || j->height != p->height ||
	    j->raw_tag != p->tags[0] || j->pdaf_tag != p->tags[1] ||
	    j->sv_id * 8 + j->raw_tag != p->cammux[0] ||
	    j->sv_id * 8 + j->pdaf_tag != p->cammux[1])
		return -EINVAL;
	return 0;
}

int mt6878_seninf_route_source_on(struct mt6878_seninf_route *r,
	struct mt6878_camsv_direct *capture)
{
	int ret = route_resources(r);

	if (ret || !capture)
		return ret ? ret : -EINVAL;
	lockdep_assert_held(&capture->lock);
	if (r->source_attempted || !r->source_stopped ||
	    !capture->pair.tx.submitted || capture->pair.tx.off_attempted ||
	    capture->pair.tx.first_error || capture->first_error)
		return -EPIPE;
	if (clk_get_rate(r->csi_clock) != r->phy.inputs.csi_clock_hz)
		return route_error(r, -ESTALE);
	ret = mt6878_seninf_route_matches(r, &capture->pair.tx.job);
	if (!ret)
		ret = route_sensor(r, &r->route.plan);
	if (ret)
		return route_error(r, ret);
	r->source_attempted = true;
	r->source_stopped = false; /* Failed stream-on still requires real stream-off. */
	ret = v4l2_subdev_call(r->sensor, video, s_stream, 1);
	return route_error(r, ret);
}

int mt6878_seninf_route_source_off(struct mt6878_seninf_route *r)
{
	int ret = route_resources(r);

	if (ret)
		return ret;
	if (!r->source_stopped) {
		ret = v4l2_subdev_call(r->sensor, video, s_stream, 0);
		if (ret)
			return route_error(r, ret);
		r->source_stopped = true;
	}
	if (r->route.attempted && !r->route.disconnected)
		ret = mt6878_route_disconnect(&r->backend.io, &r->route);
	/* Return cleanup result; first causal error remains separately retained. */
	return route_error(r, ret);
}

int mt6878_seninf_route_retire(struct mt6878_seninf_route *r,
	struct mt6878_camsv_direct *capture)
{
	int ret = route_resources(r);

	if (ret || !capture)
		return ret ? ret : -EINVAL;
	lockdep_assert_held(&capture->lock);
	if (!r->source_stopped || (r->route.attempted && !r->route.disconnected) ||
	    (capture->pair.tx.hw_attempted && !capture->pair.tx.quiesced))
		return -EBUSY;
	/* Existing PHY QUIESCED check independently verifies MAC/PHY IRQ drain
	 * and TSREC ownership. CAMSV quiesced alone cannot discharge those owners.
	 */
	ret = r->phy.attempted ? mt6878_phy_off(&r->backend, &r->phy) : 0;
	return route_error(r, ret);
}
