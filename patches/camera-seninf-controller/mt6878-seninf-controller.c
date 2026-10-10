// SPDX-License-Identifier: GPL-2.0-only
#include <linux/clk-provider.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/irq.h>
#include <linux/pm_runtime.h>
#include <linux/property.h>
#include "mt6878-seninf-controller.h"

static int remember(struct mt6878_seninf_controller *c, int ret)
{
	if (ret && !c->first_error)
		c->first_error = ret;
	return ret;
}

static int power(struct mt6878_seninf_controller *c)
{
	unsigned int i;
	int voltage;

	if (!pm_runtime_active(&c->pdev->dev) || !c->capture->powered ||
	    !pm_runtime_active(c->domains[0]) || !pm_runtime_active(c->domains[1]))
		return -EHOSTDOWN;
	for (i = 0; i < c->num_clocks; i++)
		if (!__clk_is_enabled(c->clocks[i].clk))
			return -EHOSTDOWN;
	/* Exact ee2 DT step0 tuple, but read actual provider metadata/voltage.
	 * This owner does not choose/set a guessed rail or clock rate.
	 */
	if (c->dvfs[4] * 1000000ULL != clk_get_rate(c->route.csi_clock))
		return -EOPNOTSUPP;
	voltage = regulator_get_voltage(c->vcore);
	if (voltage < 0)
		return voltage;
	if (voltage < c->dvfs[5] || voltage > c->dvfs[6])
		return -ERANGE;
	return 0;
}

static int mapped(struct mt6878_seninf_controller *c, enum mt6878_seninf_region region,
	unsigned int offset, void __iomem **address)
{
	unsigned long size = region == MT6878_SENINF_BASE ? 0x18000 : 0x30000;
	/* Full rail/domain checks occur at transaction gates. The parent retains
	 * supplier refs across the whole transaction, including failed teardown.
	 */
	if (!pm_runtime_active(&c->pdev->dev) || !__clk_is_enabled(c->route.csi_clock))
		return -EHOSTDOWN;
	if ((region != MT6878_SENINF_BASE && region != MT6878_SENINF_ANALOG) ||
	    (offset & 3) || offset > size - 4)
		return -EINVAL;
	*address = (region == MT6878_SENINF_BASE ? c->base : c->analog) + offset;
	return 0;
}

static int read_reg(void *context, enum mt6878_seninf_region region,
	unsigned int offset, unsigned int *value)
{
	void __iomem *address;
	int ret = mapped(context, region, offset, &address);

	if (!ret)
		*value = readl(address);
	return ret;
}

static int write_reg(void *context, enum mt6878_seninf_region region,
	unsigned int offset, unsigned int value)
{
	void __iomem *address;
	int ret = mapped(context, region, offset, &address);

	if (!ret)
		writel(value, address);
	return ret;
}

static int delay_us(void *context, unsigned int us)
{
	(void)context;
	if (us > 200)
		return -EINVAL;
	udelay(us);
	return 0;
}

static int owned_plan(struct mt6878_seninf_controller *c, const struct mt6878_seninf_plan *p)
{
	unsigned int i;

	lockdep_assert_held(&c->core);
	if (!c->allocated || !c->capture->media_owned)
		return -EBUSY;
	for (i = 0; i < 2; i++) {
		const struct mt6878_seninf_plan *a = &c->allocation.outputs[i];

		if (p->port == a->port && p->intf == a->intf && p->mux == a->mux &&
		    p->group == a->group && p->pixel_mode == a->pixel_mode &&
		    test_bit(p->intf, &c->intfs) && test_bit(p->mux, &c->muxes) &&
		    test_bit(c->allocation.cammux[i], &c->cammuxes))
			return 0;
	}
	return -EINVAL;
}

