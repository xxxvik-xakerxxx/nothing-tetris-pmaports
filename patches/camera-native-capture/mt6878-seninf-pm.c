// SPDX-License-Identifier: GPL-2.0-only
#include <linux/limits.h>
#include <linux/bitmap.h>
#include <linux/math64.h>
#include <linux/pm_runtime.h>
#include <linux/property.h>
#include "mt6878-seninf-pm.h"

/* e96 seninf-drv runtime_resume / set_vcore_power / set_csi_clk:
 * domains -> CAM gates/CAMTM -> VCORE vote -> CSI enable/parent.
 * Only full port0/1 and DT step0; no AOV, timer programming or MMDVFS/VCP.
 */
static int enable_clock(struct mt6878_seninf_pm *p, unsigned int index)
{
	int ret = clk_prepare_enable(p->clocks[index].clk);

	if (!ret)
		set_bit(index, &p->clock_refs);
	return ret;
}

static void disable_clock(struct mt6878_seninf_pm *p, unsigned int index)
{
	if (test_bit(index, &p->clock_refs)) {
		clk_disable_unprepare(p->clocks[index].clk);
		clear_bit(index, &p->clock_refs);
	}
}

static int release(struct mt6878_seninf_pm *p)
{
	unsigned int csi = 3 + p->port;
	int i, ret;

	lockdep_assert_held(&p->lock);
	disable_clock(p, csi);
	if (p->parent_changed) {
		if (!clk_is_match(clk_get_parent(p->clocks[csi].clk), p->clocks[8].clk))
			return -ESTALE;
		ret = clk_set_parent(p->clocks[csi].clk, p->old_parent);
		if (ret)
			return ret; /* Keep base clocks, domains and voltage vote. */
		p->parent_changed = false;
	}
	if (p->rate_owned) {
		clk_rate_exclusive_put(p->clocks[csi].clk);
		p->rate_owned = false;
	}
	disable_clock(p, 7);
	for (i = 2; i >= 0; i--)
		disable_clock(p, i);
	if (p->voltage_vote) {
		/* Remove only this regulator consumer's vote; do not restore a sampled
		 * global voltage, which could overwrite another consumer's request.
		 */
		ret = regulator_set_voltage(p->vcore, 0, INT_MAX);
		if (ret)
			return ret;
		p->voltage_vote = false;
	}
	for (i = 1; i >= 0; i--) {
		if (!(p->domain_refs & BIT(i)))
			continue;
		ret = pm_runtime_put_sync_suspend(p->domains[i]);
		if (ret < 0) {
			/* put consumed the usage ref even on failed suspend. Restore the
			 * ref without changing hardware state, retaining failed ownership.
			 */
			pm_runtime_get_noresume(p->domains[i]);
			return ret;
		}
		p->domain_refs &= ~BIT(i);
	}
	return 0;
}

int mt6878_seninf_pm_init(struct mt6878_seninf_pm *p, struct device *dev,
	struct device **domains, struct clk_bulk_data *clocks,
	unsigned int count, struct regulator *vcore, unsigned int port)
{
	unsigned int i;
	int ret;

	if (!p || !dev || !domains || !clocks || count != 12 || port > 1 ||
	    IS_ERR_OR_NULL(vcore) || p->dev)
		return -EINVAL;
	for (i = 0; i < 2; i++)
		if (IS_ERR_OR_NULL(domains[i]) || !pm_runtime_enabled(domains[i]))
			return -EPROBE_DEFER;
	for (i = 0; i < count; i++)
		if (IS_ERR_OR_NULL(clocks[i].clk))
			return -EINVAL;
	ret = device_property_read_u32_array(dev, "cdphy-dvfs-step0", p->step, 7);
	if (ret)
		return ret;
	/* Restricted calibrated PHY supports the pinned 312MHz step. Threshold
	 * and voltage remain board metadata, not per-handset/default values.
	 */
	if (!p->step[0] || !p->step[1] || p->step[4] != 312 ||
	    !p->step[5] || p->step[5] != p->step[6])
		return -EINVAL;
	/* Exact e96 IMX882 module mipi_pixel_rate, NOT V4L2 pixel-array PCLK.
	 * Vendor CPHY comparison: mipi rate * bpp * 7 / (trios * 16).
	 */
	if (p->step[0] * 1000000ULL <= div_u64(700800000ULL * 10 * 7, 3 * 16))
		return -ERANGE;
	if (clk_get_rate(clocks[8].clk) != p->step[4] * 1000000ULL)
		return -ERANGE;
	mutex_init(&p->lock);
	p->domains = domains;
	p->clocks = clocks;
	p->vcore = vcore;
	p->port = port;
	p->dev = dev;
	return 0;
}

int mt6878_seninf_pm_resume(struct mt6878_seninf_pm *p)
{
	unsigned int i, csi;
	int ret, cleanup, voltage;

	if (!p || !p->dev)
		return -EINVAL;
	mutex_lock(&p->lock);
	if (p->first_error || p->domain_refs || p->clock_refs || p->voltage_vote || p->rate_owned) {
		ret = p->first_error ? p->first_error : -EBUSY;
		goto out;
	}
	csi = 3 + p->port;
	ret = clk_rate_exclusive_get(p->clocks[csi].clk);
	if (ret)
		goto out;
	p->rate_owned = true;
	p->old_parent = clk_get_parent(p->clocks[csi].clk);
	if (IS_ERR_OR_NULL(p->old_parent)) {
		ret = -ENODEV;
		goto fail;
	}
	for (i = 0; i < 2; i++) {
		ret = pm_runtime_resume_and_get(p->domains[i]);
		if (ret < 0)
			goto fail;
		p->domain_refs |= BIT(i);
	}
	for (i = 0; i < 3; i++) {
		ret = enable_clock(p, i);
		if (ret)
			goto fail;
	}
	ret = enable_clock(p, 7);
	if (ret)
		goto fail;
	ret = regulator_set_voltage(p->vcore, p->step[5], INT_MAX);
	if (ret)
		goto fail;
	p->voltage_vote = true;
	voltage = regulator_get_voltage(p->vcore);
	if (voltage < 0 || voltage < p->step[5]) {
		ret = voltage < 0 ? voltage : -ERANGE;
		goto fail;
	}
	ret = enable_clock(p, csi);
	if (ret)
		goto fail;
	ret = clk_set_parent(p->clocks[csi].clk, p->clocks[8].clk);
	if (ret)
		goto fail;
	p->parent_changed = true;
	if (clk_get_rate(p->clocks[csi].clk) != p->step[4] * 1000000ULL) {
		ret = -ERANGE;
		goto fail;
	}
	ret = 0;
	goto out;
fail:
	p->first_error = ret;
	cleanup = release(p);
	if (cleanup)
		dev_err(p->dev, "SENINF PM cleanup failed: %d; first error: %d\n", cleanup, ret);
out:
	mutex_unlock(&p->lock);
	return ret;
}

int mt6878_seninf_pm_suspend(struct mt6878_seninf_pm *p)
{
	int ret;

	if (!p || !p->dev)
		return -EINVAL;
	mutex_lock(&p->lock);
	ret = release(p);
	if (ret && !p->first_error)
		p->first_error = ret;
	mutex_unlock(&p->lock);
	return ret;
}

bool mt6878_seninf_pm_busy(struct mt6878_seninf_pm *p)
{
	bool busy;

	mutex_lock(&p->lock);
	busy = p->domain_refs || p->clock_refs || p->voltage_vote || p->parent_changed || p->rate_owned;
	mutex_unlock(&p->lock);
	return busy;
}
