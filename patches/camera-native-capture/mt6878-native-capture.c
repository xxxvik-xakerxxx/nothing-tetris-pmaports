// SPDX-License-Identifier: GPL-2.0-only
#include <linux/pm_runtime.h>
#include "mt6878-native-capture.h"

static int remember(struct mt6878_native_capture *n, int ret)
{
	if (ret && !n->first_error)
		n->first_error = ret;
	return ret;
}

static int release_direct(struct mt6878_native_capture *n)
{
	int ret;

	mutex_lock(&n->direct.lock);
	ret = mt6878_camsv_direct_release(&n->direct);
	mutex_unlock(&n->direct.lock);
	return ret;
}

/* Read streaming bookkeeping only under the native active-state mutex. */
static bool streaming(struct v4l2_subdev *sd)
{
	struct v4l2_subdev_state *state = v4l2_subdev_lock_and_get_active_state(sd);
	bool active = v4l2_subdev_is_streaming(sd);

	v4l2_subdev_unlock_state(state);
	return active;
}

static int release_receiver(struct mt6878_native_capture *n)
{
	struct mt6878_seninf_controller *c = &n->controller;
	int ret = 0;

	if (c->allocated)
		return mt6878_seninf_controller_release(c);
	/* Bind without prepare owns only two NO_AUTOEN IRQ registrations. No
	 * PHY/route MMIO or stream is discharged by this resource-only unwind.
	 */
	mutex_lock(&c->core);
	mutex_lock(&n->direct.lock);
	if (c->requested != 2 || c->irq_enabled || c->route.phy.attempted ||
	    c->route.route.attempted || n->direct.pair.tx.hw_attempted)
		ret = -EBUSY;
	else {
		v4l2_set_subdev_hostdata(n->platform.receiver, NULL);
		c->requested = 0;
	}
	mutex_unlock(&n->direct.lock);
	mutex_unlock(&c->core);
	if (!ret) {
		free_irq(c->tsrec_irq, c);
		free_irq(c->irq, c);
	}
	return ret;
}

int mt6878_native_capture_receiver_stop(struct mt6878_camsv_platform *p)
{
	struct mt6878_seninf_controller *c;
	struct mt6878_native_capture *n;
	int ret;

	if (!p || !p->receiver)
		return -EINVAL;
	lockdep_assert_held(&p->lifecycle);
	c = v4l2_get_subdev_hostdata(p->receiver);
	if (!c || c->capture != p)
		return -ENODEV;
	n = p->native_capture;
	if (!n || &n->platform != p || &n->controller != c || !n->bound)
		return -EINVAL;
	if (streaming(p->receiver))
		return v4l2_subdev_disable_streams(p->receiver, 1, 1);
	/* A failed callback never enabled receiver software masks. EALREADY is
	 * not an OFF proof. Abort owns the attempted physical stream exactly once.
	 */
	if (n->abort_attempted)
		return n->abort_error ? n->abort_error : -EALREADY;
	n->abort_attempted = true;
	ret = mt6878_seninf_controller_drain(c);
	if (ret)
		goto out;
	if (streaming(p->sensor))
		ret = v4l2_subdev_disable_streams(p->sensor, c->route.sensor_pad, 1);
	else
		ret = v4l2_subdev_call(p->sensor, core, s_power, 0);
	if (ret)
		goto out;
	mutex_lock(&c->core);
	mutex_lock(&p->direct->lock);
	c->route.source_stopped = true; /* Only after actual sensor cleanup. */
	ret = mt6878_route_disconnect(&c->route.backend.io, &c->route.route);
	mutex_unlock(&p->direct->lock);
	mutex_unlock(&c->core);
out:
	n->abort_error = ret;
	/* Existing direct first_error retains failed ON; cleanup result is separate. */
	return ret;
}

int mt6878_native_capture_probe(struct mt6878_native_capture *n,
	struct platform_device *pdev, struct device *dma_owner, struct device *cam_main,
	struct device *smi, struct v4l2_subdev *receiver, struct v4l2_subdev *sensor,
	unsigned int sensor_pad, void __iomem *cam_main_base, unsigned long cam_main_size)
{
	struct mt6878_camsv_backend backend;
	int ret;

	if (!n || !pdev || !dma_owner || !cam_main || !smi || !receiver || !sensor ||
	    !receiver->dev || !sensor->dev || IS_ERR_OR_NULL(cam_main_base) ||
	    cam_main_size < 0x5c || n->bound)
		return -EINVAL;
	if (!device_is_bound(dma_owner) || !device_is_bound(cam_main) ||
	    !device_is_bound(smi) || !pm_runtime_enabled(receiver->dev) ||
	    !pm_runtime_enabled(cam_main) || !pm_runtime_enabled(&pdev->dev) ||
	    !pm_runtime_enabled(smi))
		return -EPROBE_DEFER;
	mutex_init(&n->lock);
	mutex_init(&n->reset_lock);
	n->hardware = (struct mt6878_camsv_hardware) {
		.platform = &n->platform, .smi_device = smi, .reset_lock = &n->reset_lock,
		.cam_main = cam_main_base, .cam_main_size = cam_main_size,
		.seninf_base = mt6878_seninf_native_base(receiver), .seninf_size = 0x18000,
	};
	ret = mt6878_camsv_native_smi_backend(&n->hardware, &backend);
	if (ret)
		return ret;
	ret = mt6878_camsv_direct_init(&n->direct, pdev, dma_owner, &backend);
	if (ret)
		return ret;
	ret = mt6878_camsv_platform_bind(&n->platform, &n->direct, cam_main,
		sensor, sensor_pad, receiver, 0);
	if (ret)
		goto release_direct;
	ret = mt6878_seninf_native_bind(&n->controller, &n->platform);
	if (ret) {
		int cleanup;

		/* No MMIO, no powered stream: existing retire drains owned work/IRQs. */
		cleanup = mt6878_camsv_platform_retire(&n->platform, msecs_to_jiffies(1000));
		if (cleanup) {
			n->first_error = ret;
			return cleanup; /* Parent MUST retain storage until work is drained. */
		}
		goto release_direct;
	}
	n->smi = get_device(smi);
	n->platform.native_capture = n;
	n->bound = true;
	return 0;
release_direct:
	if (release_direct(n))
		return -EBUSY;
	return ret;
}

