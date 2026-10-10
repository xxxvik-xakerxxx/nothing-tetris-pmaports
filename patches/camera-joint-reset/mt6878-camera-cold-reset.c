// SPDX-License-Identifier: GPL-2.0-only
#include <linux/clk-provider.h>
#include <linux/irq.h>
#include <linux/pm_runtime.h>
#include <linux/property.h>
#include "mt6878-camera-cold-reset.h"

static int cold_irq_off(int irq)
{
	struct irq_data *data = irq_get_irq_data(irq);

	return data && irq_has_action(irq) && irqd_irq_disabled(data) ? 0 : -EBUSY;
}

static int cold_power(struct mt6878_native_capture *n, unsigned int port)
{
	struct mt6878_seninf_controller *c = &n->controller;
	unsigned int i;
	int voltage;

	if (!pm_runtime_active(&c->pdev->dev) || !n->platform.powered ||
	    !pm_runtime_active(c->domains[0]) || !pm_runtime_active(c->domains[1]))
		return -EHOSTDOWN;
	/* Match native PM's actual 0..2 + CAMTM + selected CSI ownership.
	 * Unselected muxes/PLL alternatives are not owned enable references.
	 */
	if (port > 1 || c->num_clocks != 12 ||
	    !clk_is_match(c->route.csi_clock, c->clocks[3 + port].clk))
		return -EINVAL;
	for (i = 0; i < 3; i++)
		if (!__clk_is_enabled(c->clocks[i].clk))
			return -EHOSTDOWN;
	if (!__clk_is_enabled(c->clocks[7].clk) || !__clk_is_enabled(c->route.csi_clock))
		return -EHOSTDOWN;
	if (c->dvfs[4] * 1000000ULL != clk_get_rate(c->route.csi_clock))
		return -EOPNOTSUPP;
	voltage = regulator_get_voltage(c->vcore);
	if (voltage < 0)
		return voltage;
	/* Shared VCORE: native PM votes step[5]..INT_MAX, regulator core enforces
	 * provider constraints. step[6] is not a global upper safety limit.
	 */
	return voltage >= c->dvfs[5] ? 0 : -ERANGE;
}

/* Exact e96 PHY3.1 set_cammux_src/disable sequence, already traced by the
 * frozen route_disconnect recipe. OFF-only: it needs no fictional PHY ON.
 */
static int cold_mapping(struct device *dev)
{
	static const char * const names[] = {
		"mux-camsv-sat-range", "muxvr-camsv-sat-range", "cammux-camsv-sat-range",
	};
	static const u32 expected[][2] = { { 0, 2 }, { 0, 23 }, { 0, 15 } };
	u32 range[2];
	unsigned int i;
	int ret;

	/* Exact ee2 MT6878 DT supplier metadata, as frozen route_mapping checks. */
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

static int cold_disconnect(struct mt6878_camera_cold_reset *cold)
{
	const struct mt6878_seninf_backend *io = &cold->controller->route.backend.io;
	struct mt6878_seninf_transaction *tx = &cold->off;
	unsigned int bank, i, page, b, bit;
	int ret = 0;

#define OFF(off, mask, value) do { \
	if (!ret) \
		ret = mt6878_seninf_update(io, tx, MT6878_SENINF_BASE, off, mask, value); \
} while (0)
	for (bank = 0; !ret && bank < 2; bank++) {
		OFF(0x17f04, 0x80, bank ? 0 : 0x80);
		for (i = 0; !ret && i < 2; i++) {
			b = 0x17000 + cold->plan.cammux[i] * 0x40;
			bit = 1U << cold->plan.cammux[i];
			OFF(0x17fc0, bit, 0);
			OFF(b, 0x7f0000, 0x7f0000);
			OFF(b, 0x7f, 0x7f);
			OFF(b, 0x80, 0);
			for (page = 0; !ret && page < 4; page++) {
				OFF(b + 4, 0x07000000, page << 24);
				if (!ret)
					ret = mt6878_route_write(io, tx, MT6878_SENINF_BASE, b + 0x20, 0);
				if (!ret)
					ret = mt6878_route_write(io, tx, MT6878_SENINF_BASE, b + 0x24, 0);
			}
			if (!ret)
				ret = mt6878_route_write(io, tx, MT6878_SENINF_BASE, b + 0xc, 0x103);
			OFF(0xd00 + cold->plan.outputs[i].mux * 0x1000, 1, 0);
		}
	}
#undef OFF
	return ret;
}

