// SPDX-License-Identifier: GPL-2.0-only
#include <linux/err.h>
#include <linux/irq.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/string.h>
#include "mt6878-capture-epoch.h"

static int epoch_error(struct mt6878_capture_epoch *e, int ret)
{
	if (ret && !e->first_error)
		e->first_error = ret;
	return e->first_error;
}

static int epoch_irq_off(int irq)
{
	struct irq_data *data = irq_get_irq_data(irq);

	return data && irq_has_action(irq) && irqd_irq_disabled(data) ? 0 : -EBUSY;
}

static int epoch_done(const struct mt6878_camsv_direct *d)
{
	unsigned int tags;

	if (d->first_error || d->pair.tx.first_error)
		return d->first_error ? d->first_error : d->pair.tx.first_error;
	if (d->job.raw_tag > 7 || d->job.pdaf_tag > 7)
		return -EINVAL;
	tags = BIT(d->job.raw_tag) | BIT(d->job.pdaf_tag);
	/* stop clears submitted only after its real reset/unclamp succeeds. */
	return d->completion_observed && d->pair.completed && d->pair.tx.hw_attempted &&
		d->pair.tx.off_attempted && d->pair.tx.quiesced && !d->pair.tx.submitted &&
		d->pair.tx.complete_tags == tags && !d->pair.raw && !d->pair.pdaf ? 0 : -EBUSY;
}

static int epoch_warm_submit(struct mt6878_capture_epoch *e,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf)
{
	struct mt6878_native_capture *n = e->capture;
	int ret;

	mutex_lock(&n->lock);
	if (!n->bound || n->epoch != e || n->platform.retired || n->first_error ||
	    !n->receiver_ref || !n->smi_ref || !n->platform.powered || !n->reset_completed) {
		ret = n->first_error ? n->first_error : -ENODEV;
		goto out;
	}
	ret = mt6878_seninf_controller_prepare(&n->controller, &e->layout, e->port, e->pixel_mode);
	if (!ret) {
		mutex_lock(&n->direct.lock);
		ret = mt6878_camsv_direct_submit(&n->direct, raw, pdaf, &e->layout, &e->config);
		mutex_unlock(&n->direct.lock);
	}
	if (!ret)
		ret = mt6878_camsv_platform_arm(&n->platform);
	if (!ret) {
		mutex_lock(&n->platform.lifecycle);
		ret = atomic_read(&n->platform.stop_requested) ? -ESHUTDOWN :
			v4l2_subdev_enable_streams(n->platform.receiver, 1, 1);
		mutex_unlock(&n->platform.lifecycle);
	}
	if (ret) {
		if (!n->first_error)
			n->first_error = ret;
		mutex_lock(&n->direct.lock);
		if (!n->direct.first_error)
			n->direct.first_error = ret;
		mutex_unlock(&n->direct.lock);
		mt6878_camsv_platform_stop_async(&n->platform);
	}
out:
	mutex_unlock(&n->lock);
	return ret;
}

struct mt6878_capture_epoch *mt6878_capture_epoch_alloc(struct mt6878_native_capture *n)
{
	struct mt6878_capture_epoch *e;
	int ret;

	if (!n || !n->bound)
		return ERR_PTR(-ENODEV);
	lockdep_assert_not_held(&n->direct.lock);
	e = kzalloc(sizeof(*e), GFP_KERNEL);
	if (!e)
		return ERR_PTR(-ENOMEM);
	mutex_init(&e->lock);
	e->capture = n;
	mutex_lock(&n->lock);
	mutex_lock(&n->direct.lock);
	ret = n->first_error ? n->first_error : 0;
	if (!ret && (n->epoch || n->reset_attempted || n->receiver_ref || n->smi_ref ||
	    n->direct.first_error || n->direct.pair.tx.attempted ||
	    n->direct.encoder.finished || !n->direct.cq_cpu || n->platform.retired ||
	    atomic_read(&n->platform.stop_requested)))
		ret = -EBUSY;
	if (!ret)
		n->epoch = e;
	mutex_unlock(&n->direct.lock);
	mutex_unlock(&n->lock);
	if (ret) {
		kfree(e);
		return ERR_PTR(ret);
	}
	return e;
}