static int check(void *context, enum mt6878_seninf_action action,
	const struct mt6878_seninf_plan *p)
{
	struct mt6878_seninf_controller *c = context;
	int ret = owned_plan(c, p);

	if (!ret)
		ret = power(c);
	if (ret)
		return ret;
	if (action == MT6878_MUX_SETUP)
		return c->route.phy.configured && c->route.source_stopped ? 0 : -EPIPE;
	if (action == MT6878_RECEIVER_OFF)
		return c->irq_drained && c->route.source_stopped && c->route.route.disconnected &&
			c->capture->direct->pair.tx.quiesced ? 0 : -EBUSY;
	return -EOPNOTSUPP;
}

static int verify(void *context, enum mt6878_phy_owner owner,
	const struct mt6878_seninf_plan *p, const struct mt6878_phy_inputs *in)
{
	struct mt6878_seninf_controller *c = context;
	int ret = owned_plan(c, p);

	if (!ret)
		ret = power(c);
	if (ret)
		return ret;
	if (in->rg_csi_verified != 1 || in->rg_csi_port != p->port ||
	    in->csi_clock_hz != clk_get_rate(c->route.csi_clock))
		return -ESTALE;
	switch (owner) {
	case MT6878_PHY_POWER:
		return c->route.source_stopped ? 0 : -EBUSY;
	case MT6878_PHY_IRQ:
		return c->requested == 2 && irq_has_action(c->irq) &&
			irq_has_action(c->tsrec_irq) ? 0 : -ENODEV;
	case MT6878_PHY_ROUTE:
		return 0; /* Exact native allocation checked above, not caller ready. */
	case MT6878_PHY_TSREC:
		return c->tsrec_disabled && !c->tsrec.first_error ? 0 : -EPIPE;
	case MT6878_PHY_QUIESCED:
		return c->irq_drained && c->tsrec_disabled &&
			c->capture->drained && c->route.source_stopped &&
			c->route.route.disconnected && c->capture->direct->pair.tx.quiesced ? 0 : -EBUSY;
	}
	return -EINVAL;
}

static irqreturn_t receiver_irq(int irq, void *context)
{
	struct mt6878_seninf_controller *c = context;
	struct mt6878_seninf_events sample = { 0 };
	struct mt6878_seninf_transaction tx = { 0 };
	struct mt6878_camsv_direct *direct = c->capture->direct;
	int ret;

	(void)irq;
	/* No core/queue lock across IRQ drain. Single registered ONESHOT thread.
	 * On any receiver event, mask first and schedule existing native stop.
	 */
	ret = mt6878_seninf_sample_events(&c->route.backend.io, &c->allocation, &sample);
	if (!ret && !sample.mac[0] && !sample.mac[1] && !sample.g1[0] &&
	    !sample.g1[1] && !sample.csi && !(sample.cphy & 0xff0000) &&
	    !(sample.mux[0] & 0xf) && !(sample.mux[1] & 0xf))
		return IRQ_NONE;
	c->observed = sample;
	if (!ret)
		ret = mt6878_seninf_mask_events(&c->route.backend.io, &c->allocation, &tx);
	if (!ret)
		ret = mt6878_seninf_ack_events(&c->route.backend.io, &c->allocation, &tx, &sample);
	mutex_lock(&direct->lock);
	if (!direct->first_error)
		direct->first_error = ret ? ret : -EIO;
	mutex_unlock(&direct->lock);
	mt6878_camsv_platform_stop_async(c->capture);
	return IRQ_HANDLED;
}

static irqreturn_t tsrec_irq(int irq, void *context)
{
	(void)irq;
	(void)context;
	/* Line is requested NO_AUTOEN and NEVER enabled in first-frame mode.
	 * TSREC engines/interrupts are actually disabled before PHY setup.
	 */
	return IRQ_NONE;
}