static int cold_readback(struct mt6878_camera_cold_reset *cold)
{
	const struct mt6878_seninf_backend *io = &cold->controller->route.backend.io;
	u32 bank, i, value, b;
	int ret = 0;

	for (bank = 0; !ret && bank < 2; bank++) {
		ret = mt6878_seninf_update(io, &cold->off, MT6878_SENINF_BASE,
			0x17f04, 0x80, bank ? 0 : 0x80);
		for (i = 0; !ret && i < 2; i++) {
			b = 0x17000 + cold->plan.cammux[i] * 0x40;
			ret = io->read(io->context, MT6878_SENINF_BASE, b, &value);
			if (!ret && (value & 0x7f00ff) != 0x7f007f)
				ret = -EIO;
			if (!ret)
				ret = io->read(io->context, MT6878_SENINF_BASE,
					0xd00 + cold->plan.outputs[i].mux * 0x1000, &value);
			if (!ret && (value & 1))
				ret = -EIO;
		}
	}
	return ret;
}

static int cold_inactive_pages(struct mt6878_camera_cold_reset *cold)
{
	const struct mt6878_seninf_backend *io = &cold->controller->route.backend.io;
	u32 original, bank;
	int ret, restore;

	ret = io->read(io->context, MT6878_SENINF_BASE, 0x17f04, &original);
	if (ret)
		return ret;
	for (bank = 0; !ret && bank < 2; bank++) {
		ret = mt6878_seninf_update(io, &cold->off, MT6878_SENINF_BASE,
			0x17f04, 0x80, bank ? 0 : 0x80);
		if (!ret)
			ret = mt6878_route_preflight(io, &cold->plan);
	}
	restore = mt6878_seninf_update(io, &cold->off, MT6878_SENINF_BASE,
		0x17f04, 0x80, original & 0x80);
	return ret ? ret : restore;
}

int mt6878_camera_cold_prepare(struct mt6878_camera_cold_reset *cold,
	struct mt6878_native_capture *n, const struct mt6878_camsv_job *job,
	unsigned int port, unsigned int pixel_mode)
{
	struct mt6878_seninf_controller *c;
	struct mt6878_seninf_events observed;
	struct mt6878_seninf_transaction events = { 0 };
	unsigned int i, intf, mux;
	int ret;

	if (!cold || !n || !n->bound || !job || port > 1 || pixel_mode > 7 || job->sv_id > 1)
		return -EINVAL;
	if (!((job->width == 4000 && job->height == 3000) ||
	    (job->width == 4096 && job->height == 2304)) ||
	    job->raw_tag > 7 || job->pdaf_tag > 7 || job->raw_tag == job->pdaf_tag ||
	    job->sv_id != n->direct.resources.sv_id)
		return -EINVAL;
	lockdep_assert_held(&n->lock);
	lockdep_assert_held(&n->platform.lifecycle);
	c = &n->controller;
	if (cold->allocated || cold->first_error || c->allocated || c->requested != 2 ||
	    n->platform.requested != 4 || n->platform.enabled || c->irq_enabled ||
	    !n->platform.media_owned || !n->receiver_ref || !n->smi_ref ||
	    c->route.phy.attempted || c->route.route.attempted || n->direct.pair.tx.attempted)
		return -EBUSY;
	ret = cold_mapping(&c->pdev->dev);
	if (!ret)
		ret = cold_power(n, port);
	for (i = 0; !ret && i < 4; i++)
		ret = cold_irq_off(n->direct.resources.irqs[i]);
	if (!ret)
		ret = cold_irq_off(c->irq);
	if (!ret)
		ret = cold_irq_off(c->tsrec_irq);
	if (ret)
		return ret;
	/* No core/queue/state lock is held across actual IRQ completion waits. */
	for (i = 0; i < 4; i++)
		synchronize_irq(n->direct.resources.irqs[i]);
	synchronize_irq(c->irq);
	synchronize_irq(c->tsrec_irq);
	cold->irq_drained = true;
	cold->attempted = true;
	ret = v4l2_subdev_call(n->platform.sensor, core, s_power, 0);
	if (ret)
		return ret;
	cold->sensor_cleaned = true;
	mutex_lock(&c->core);
	if (c->allocated || c->intfs || c->muxes || c->cammuxes) {
		ret = -EBUSY;
		goto out;
	}
	cold->controller = c;
	cold->plan.width = job->width;
	cold->plan.height = job->height;
	intf = find_first_zero_bit(&c->intfs, 12);
	set_bit(intf, &c->intfs);
	for (i = 0; i < 2; i++) {
		mux = find_first_zero_bit(&c->muxes, 3);
		set_bit(mux, &c->muxes);
		cold->plan.outputs[i] = (struct mt6878_seninf_plan) {
			port, intf, mux, i ? 0 : 1, pixel_mode,
		};
		cold->plan.tags[i] = i ? job->pdaf_tag : job->raw_tag;
		cold->plan.cammux[i] = job->sv_id * 8 + cold->plan.tags[i];
	}
	ret = mt6878_route_validate(&c->route.backend.io, &cold->plan);
	if (ret) {
		c->intfs = c->muxes = 0; /* No controller allocation existed; no MMIO yet. */
		goto out;
	}
	for (i = 0; i < 2; i++)
		set_bit(cold->plan.cammux[i], &c->cammuxes);
	cold->allocated = true; /* Actual bitmap reservation, not route readiness. */
	ret = mt6878_seninf_events_preflight(&c->route.backend.io, &cold->plan);
	if (!ret)
		ret = cold_inactive_pages(cold);
	if (!ret)
		ret = mt6878_seninf_tsrec_disable(&c->route.backend.io, &cold->tsrec);
	if (!ret)
		ret = mt6878_seninf_mask_events(&c->route.backend.io, &cold->plan, &events);
	if (!ret)
		ret = mt6878_seninf_sample_events(&c->route.backend.io, &cold->plan, &observed);
	if (!ret && (observed.g1[0] || observed.g1[1]))
		ret = -EOPNOTSUPP; /* No source-proven G1 ACK; keep quarantine. */
	if (!ret)
		ret = mt6878_seninf_ack_events(&c->route.backend.io, &cold->plan, &events, &observed);
	if (!ret)
		ret = cold_disconnect(cold);
	if (!ret)
		ret = cold_readback(cold);
	if (!ret)
		cold->disconnected = true;
out:
	if (ret && cold->allocated && !cold->first_error)
		cold->first_error = ret; /* Retain real reservations after possible MMIO. */
	mutex_unlock(&c->core);
	return ret;
}