int mt6878_capture_epoch_submit(struct mt6878_capture_epoch *e,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	const struct mt6878_camsv_job *layout, const struct mtkcam_ipi_config_param *config,
	unsigned int port, unsigned int pixel_mode)
{
	int ret;

	if (!e || !raw || !pdaf || !layout || !config)
		return -EINVAL;
	lockdep_assert_not_held(&e->capture->direct.lock);
	mutex_lock(&e->lock);
	if (e->first_error || e->entered || e->retirement_attempted) {
		ret = e->first_error ? e->first_error : -EALREADY;
		goto out;
	}
	e->entered = true;
	if (e->warm && (memcmp(layout, &e->layout, sizeof(*layout)) || port != e->port ||
	    pixel_mode != e->pixel_mode ||
	    memcmp(config, &e->config, sizeof(*config)))) {
		ret = -ESTALE;
		goto fail;
	}
	if (!e->warm) {
		e->layout = *layout;
		e->config = *config;
		e->port = port;
		e->pixel_mode = pixel_mode;
	}
	ret = e->warm ? epoch_warm_submit(e, raw, pdaf) :
		mt6878_camera_cold_frame(&e->reset, e->capture, raw, pdaf,
			layout, config, port, pixel_mode);
fail:
	epoch_error(e, ret);
out:
	mutex_unlock(&e->lock);
	return ret;
}

int mt6878_capture_epoch_retire(struct mt6878_capture_epoch *e, unsigned long timeout)
{
	struct mt6878_native_capture *n;
	struct mt6878_camsv_direct *d;
	struct mt6878_seninf_controller *c;
	unsigned int i;
	int ret;

	if (!e || !timeout)
		return -EINVAL;
	n = e->capture;
	d = &n->direct;
	c = &n->controller;
	lockdep_assert_not_held(&d->lock);
	mutex_lock(&e->lock);
	if (e->retirement_attempted) {
		ret = e->first_error ? e->first_error : -EALREADY;
		goto out;
	}
	e->retirement_attempted = true;
	/* IRQ DONE/error schedules native stop; do not truncate an in-flight
	 * frame by requesting stop before its completion. Completion precedes
	 * work return, so successful waiting still requires the work drain below.
	 */
	if (!wait_for_completion_timeout(&n->platform.stopped, timeout)) {
		ret = -ETIMEDOUT;
		/* Preserve an already-latched causal IRQ failure. Latch timeout in
		 * the persistent owners BEFORE abort, so late DONE cannot yield a
		 * healthy frame/rearm. Native full cleanup alone may retire the refs.
		 */
		mutex_lock(&n->lock);
		mutex_lock(&d->lock);
		epoch_error(e, n->first_error);
		epoch_error(e, d->first_error);
		epoch_error(e, ret);
		if (!n->first_error)
			n->first_error = e->first_error;
		if (!d->first_error)
			d->first_error = e->first_error;
		mutex_unlock(&d->lock);
		mutex_unlock(&n->lock);
		mt6878_camsv_platform_stop_async(&n->platform);
		goto fail;
	}
	flush_work(&n->platform.stop_work);
	mutex_lock(&n->lock);
	mutex_lock(&d->lock);
	e->dma_receipt = d->pair.tx;
	e->timestamp = d->completion_timestamp;
	ret = epoch_done(d);
	e->frame_done = e->entered && !ret;
	epoch_error(e, n->first_error);
	epoch_error(e, d->first_error);
	epoch_error(e, n->platform.stop_error);
	epoch_error(e, ret);
	mutex_unlock(&d->lock);
	mutex_unlock(&n->lock);
	if (e->first_error) {
		ret = e->first_error;
		goto fail;
	}
	/* Fresh reset transaction records the actual source-backed CAM_MAIN pulse
	 * while the disconnected controller still owns its STOPPED reservations.
	 */
	ret = mt6878_camera_joint_reset(&e->retirement_reset, n, &e->dma_receipt.job);
	if (ret)
		goto fail;
	mutex_lock(&n->lock);
	mutex_lock(&n->platform.lifecycle);
	ret = !n->bound || n->epoch != e || n->platform.retired || n->first_error ||
		!n->platform.drained || n->platform.enabled || c->irq_enabled ||
		!c->irq_drained || c->requested != 2 || n->platform.requested != 4 ? -EBUSY : 0;
	for (i = 0; !ret && i < 4; i++)
		ret = epoch_irq_off(d->resources.irqs[i]);
	if (!ret)
		ret = epoch_irq_off(c->irq);
	if (!ret)
		ret = epoch_irq_off(c->tsrec_irq);
	if (ret)
		goto unlock_lifecycle;
	/* Hardware IRQs stay disabled; drains occur outside core/queue/state. */
	for (i = 0; i < 4; i++)
		synchronize_irq(d->resources.irqs[i]);
	synchronize_irq(c->irq);
	synchronize_irq(c->tsrec_irq);
	mutex_lock(&c->core);
	mutex_lock(&d->lock);
	ret = epoch_done(d);
	if (!ret)
		ret = mt6878_seninf_route_retire(&c->route, d);
	if (!ret && (!c->allocated || c->route.phy.configured || !c->route.phy.off_attempted ||
	    c->route.first_error || c->first_error))
		ret = -EBUSY;
	if (!ret) {
		e->route_receipt = c->route;
		e->tsrec_receipt = c->tsrec;
		e->events_receipt = c->events;
		/* Single native controller owns exactly this pair's reservations. */
		for (i = 0; i < 2; i++) {
			clear_bit(c->allocation.outputs[i].intf, &c->intfs);
			clear_bit(c->allocation.outputs[i].mux, &c->muxes);
			clear_bit(c->allocation.cammux[i], &c->cammuxes);
		}
		c->allocated = false;
		e->cq_bytes = d->cq_capacity;
		dma_free_coherent(d->dma_owner, d->cq_capacity, d->cq_cpu, d->cq_dma);
		d->cq_cpu = NULL;
		e->retired = true;
	}
	mutex_unlock(&d->lock);
	mutex_unlock(&c->core);
unlock_lifecycle:
	mutex_unlock(&n->platform.lifecycle);
	mutex_unlock(&n->lock);
	if (ret)
		goto fail;
	ret = e->first_error;
	goto out;
fail:
	e->retirement_error = ret;
	ret = epoch_error(e, ret);
	mutex_lock(&n->lock);
	if (!n->first_error)
		n->first_error = ret;
	mutex_unlock(&n->lock);
out:
	mutex_unlock(&e->lock);
	return ret;
}

