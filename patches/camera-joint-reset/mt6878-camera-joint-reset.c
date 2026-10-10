// SPDX-License-Identifier: GPL-2.0-only
#include <linux/clk-provider.h>
#include <linux/iopoll.h>
#include <linux/irq.h>
#include <linux/pm_runtime.h>
#include <soc/mediatek/cam-main-lease.h>
#include <soc/mediatek/smi-camera-reset.h>
#include "mt6878-camera-joint-reset.h"

/* e96 mtk_cam-sv-regs.h REG_CAM_MAIN_SW_RST_1; SCQ uses frozen SV_CQ_RESET. */
#define CAM_MAIN_SW_RESET 0x0058

static int joint_once(struct mt6878_camera_joint_reset *transaction)
{
	if (!transaction)
		return -EINVAL;
	if (transaction->first_error)
		return transaction->first_error;
	return transaction->attempted ? -EALREADY : 0;
}

static int joint_finish(struct mt6878_camera_joint_reset *transaction,
	struct mt6878_native_capture *n, int first, int cleanup)
{
	int ret = first ? first : cleanup;

	lockdep_assert_held(&n->lock);
	transaction->lease_retire_error = cleanup;
	if (ret) {
		if (!transaction->first_error)
			transaction->first_error = ret;
		if (!n->first_error)
			n->first_error = ret;
		/* Also quarantine cleanup failures before the first reset write. */
		n->reset_attempted = true;
		n->reset_completed = false;
		transaction->completed = false;
	} else if (transaction->attempted) {
		transaction->completed = true;
		n->reset_completed = true;
	}
	return ret;
}

static int irq_off(int irq)
{
	struct irq_data *data = irq_get_irq_data(irq);

	if (!data || !irq_has_action(irq) || !irqd_irq_disabled(data))
		return -EBUSY;
	return 0;
}

static int joint_preflight(struct mt6878_native_capture *n,
	const struct mt6878_camsv_job *layout, struct mt6878_camera_cold_reset *cold)
{
	struct mt6878_camsv_direct *d = &n->direct;
	struct mt6878_camsv_platform *p = &n->platform;
	struct mt6878_seninf_controller *c = &n->controller;
	struct resource *resource;
	unsigned int i;
	int ret;

	lockdep_assert_held(&n->lock);
	lockdep_assert_held(&p->lifecycle);
	lockdep_assert_held(&c->core);
	lockdep_assert_held(&d->lock);
	if (n->first_error)
		return n->first_error;
	if (!n->bound || p->direct != d || c->capture != p ||
	    p->retired || !p->powered || p->enabled || (!cold && !p->drained) ||
	    p->requested != 4 || !p->media_owned ||
	    !n->receiver_ref || !n->smi_ref || (!cold && !c->allocated) ||
	    d->resources.sv_id > 1 || layout->sv_id != d->resources.sv_id ||
	    IS_ERR_OR_NULL(d->resources.banks[2]))
		return -EBUSY;
	if (d->pair.tx.hw_attempted && !d->pair.tx.quiesced)
		return -EBUSY; /* Never reset an unretired DMA attempt. */
	if (!device_is_bound(d->consumer) || !device_is_bound(d->dma_owner) ||
	    !device_is_bound(n->smi) || !pm_runtime_active(d->consumer) ||
	    !pm_runtime_active(n->smi) || !pm_runtime_active(p->receiver->dev))
		return -EHOSTDOWN;
	resource = platform_get_resource(to_platform_device(p->cam_main), IORESOURCE_MEM, 0);
	if (!resource || resource_size(resource) < CAM_MAIN_SW_RESET + 4)
		return -ERANGE;
	for (i = 0; i < 8; i++)
		if (!__clk_is_enabled(d->resources.clocks[i].clk))
			return -EHOSTDOWN;
	for (i = 0; i < 4; i++) {
		ret = irq_off(d->resources.irqs[i]);
		if (ret)
			return ret;
	}
	ret = irq_off(c->irq);
	if (!ret)
		ret = irq_off(c->tsrec_irq);
	if (!ret)
		ret = cold ? mt6878_camera_cold_verify(cold, n, layout) :
			mt6878_seninf_controller_gate(c, MT6878_SV_STOPPED, layout);
	return ret;
}

static int joint_run(struct mt6878_camera_joint_reset *transaction,
	struct mt6878_native_capture *n, const struct mt6878_camsv_job *layout,
	struct mt6878_cam_main_lease **supplied, unsigned int port, unsigned int pixel_mode)
{
	struct mt6878_cam_main_lease *lease = NULL;
	struct v4l2_subdev_state *receiver_state, *sensor_state;
	struct regmap *cam_main;
	void __iomem *scq;
	u32 ready;
	int ret, cleanup;
	bool native_locked = supplied != NULL, reset_started = false;