int mt6878_camera_cold_verify(struct mt6878_camera_cold_reset *cold,
	struct mt6878_native_capture *n, const struct mt6878_camsv_job *job)
{
	struct mt6878_seninf_controller *c = &n->controller;
	unsigned int i;
	int ret;

	lockdep_assert_held(&c->core);
	if (!cold || cold->controller != c || !cold->allocated || cold->first_error ||
	    !cold->sensor_cleaned || !cold->irq_drained || !cold->disconnected ||
	    cold->plan.width != job->width || cold->plan.height != job->height ||
	    c->allocated || c->route.phy.attempted || c->route.route.attempted)
		return -EBUSY;
	for (i = 0; i < 2; i++)
		if (!test_bit(cold->plan.outputs[i].intf, &c->intfs) ||
		    !test_bit(cold->plan.outputs[i].mux, &c->muxes) ||
		    !test_bit(cold->plan.cammux[i], &c->cammuxes) ||
		    cold->plan.cammux[i] != job->sv_id * 8 + (i ? job->pdaf_tag : job->raw_tag))
			return -ESTALE;
	ret = cold_power(n, cold->plan.outputs[0].port);
	return ret ? ret : cold_readback(cold);
}

int mt6878_camera_cold_release(struct mt6878_camera_cold_reset *cold,
	struct mt6878_native_capture *n)
{
	struct mt6878_seninf_controller *c = &n->controller;
	unsigned int i;

	lockdep_assert_held(&n->lock);
	if (!cold->allocated)
		return 0;
	mutex_lock(&c->core);
	if (cold->controller != c || cold->first_error || !cold->disconnected || c->allocated) {
		mutex_unlock(&c->core);
		return -EBUSY;
	}
	for (i = 0; i < 2; i++) {
		clear_bit(cold->plan.outputs[i].intf, &c->intfs);
		clear_bit(cold->plan.outputs[i].mux, &c->muxes);
		clear_bit(cold->plan.cammux[i], &c->cammuxes);
	}
	cold->allocated = false;
	mutex_unlock(&c->core);
	return 0;
}