int mt6878_seninf_controller_bind(struct mt6878_seninf_controller *c,
	struct platform_device *pdev, struct mt6878_camsv_platform *capture,
	void __iomem *base, void __iomem *analog, struct clk_bulk_data *clocks,
	unsigned int num_clocks, struct device **domains, struct regulator *vcore,
	struct clk *csi_clock, const struct v4l2_mbus_config_mipi_csi2 *endpoint,
	unsigned int sensor_pad)
{
	struct resource *resource;
	u32 count;
	unsigned int i;
	int ret;

	if (!c || !pdev || !capture || !capture->direct || !capture->sensor ||
	    !capture->receiver || !capture->media_owned || !base || !analog ||
	    !clocks || num_clocks != 12 || !domains || IS_ERR_OR_NULL(domains[0]) ||
	    IS_ERR_OR_NULL(domains[1]) || IS_ERR_OR_NULL(vcore) ||
	    IS_ERR_OR_NULL(csi_clock) || !endpoint || c->requested ||
	    v4l2_get_subdev_hostdata(capture->receiver))
		return -EINVAL;
	if (capture->receiver->dev != &pdev->dev || endpoint->num_data_lanes != 3 ||
	    sensor_pad >= capture->sensor->entity.num_pads)
		return -EINVAL;
	if (!v4l2_subdev_has_op(capture->sensor, pad, enable_streams) ||
	    !v4l2_subdev_has_op(capture->sensor, pad, disable_streams) ||
	    !v4l2_subdev_has_op(capture->sensor, core, s_power) ||
	    !v4l2_subdev_has_op(capture->receiver, pad, enable_streams) ||
	    !v4l2_subdev_has_op(capture->receiver, pad, disable_streams))
		return -EOPNOTSUPP;
	for (i = 0; i < num_clocks; i++)
		if (IS_ERR_OR_NULL(clocks[i].clk))
			return -EINVAL;
	resource = platform_get_resource_byname(pdev, IORESOURCE_MEM, "base");
	if (!resource || resource_size(resource) != 0x18000)
		return -EINVAL;
	resource = platform_get_resource_byname(pdev, IORESOURCE_MEM, "ana-rx");
	if (!resource || resource_size(resource) != 0x30000)
		return -EINVAL;
	ret = device_property_read_u32(&pdev->dev, "tsrec-num", &count);
	if (ret || count != 6)
		return ret ? ret : -EINVAL;
	c->irq = platform_get_irq_byname(pdev, "seninf-irq");
	if (c->irq < 0)
		return c->irq;
	c->tsrec_irq = platform_get_irq_byname(pdev, "tsrec-irq");
	if (c->tsrec_irq < 0)
		return c->tsrec_irq;
	mutex_init(&c->core);
	c->pdev = pdev;
	c->capture = capture;
	c->base = base;
	c->analog = analog;
	c->clocks = clocks;
	c->num_clocks = num_clocks;
	c->domains = domains;
	c->vcore = vcore;
	ret = device_property_read_u32_array(&pdev->dev, "cdphy-dvfs-step0", c->dvfs, 7);
	if (ret || !c->dvfs[4] || !c->dvfs[5] || c->dvfs[6] < c->dvfs[5])
		return ret ? ret : -EINVAL;
	c->route.core_lock = &c->core;
	c->route.sensor = capture->sensor;
	c->route.receiver = capture->receiver;
	c->route.sensor_pad = sensor_pad;
	c->route.csi_clock = csi_clock;
	c->route.endpoint = *endpoint;
	c->route.backend = (struct mt6878_phy_backend) {
		.io = { .check = check, .read = read_reg, .write = write_reg,
			.delay_us = delay_us, .context = c, .base_size = 0x18000, .analog_size = 0x30000 },
		.verify = verify,
	};
	ret = request_threaded_irq(c->irq, NULL, receiver_irq,
		IRQF_ONESHOT | IRQF_NO_AUTOEN, "mt6878-seninf-first-frame", c);
	if (ret)
		return ret;
	c->requested = 1;
	ret = request_threaded_irq(c->tsrec_irq, NULL, tsrec_irq,
		IRQF_ONESHOT | IRQF_NO_AUTOEN, "mt6878-tsrec-disabled", c);
	if (ret) {
		free_irq(c->irq, c);
		c->requested = 0;
		return ret;
	}
	c->requested = 2;
	v4l2_set_subdev_hostdata(capture->receiver, c);
	return 0;
}