int mt6878_native_capture_frame(struct mt6878_native_capture *n,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	const struct mt6878_camsv_job *layout, const struct mtkcam_ipi_config_param *config,
	unsigned int port, unsigned int pixel_mode)
{
	int ret;

	if (!n || !n->bound || !raw || !pdaf || !layout || !config)
		return -EINVAL;
	mutex_lock(&n->lock);
	if (n->first_error || n->direct.pair.tx.attempted || n->receiver_ref) {
		ret = n->first_error ? n->first_error : -EALREADY;
		goto out;
	}
	ret = pm_runtime_resume_and_get(n->smi);
	if (ret < 0)
		goto out;
	n->smi_ref = true;
	ret = mt6878_camsv_platform_power_get(&n->platform);
	if (ret)
		goto fail;
	ret = pm_runtime_resume_and_get(n->platform.receiver->dev);
	if (ret < 0)
		goto fail;
	n->receiver_ref = true;
	mutex_lock(&n->reset_lock);
	n->reset_attempted = true;
	ret = mt6878_camsv_native_cam_main_reset(&n->hardware);
	if (!ret)
		n->reset_completed = true;
	mutex_unlock(&n->reset_lock);
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
	/* IRQ stop work may have won the race after arm. Serialize the actual
	 * stream attempt with its lifecycle; worker never acquires n->lock.
	 */
	mutex_lock(&n->platform.lifecycle);
	ret = atomic_read(&n->platform.stop_requested) ? -ESHUTDOWN :
		v4l2_subdev_enable_streams(n->platform.receiver, 1, 1);
	mutex_unlock(&n->platform.lifecycle);
	if (!ret)
		goto out;
fail:
	remember(n, ret);
	mutex_lock(&n->direct.lock);
	if (!n->direct.first_error)
		n->direct.first_error = ret;
	mutex_unlock(&n->direct.lock);
	mt6878_camsv_platform_stop_async(&n->platform);
out:
	mutex_unlock(&n->lock);
	return ret;
}

int mt6878_native_capture_retire(struct mt6878_native_capture *n, unsigned long timeout)
{
	int ret;

	if (!n || !n->bound || !timeout)
		return -EINVAL;
	mutex_lock(&n->lock);
	if (n->reset_attempted && !n->reset_completed) {
		ret = -EBUSY; /* Source reset timeout retains clamp/provider lease. */
		goto out;
	}
	mt6878_camsv_platform_stop_async(&n->platform);
	if (!wait_for_completion_timeout(&n->platform.stopped, timeout)) {
		ret = -ETIMEDOUT;
		goto out;
	}
	flush_work(&n->platform.stop_work);
	mutex_lock(&n->direct.lock);
	ret = n->direct.pair.tx.hw_attempted && !n->direct.pair.tx.quiesced ? -EBUSY : 0;
	mutex_unlock(&n->direct.lock);
	if (ret)
		goto out;
	/* Submit can fail before CAMSV MMIO, after PHY/route preparation. Worker
	 * then had no DMA attempt to stop, but receiver still owns real resources.
	 */
	if (n->controller.allocated && !n->controller.route.route.disconnected) {
		mutex_lock(&n->platform.lifecycle);
		ret = mt6878_native_capture_receiver_stop(&n->platform);
		mutex_unlock(&n->platform.lifecycle);
		if (ret)
			goto out;
	}
	ret = release_receiver(n);
	if (ret)
		goto out;
	if (n->receiver_ref) {
		ret = pm_runtime_put_sync_suspend(n->platform.receiver->dev);
		if (ret < 0) {
			pm_runtime_get_noresume(n->platform.receiver->dev);
			goto out;
		}
		n->receiver_ref = false;
	}
	ret = mt6878_camsv_platform_retire(&n->platform, timeout);
	if (ret && !n->platform.retired)
		goto out;
	/* Platform can return the original failed ON after proven retirement.
	 * Keep that failure separately, without leaking already-quiesced resources.
	 */
	remember(n, ret);
	if (n->smi_ref) {
		ret = pm_runtime_put_sync_suspend(n->smi);
		if (ret < 0) {
			pm_runtime_get_noresume(n->smi);
			goto out;
		}
		n->smi_ref = false;
	}
	ret = release_direct(n);
	if (!ret) {
		put_device(n->smi);
		n->platform.native_capture = NULL;
		n->bound = false;
	}
out:
	mutex_unlock(&n->lock);
	return ret;
}