	ret = joint_once(transaction);
	if (ret || !n || !layout)
		return ret ? ret : -EINVAL;
	if (!n->bound || !n->platform.cam_main || !n->platform.receiver ||
	    !n->platform.sensor || !n->platform.receiver->active_state ||
	    !n->platform.sensor->active_state)
		return -ENODEV;
	if (supplied)
		lockdep_assert_held(&n->lock);
	else
		lockdep_assert_not_held(&n->lock);
	lockdep_assert_not_held(&n->reset_lock);
	lockdep_assert_not_held(&n->direct.lock);
	lockdep_assert_not_held(&n->controller.core);
	/* Supplier exclusion precedes every consumer mutex. No borrowed mapping
	 * can survive this synchronous task; native capture PM remains separate.
	 */
	if (supplied) {
		lease = *supplied;
		*supplied = NULL; /* This transaction owns retirement on every exit. */
	} else {
		ret = mt6878_cam_main_prepare(n->platform.cam_main, &lease);
		if (ret)
			return ret;
	}
	cam_main = mt6878_cam_main_regmap(lease);
	if (IS_ERR(cam_main)) {
		ret = PTR_ERR(cam_main);
		goto retire_lease;
	}
	if (!supplied)
		mutex_lock(&n->lock);
	native_locked = true;
	mutex_lock(&n->platform.lifecycle);
	ret = joint_once(transaction);
	if (ret)
		goto unlock_lifecycle;
	if (supplied) {
		ret = mt6878_camera_cold_prepare(&transaction->cold, n, layout, port, pixel_mode);
		reset_started = transaction->cold.attempted;
		if (reset_started) {
			transaction->attempted = true;
			n->reset_attempted = true;
			n->reset_completed = false;
		}
		if (ret)
			goto unlock_lifecycle;
	}
	/* Native receiver stream callbacks take receiver state before sensor
	 * state. Hold both across the pulse, excluding new stream attempts.
	 */
	receiver_state = v4l2_subdev_lock_and_get_active_state(n->platform.receiver);
	sensor_state = v4l2_subdev_lock_and_get_active_state(n->platform.sensor);
	if (v4l2_subdev_is_streaming(n->platform.receiver) ||
	    v4l2_subdev_is_streaming(n->platform.sensor)) {
		ret = -EBUSY;
		goto unlock_states;
	}
	mutex_lock(&n->controller.core);
	mutex_lock(&n->direct.lock);
	ret = joint_preflight(n, layout, supplied ? &transaction->cold : NULL);
	mutex_unlock(&n->direct.lock);
	if (ret)
		goto unlock_core;
	mutex_lock(&n->reset_lock);
	transaction->attempted = true;
	reset_started = true;
	n->reset_attempted = true;
	n->reset_completed = false;
	transaction->clamp_attempted = true;
	ret = mtk_smi_camera_reset_clamp(n->smi, n->direct.consumer, true);
	if (ret)
		goto finish;
	/* Exact e96 sv_reset_by_camsys_top sequence; no guessed reset/ready bits.
	 * Receiver/capture IRQs were drained before the supplied STOPPED proof.
	 * The bounded ready poll never holds the queue mutex or IRQ context.
	 */
	scq = n->direct.resources.banks[2];
	writel(0, scq + SV_CQ_RESET);
	writel(1, scq + SV_CQ_RESET);
	wmb(); /* Commit SCQ request before the vendor bit1 ready poll. */
	ret = readl_poll_timeout(scq + SV_CQ_RESET, ready, ready & BIT(1), 1, 100000);
	if (ret)
		goto finish; /* Keep SMI clamp and native PM/DMA ownership. */
	writel(0, scq + SV_CQ_RESET);
	ret = regmap_write(cam_main, CAM_MAIN_SW_RESET, 0);
	if (!ret)
		ret = regmap_write(cam_main, CAM_MAIN_SW_RESET, 3U << (layout->sv_id * 2));
	if (!ret)
		ret = regmap_write(cam_main, CAM_MAIN_SW_RESET, 0);
	if (ret)
		goto finish;
	wmb(); /* Commit CAM_MAIN pulse before releasing the SMI clamp. */
	ret = mtk_smi_camera_reset_clamp(n->smi, n->direct.consumer, false);
finish:
	if (ret) {
		transaction->first_error = ret;
		if (!n->first_error)
			n->first_error = ret;
	}
	mutex_unlock(&n->reset_lock);
unlock_core:
	mutex_unlock(&n->controller.core);
unlock_states:
	v4l2_subdev_unlock_state(sensor_state);
	v4l2_subdev_unlock_state(receiver_state);
unlock_lifecycle:
	mutex_unlock(&n->platform.lifecycle);
retire_lease:
	/* Only our synchronous mapping user is retired. This does NOT discharge
	 * native capture refs, SMI error/clamp quarantine or DMA on failure.
	 */
	cleanup = mt6878_cam_main_retire(&lease);
	/* Keep native retirement excluded until supplier PM cleanup is known.
	 * An early mapping error has not yet acquired native lock; acquire it
	 * before recording a genuine cleanup error on the persistent owner.
	 */
	if (native_locked || cleanup) {
		if (!native_locked)
			mutex_lock(&n->lock);
		if (reset_started || cleanup)
			ret = joint_finish(transaction, n, ret, cleanup);
		if (!ret && supplied) {
			ret = mt6878_camera_cold_release(&transaction->cold, n);
			if (ret)
				ret = joint_finish(transaction, n, ret, 0);
		}
		if (!supplied)
			mutex_unlock(&n->lock);
	}
	return ret;
}