int mt6878_seninf_controller_prepare(struct mt6878_seninf_controller *c,
	const struct mt6878_camsv_job *job, unsigned int port, unsigned int pixel_mode)
{
	unsigned int i;
	int ret;

	if (!c || c->requested != 2 || !job || job->sv_id > 1)
		return -EINVAL;
	mutex_lock(&c->core);
	mutex_lock(&c->capture->direct->lock);
	if (c->allocated || c->first_error || port > 1 || pixel_mode > 7) {
		ret = -EBUSY;
		goto out;
	}
	/* One embedded core owns all allocations. No external reservation flag.
	 * B4.1 RAW group=RAW1(1), PDAF default group=ALL(0), both VC0.
	 */
	c->allocation.width = job->width;
	c->allocation.height = job->height;
	for (i = 0; i < 2; i++) {
		unsigned int intf = find_first_zero_bit(&c->intfs, 12);
		unsigned int mux = find_first_zero_bit(&c->muxes, 3);
		unsigned int tag = i ? job->pdaf_tag : job->raw_tag;

		if (!i)
			set_bit(intf, &c->intfs);
		else
			intf = c->allocation.outputs[0].intf;
		set_bit(mux, &c->muxes);
		c->allocation.outputs[i] = (struct mt6878_seninf_plan) {
			port, intf, mux, i ? 0 : 1, pixel_mode,
		};
		c->allocation.tags[i] = tag;
		c->allocation.cammux[i] = job->sv_id * 8 + tag;
	}
	ret = mt6878_route_validate(&c->route.backend.io, &c->allocation);
	if (ret)
		goto unreserve;
	for (i = 0; i < 2; i++)
		set_bit(c->allocation.cammux[i], &c->cammuxes);
	c->allocated = true;
	ret = power(c);
	if (!ret)
		ret = mt6878_seninf_events_preflight(&c->route.backend.io, &c->allocation);
	if (!ret)
		ret = mt6878_seninf_tsrec_disable(&c->route.backend.io, &c->tsrec);
	if (!ret) {
		c->tsrec_disabled = true;
		ret = mt6878_seninf_route_prepare(&c->route, &c->allocation);
	}
	remember(c, ret);
	goto out; /* Keep reservations/refs after any possible MMIO failure. */
unreserve:
	c->intfs = c->muxes = c->cammuxes = 0;
out:
	mutex_unlock(&c->capture->direct->lock);
	mutex_unlock(&c->core);
	return ret;
}

int mt6878_seninf_controller_gate(struct mt6878_seninf_controller *c,
	enum mt6878_camsv_owner gate, const struct mt6878_camsv_job *job)
{
	const struct mt6878_route_plan *p;
	int ret;

	if (!c || !c->capture || !job || c->requested != 2)
		return -ENODEV;
	lockdep_assert_held(&c->capture->direct->lock);
	if (!c->allocated)
		return -ENOLINK;
	p = &c->allocation;
	if (job->width != p->width || job->height != p->height ||
	    job->raw_tag != p->tags[0] || job->pdaf_tag != p->tags[1] ||
	    job->sv_id * 8 + job->raw_tag != p->cammux[0] ||
	    job->sv_id * 8 + job->pdaf_tag != p->cammux[1])
		return -EINVAL;
	ret = power(c);
	if (ret)
		return ret;
	if (gate == MT6878_SV_ROUTE)
		return !c->first_error && !c->route.first_error &&
			!c->route.phy.bus.first_error && !c->route.route.bus.first_error &&
			c->route.phy.configured && c->route.route.configured &&
			!c->route.route.disconnected && c->route.source_stopped &&
			!c->route.source_attempted ? 0 : -EPIPE;
	if (gate == MT6878_SV_STOPPED)
		return c->irq_drained && c->capture->drained && c->tsrec_disabled &&
			c->route.source_stopped && c->route.route.disconnected ? 0 : -EBUSY;
	return -EINVAL;
}