struct mt6878_capture_epoch *mt6878_capture_epoch_next(struct mt6878_capture_epoch *old)
{
	struct mt6878_capture_epoch *next;
	struct mt6878_native_capture *n;
	struct mt6878_seninf_controller *c;
	struct mt6878_camsv_direct *d;
	struct mt6878_seninf_route fresh;
	struct mt6878_camsv_buffer allocation;
	void *cpu;
	dma_addr_t dma;
	unsigned int i;
	int ret;

	if (!old)
		return ERR_PTR(-EINVAL);
	n = old->capture;
	c = &n->controller;
	d = &n->direct;
	lockdep_assert_not_held(&d->lock);
	next = kzalloc(sizeof(*next), GFP_KERNEL);
	if (!next)
		return ERR_PTR(-ENOMEM);
	mutex_init(&next->lock);
	mutex_lock(&old->lock);
	/* Reusing an old receipt is an admission error, not a hardware failure on
	 * an already-running successor. Do not poison that successor's owner.
	 */
	if (old->detached || !old->retired || old->first_error) {
		ret = old->first_error ? old->first_error : -EALREADY;
		mutex_unlock(&old->lock);
		kfree(next);
		return ERR_PTR(ret);
	}
	mutex_lock(&n->lock);
	mutex_lock(&n->platform.lifecycle);
	mutex_lock(&c->core);
	mutex_lock(&d->lock);
	ret = old->first_error ? old->first_error : n->first_error;
	if (!ret && (!old->retired || !old->frame_done || old->detached || n->epoch != old ||
	    !old->retirement_reset.completed || !n->bound || n->platform.retired ||
	    !n->platform.media_owned || !n->platform.powered || !n->receiver_ref || !n->smi_ref ||
	    n->platform.stop_error || d->first_error || c->first_error || c->route.first_error ||
	    c->allocated || c->intfs || c->muxes || c->cammuxes || c->route.phy.configured ||
	    c->route.phy.bus.first_error || c->route.route.bus.first_error ||
	    !c->route.phy.off_attempted || !c->route.route.disconnected || d->cq_cpu ||
	    n->platform.enabled || c->irq_enabled || c->requested != 2 ||
	    n->platform.requested != 4 || !completion_done(&n->platform.stopped) ||
	    atomic_read(&n->platform.stop_requested) != 1 || old->layout.sequence == U32_MAX))
		ret = -EBUSY;
	for (i = 0; !ret && i < 4; i++)
		ret = epoch_irq_off(d->resources.irqs[i]);
	if (!ret)
		ret = epoch_irq_off(c->irq);
	if (!ret)
		ret = epoch_irq_off(c->tsrec_irq);
	if (!ret && iommu_get_domain_for_dev(d->dma_owner) != d->resources.domain)
		ret = -ESTALE;
	if (ret)
		goto out;
	cpu = dma_alloc_coherent(d->dma_owner, old->cq_bytes, &dma, GFP_KERNEL);
	if (!cpu) {
		ret = -ENOMEM;
		goto out;
	}
	allocation = (struct mt6878_camsv_buffer) { dma, old->cq_bytes, 1 };
	ret = mt6878_camsv_range(&allocation, old->cq_bytes);
	if (ret || (dma & 15)) {
		dma_free_coherent(d->dma_owner, old->cq_bytes, cpu, dma);
		ret = -ERANGE;
		goto out;
	}
	/* New transaction objects, after the old immutable receipt was saved.
	 * Never reinitialize direct.lock, devres, IRQ registrations or suppliers.
	 */
	fresh = (struct mt6878_seninf_route) {
		.core_lock = c->route.core_lock, .sensor = c->route.sensor,
		.receiver = c->route.receiver, .sensor_pad = c->route.sensor_pad,
		.csi_clock = c->route.csi_clock, .endpoint = c->route.endpoint,
		.backend = c->route.backend,
	};
	c->route = fresh;
	c->tsrec = (struct mt6878_seninf_transaction) { 0 };
	c->events = (struct mt6878_seninf_transaction) { 0 };
	c->observed = (struct mt6878_seninf_events) { 0 };
	c->allocation = (struct mt6878_route_plan) { 0 };
	c->tsrec_disabled = false;
	c->irq_drained = false;
	d->pair = (struct mt6878_camsv_vb2_pair) { 0 };
	d->encoder = (struct mt6878_ccd_cq) { 0 };
	d->completion_observed = false;
	d->completion_timestamp = 0;
	d->cq_cpu = cpu;
	d->cq_dma = dma;
	d->cq_capacity = old->cq_bytes;
	next->capture = n;
	next->warm = true;
	next->layout = old->layout;
	next->layout.sequence++;
	next->config = old->config;
	next->port = old->port;
	next->pixel_mode = old->pixel_mode;
	/* No IRQ is enabled and old stop work has been flushed. Only the control
	 * producer may now publish a new submission; stale DONE uses new sequence.
	 */
	reinit_completion(&n->platform.stopped);
	n->platform.drained = false;
	atomic_set(&n->platform.stop_requested, 0);
	n->epoch = next;
	old->detached = true;
out:
	if (ret && !n->first_error)
		n->first_error = ret;
	mutex_unlock(&d->lock);
	mutex_unlock(&c->core);
	mutex_unlock(&n->platform.lifecycle);
	mutex_unlock(&n->lock);
	mutex_unlock(&old->lock);
	if (ret) {
		kfree(next);
		return ERR_PTR(ret);
	}
	return next;
}

int mt6878_capture_epoch_free(struct mt6878_capture_epoch *e)
{
	struct mt6878_native_capture *n;

	if (!e)
		return -EINVAL;
	if (!e->capture)
		return -EBUSY;
	/* Parent has drained its frame worker and excluded all epoch callers.
	 * Failed native retirement retains record/storage, just like DMA owner.
	 */
	n = e->capture;
	mutex_lock(&n->lock);
	if (e->retired && e->detached) {
		mutex_unlock(&n->lock);
		kfree(e);
		return 0;
	}
	/* Final streamoff uses native full retirement, not the per-frame API. */
	if (n->bound || n->receiver_ref || n->smi_ref || n->direct.cq_cpu ||
	    n->platform.requested || n->controller.requested || !n->platform.retired) {
		mutex_unlock(&n->lock);
		return -EBUSY;
	}
	if (n->epoch != e) {
		mutex_unlock(&n->lock);
		return -ESTALE;
	}
	n->epoch = NULL;
	mutex_unlock(&n->lock);
	kfree(e);
	return 0;
}

#if IS_ENABLED(CONFIG_KUNIT)
#include "epoch-test.inc"
#endif