int mt6878_camera_joint_reset(struct mt6878_camera_joint_reset *transaction,
	struct mt6878_native_capture *n, const struct mt6878_camsv_job *layout)
{
	return joint_run(transaction, n, layout, NULL, 0, 0);
}

int mt6878_camera_cold_frame(struct mt6878_camera_joint_reset *transaction,
	struct mt6878_native_capture *n, struct vb2_v4l2_buffer *raw,
	struct vb2_v4l2_buffer *pdaf, const struct mt6878_camsv_job *layout,
	const struct mtkcam_ipi_config_param *config, unsigned int port,
	unsigned int pixel_mode)
{
	struct mt6878_cam_main_lease *lease = NULL;
	int ret, cleanup;

	if (!n || !n->bound || !transaction || !raw || !pdaf || !layout || !config)
		return -EINVAL;
	ret = joint_once(transaction);
	if (ret)
		return ret;
	ret = mt6878_cam_main_prepare(n->platform.cam_main, &lease);
	if (ret)
		return ret;
	mutex_lock(&n->lock);
	if (n->first_error || n->direct.pair.tx.attempted || n->receiver_ref) {
		ret = n->first_error ? n->first_error : -EALREADY;
		goto retire_unused;
	}
	ret = pm_runtime_resume_and_get(n->smi);
	if (ret < 0)
		goto retire_unused;
	n->smi_ref = true;
	ret = mt6878_camsv_platform_power_get(&n->platform);
	if (ret)
		goto fail;
	ret = pm_runtime_resume_and_get(n->platform.receiver->dev);
	if (ret < 0)
		goto fail;
	n->receiver_ref = true;
	/* Continuous native lock excludes removal/retire through mapping cleanup,
	 * OFF proof, reset and the existing calibrated ON path. No unlocked gap.
	 */
	ret = joint_run(transaction, n, layout, &lease, port, pixel_mode);
	if (ret)
		goto fail;
	ret = mt6878_seninf_controller_prepare(&n->controller, layout, port, pixel_mode);
	if (ret)
		goto fail;
	mutex_lock(&n->direct.lock);
	ret = mt6878_camsv_direct_submit(&n->direct, raw, pdaf, layout, config);
	mutex_unlock(&n->direct.lock);
	if (ret)
		goto fail;
	ret = mt6878_camsv_platform_arm(&n->platform);
	if (ret)
		goto fail;
	mutex_lock(&n->platform.lifecycle);
	ret = atomic_read(&n->platform.stop_requested) ? -ESHUTDOWN :
		v4l2_subdev_enable_streams(n->platform.receiver, 1, 1);
	mutex_unlock(&n->platform.lifecycle);
	if (!ret)
		goto out;
fail:
	if (!n->first_error)
		n->first_error = ret;
	mutex_lock(&n->direct.lock);
	if (!n->direct.first_error)
		n->direct.first_error = ret;
	mutex_unlock(&n->direct.lock);
	mt6878_camsv_platform_stop_async(&n->platform);
retire_unused:
	if (lease) {
		cleanup = mt6878_cam_main_retire(&lease);
		if (cleanup)
			ret = joint_finish(transaction, n, ret, cleanup);
	}
out:
	mutex_unlock(&n->lock);
	return ret;
}

#if IS_ENABLED(CONFIG_KUNIT)
#include "joint-reset-test.inc"
#endif