int mt6878_seninf_controller_enable(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask)
{
	struct mt6878_seninf_controller *c = v4l2_get_subdev_hostdata(sd);
	struct mt6878_camsv_direct *direct;
	int ret;

	(void)state;
	if (!c || pad != 1 || mask != 1)
		return -EINVAL;
	direct = c->capture->direct;
	mutex_lock(&c->core);
	mutex_lock(&direct->lock);
	ret = mt6878_seninf_route_matches(&c->route, &direct->pair.tx.job);
	if (!ret && (!direct->pair.tx.submitted || direct->pair.tx.off_attempted ||
	    direct->pair.tx.first_error || direct->first_error || c->first_error ||
	    c->route.source_attempted))
		ret = -EPIPE;
	if (!ret && (!v4l2_subdev_has_op(c->route.sensor, pad, enable_streams) ||
		!v4l2_subdev_has_op(c->route.sensor, pad, disable_streams)))
		ret = -EOPNOTSUPP; /* Never fall back to error-swallowing legacy stop. */
	if (!ret) {
		enable_irq(c->irq);
		c->irq_enabled = true;
		c->route.source_attempted = true;
		c->route.source_stopped = false;
		ret = v4l2_subdev_enable_streams(c->route.sensor, c->route.sensor_pad, 1);
	}
	remember(c, ret);
	mutex_unlock(&direct->lock);
	mutex_unlock(&c->core);
	return ret;
}

int mt6878_seninf_controller_drain(struct mt6878_seninf_controller *c)
{
	struct mt6878_seninf_transaction tx = { 0 };
	int ret;

	if (!c || c->requested != 2 || !c->allocated)
		return -EINVAL;
	/* Parent lifecycle serialized; no self-drain, no core/queue lock held. */
	if (c->irq_enabled) {
		disable_irq(c->irq);
		c->irq_enabled = false;
	}
	mutex_lock(&c->core);
	mutex_lock(&c->capture->direct->lock);
	ret = mt6878_seninf_mask_events(&c->route.backend.io, &c->allocation, &tx);
	if (!ret)
		ret = mt6878_seninf_sample_events(&c->route.backend.io, &c->allocation, &c->observed);
	if (!ret)
		ret = mt6878_seninf_ack_events(&c->route.backend.io, &c->allocation, &tx, &c->observed);
	if (!ret)
		c->irq_drained = true;
	remember(c, ret);
	mutex_unlock(&c->capture->direct->lock);
	mutex_unlock(&c->core);
	return ret;
}

int mt6878_seninf_controller_disable(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask)
{
	struct mt6878_seninf_controller *c = v4l2_get_subdev_hostdata(sd);
	int ret;

	(void)state;
	if (!c || pad != 1 || mask != 1)
		return -EINVAL;
	ret = mt6878_seninf_controller_drain(c);
	if (ret)
		return ret;
	mutex_lock(&c->core);
	mutex_lock(&c->capture->direct->lock);
	ret = v4l2_subdev_disable_streams(c->route.sensor, c->route.sensor_pad, 1);
	if (!ret) {
		c->route.source_stopped = true;
		ret = mt6878_route_disconnect(&c->route.backend.io, &c->route.route);
	}
	remember(c, ret);
	mutex_unlock(&c->capture->direct->lock);
	mutex_unlock(&c->core);
	return ret;
}

int mt6878_seninf_controller_release(struct mt6878_seninf_controller *c)
{
	int ret;

	if (!c || c->requested != 2 || !c->allocated)
		return -EINVAL;
	mutex_lock(&c->core);
	mutex_lock(&c->capture->direct->lock);
	ret = mt6878_seninf_route_retire(&c->route, c->capture->direct);
	if (!ret) {
		v4l2_set_subdev_hostdata(c->route.receiver, NULL);
		c->requested = 0;
		c->allocated = false;
		c->intfs = c->muxes = c->cammuxes = 0;
	}
	mutex_unlock(&c->capture->direct->lock);
	if (!ret) {
		free_irq(c->tsrec_irq, c);
		free_irq(c->irq, c);
	}
	mutex_unlock(&c->core);
	return ret;
}
