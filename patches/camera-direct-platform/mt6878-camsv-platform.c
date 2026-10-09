// SPDX-License-Identifier: GPL-2.0-only
#include <linux/io.h>
#include <linux/module.h>
#include <linux/pm_runtime.h>
#include <media/media-device.h>
#include "mt6878-camsv-platform.h"
#include "mt6878-camera-irq-registers.h"

/* e96f60dc, mtkcam/camsys/isp7sp/cam/mtk_cam-sv-regs.h. */
#define SV_ERR_STATUS 0x0350
#define SV_SOF_STATUS 0x0360
#define SV_CHANNEL_STATUS 0x0370
#define SV_CQ_STATUS 0x001c
#define SV_LAST_TAG 0x01c8
#define SV_GROUP_TAG0 0x01b8
#define SV_GROUP_TAG_SHIFT 0x4
#define SV_VF_ST_TAG1 0x0550
#define SV_VF_ST_TAG_SHIFT 0x40

static void latch_error(struct mt6878_camsv_direct *direct, int error)
{
	if (error && !direct->first_error)
		direct->first_error = error;
}

static irqreturn_t platform_irq(int irq, void *data)
{
	struct mt6878_camsv_platform_irq *line = data;
	struct mt6878_camsv_platform *p = line->platform;
	struct mt6878_camsv_direct *d = p->direct;
	unsigned int first, offset = CAMERA_FH_SPARE_TAG1, i;
	int ret;
	bool stop = false;

	mutex_lock(&d->lock);
	if (d->first_error || d->completion_observed) {
		stop = true;
		goto out;
	}
	if (!line->index) {
		ret = mt6878_camsv_direct_done(d);
		stop = ret == 1 || (ret < 0 && ret != -ESTALE && ret != -EALREADY);
		if (stop && ret < 0)
			latch_error(d, ret);
		goto out;
	}
	ret = d->hardware.verify(d->hardware.context, MT6878_SV_RESOURCES, &d->job);
	if (!ret)
		ret = d->hardware.verify(d->hardware.context, MT6878_SV_IRQ, &d->job);
	if (ret) {
		latch_error(d, ret);
		stop = true;
		goto out;
	}
	/* All four vendor handlers read FIRST_TAG and outer/inner FH_SPARE before
	 * their status. No W1C or read-clear assumption is added here.
	 */
	first = readl_relaxed(d->resources.banks[3] + CAMERA_FIRST_TAG);
	if (line->index == 2)
		p->last_tag = readl_relaxed(d->resources.banks[3] + SV_LAST_TAG);
	for (i = 0; i < 8; i++)
		if (first & BIT(i)) {
			offset += CAMERA_FH_SPARE_SHIFT * i;
			break;
		}
	readl_relaxed(d->resources.banks[0] + offset);
	readl_relaxed(d->resources.banks[3] + offset);
	switch (line->index) {
	case 1:
		p->status[1] = readl_relaxed(d->resources.banks[3] + SV_ERR_STATUS);
		if (p->status[1]) {
			latch_error(d, -EIO);
			stop = true;
		}
		break;
	case 2:
		p->status[2] = readl_relaxed(d->resources.banks[0] + SV_SOF_STATUS);
		p->channel_status = readl_relaxed(d->resources.banks[0] + SV_CHANNEL_STATUS);
		for (i = 0; i < 4; i++)
			p->group_tags[i] = readl_relaxed(d->resources.banks[3] +
				SV_GROUP_TAG0 + SV_GROUP_TAG_SHIFT * i);
		p->tg_count = readl_relaxed(d->resources.banks[0] +
			SV_VF_ST_TAG1 + SV_VF_ST_TAG_SHIFT * 3);
		for (i = 0; i < 4; i++)
			if (p->group_tags[i] != d->job.group_tags[i]) {
				latch_error(d, -ESTALE);
				stop = true;
			}
		break;
	case 3:
		p->status[3] = readl_relaxed(d->resources.banks[2] + SV_CQ_STATUS);
		break;
	}
out:
	mutex_unlock(&d->lock);
	if (stop)
		mt6878_camsv_platform_stop_async(p);
	return IRQ_HANDLED;
}

static void platform_stop_work(struct work_struct *work)
{
	struct mt6878_camsv_platform *p = container_of(work, struct mt6878_camsv_platform, stop_work);
	struct mt6878_camsv_direct *d = p->direct;
	int ret, first = 0;
	unsigned int i;
	bool attempted;

	/* Never hold the queue mutex while disable_irq waits for threaded handlers.
	 * Power and DMA mappings remain held even if route stop/reset fails.
	 */
	mutex_lock(&p->lifecycle);
	for (i = 0; i < p->enabled; i++)
		disable_irq(d->resources.irqs[i]);
	p->enabled = 0;
	p->drained = true;
	mutex_lock(&d->lock);
	attempted = d->pair.tx.hw_attempted;
	mutex_unlock(&d->lock);
	if (p->powered && attempted) {
		ret = v4l2_subdev_call(p->sensor, video, s_stream, 0);
		if (ret)
			first = ret;
		ret = v4l2_subdev_call(p->receiver, video, s_stream, 0);
		if (ret && !first)
			first = ret;
	}
	mutex_lock(&d->lock);
	latch_error(d, first);
	/* No caller-written quiesced flag. Direct stop verifies the real route,
	 * IRQ drain, TG/VF and then performs its bounded reset transaction.
	 */
	ret = first ? first : mt6878_camsv_direct_stop(d);
	p->stop_error = ret;
	mutex_unlock(&d->lock);
	mutex_unlock(&p->lifecycle);
	complete_all(&p->stopped);
}

int mt6878_camsv_platform_bind(struct mt6878_camsv_platform *p,
	struct mt6878_camsv_direct *d, struct device *cam_main,
	struct v4l2_subdev *sensor, unsigned int source_pad,
	struct v4l2_subdev *receiver, unsigned int sink_pad)
{
	struct media_device *mdev;
	struct media_link *link;
	unsigned int i;
	int ret;

	if (!p || p->direct || !d || !d->cq_cpu || !cam_main || !sensor || !receiver ||
	    !sensor->dev || !receiver->dev || source_pad >= sensor->entity.num_pads ||
	    sink_pad >= receiver->entity.num_pads ||
	    !(sensor->entity.pads[source_pad].flags & MEDIA_PAD_FL_SOURCE) ||
	    !(receiver->entity.pads[sink_pad].flags & MEDIA_PAD_FL_SINK))
		return -EINVAL;
	mdev = sensor->entity.graph_obj.mdev;
	if (!mdev || receiver->entity.graph_obj.mdev != mdev)
		return -ENOLINK;
	mutex_lock(&mdev->graph_mutex);
	link = media_entity_find_link(&sensor->entity.pads[source_pad], &receiver->entity.pads[sink_pad]);
	ret = link && (link->flags & MEDIA_LNK_FL_ENABLED) ? 0 : -ENOLINK;
	mutex_unlock(&mdev->graph_mutex);
	if (ret)
		return ret;
	if (!try_module_get(sensor->owner))
		return -ENODEV;
	if (!try_module_get(receiver->owner)) {
		module_put(sensor->owner);
		return -ENODEV;
	}
	p->direct = d;
	p->cam_main = get_device(cam_main);
	p->sensor = sensor;
	p->receiver = receiver;
	get_device(sensor->dev);
	get_device(receiver->dev);
	INIT_WORK(&p->stop_work, platform_stop_work);
	init_completion(&p->stopped);
	mutex_init(&p->lifecycle);
	atomic_set(&p->stop_requested, 0);
	p->origin = &sensor->entity.pads[source_pad];
	mutex_lock(&mdev->graph_mutex);
	link = media_entity_find_link(p->origin, &receiver->entity.pads[sink_pad]);
	if (!link || !(link->flags & MEDIA_LNK_FL_ENABLED))
		ret = -ENOLINK;
	else if (media_pad_pipeline(p->origin))
		ret = -EBUSY;
	else
		ret = __media_pipeline_start(p->origin, &p->pipeline);
	mutex_unlock(&mdev->graph_mutex);
	if (ret)
		goto unwind;
	p->media_owned = true;
	for (i = 0; i < 4; i++) {
		p->lines[i].platform = p;
		p->lines[i].index = i;
		ret = request_threaded_irq(d->resources.irqs[i], NULL, platform_irq,
			IRQF_ONESHOT | IRQF_NO_AUTOEN, dev_name(d->consumer), &p->lines[i]);
		if (ret)
			goto unwind;
		p->requested++;
	}
	return 0;
unwind:
	while (p->requested) {
		p->requested--;
		free_irq(d->resources.irqs[p->requested], &p->lines[p->requested]);
	}
	if (p->media_owned) {
		media_pipeline_stop(p->origin);
		p->media_owned = false;
	}
	put_device(receiver->dev);
	put_device(sensor->dev);
	put_device(p->cam_main);
	module_put(receiver->owner);
	module_put(sensor->owner);
	p->direct = NULL;
	return ret;
}

int mt6878_camsv_platform_power_get(struct mt6878_camsv_platform *p)
{
	struct device *dev;
	int ret;

	if (!p || !p->direct)
		return -EINVAL;
	mutex_lock(&p->lifecycle);
	if (p->retired || p->powered || atomic_read(&p->stop_requested)) {
		ret = -ESHUTDOWN;
		goto out;
	}
	dev = p->direct->consumer;
	/* CAM_MAIN provider must already implement its actual PM/reset ownership.
	 * A disabled runtime-PM provider is not interpreted as powered hardware.
	 */
	if (!pm_runtime_enabled(p->cam_main) || !pm_runtime_enabled(dev)) {
		ret = -EOPNOTSUPP;
		goto out;
	}
	ret = pm_runtime_resume_and_get(p->cam_main);
	if (ret < 0)
		goto out;
	if (dev != p->cam_main) {
		ret = pm_runtime_resume_and_get(dev);
		if (ret < 0) {
			pm_runtime_put_sync(p->cam_main);
			goto out;
		}
	}
	ret = clk_bulk_prepare_enable(8, p->direct->resources.clocks);
	if (ret) {
		if (dev != p->cam_main)
			pm_runtime_put_sync(dev);
		pm_runtime_put_sync(p->cam_main);
		goto out;
	}
	p->powered = true;
	ret = 0;
out:
	mutex_unlock(&p->lifecycle);
	return ret;
}

int mt6878_camsv_platform_arm(struct mt6878_camsv_platform *p)
{
	struct mt6878_camsv_direct *d;
	unsigned int i;
	int ret;

	if (!p || !p->direct)
		return -EINVAL;
	d = p->direct;
	mutex_lock(&p->lifecycle);
	if (!p->powered || p->enabled || p->drained || p->requested != 4 ||
	    atomic_read(&p->stop_requested)) {
		mutex_unlock(&p->lifecycle);
		return -ESHUTDOWN;
	}
	mutex_lock(&d->lock);
	ret = d->hardware.verify(d->hardware.context, MT6878_SV_RESOURCES, &d->job);
	if (!ret)
		ret = d->hardware.verify(d->hardware.context, MT6878_SV_ROUTE, &d->job);
	if (!ret)
		ret = d->hardware.verify(d->hardware.context, MT6878_SV_IRQ, &d->job);
	mutex_unlock(&d->lock);
	if (ret) {
		mutex_unlock(&p->lifecycle);
		return ret;
	}
	for (i = 0; i < 4; i++) {
		p->enabled++;
		enable_irq(d->resources.irqs[i]);
	}
	mutex_unlock(&p->lifecycle);
	return 0;
}

void mt6878_camsv_platform_stop_async(struct mt6878_camsv_platform *p)
{
	if (atomic_cmpxchg(&p->stop_requested, 0, 1) == 0)
		schedule_work(&p->stop_work);
}

int mt6878_camsv_platform_retire(struct mt6878_camsv_platform *p, unsigned long timeout)
{
	struct mt6878_camsv_direct *d;
	unsigned int i;
	int ret;

	if (!p || !p->direct || !timeout || p->retired)
		return -EINVAL;
	d = p->direct;
	lockdep_assert_not_held(&d->lock);
	mt6878_camsv_platform_stop_async(p);
	if (!wait_for_completion_timeout(&p->stopped, timeout))
		return -ETIMEDOUT;
	/* Completion wakes before work returns. Drain work too before freeing its
	 * storage; controller serialization forbids any new stop/arm requests.
	 */
	flush_work(&p->stop_work);
	mutex_lock(&d->lock);
	ret = d->pair.tx.hw_attempted && !d->pair.tx.quiesced ? -EBUSY : 0;
	mutex_unlock(&d->lock);
	if (ret)
		return ret;
	for (i = 0; i < p->requested; i++)
		free_irq(d->resources.irqs[i], &p->lines[i]);
	p->requested = 0;
	if (p->powered) {
		clk_bulk_disable_unprepare(8, d->resources.clocks);
		if (d->consumer != p->cam_main) {
			ret = pm_runtime_put_sync(d->consumer);
			if (ret < 0 && !p->stop_error)
				p->stop_error = ret;
		}
		ret = pm_runtime_put_sync(p->cam_main);
		if (ret < 0 && !p->stop_error)
			p->stop_error = ret;
		p->powered = false;
	}
	if (p->media_owned) {
		media_pipeline_stop(p->origin);
		p->media_owned = false;
	}
	put_device(p->receiver->dev);
	put_device(p->sensor->dev);
	put_device(p->cam_main);
	module_put(p->receiver->owner);
	module_put(p->sensor->owner);
	p->retired = true;
	return p->stop_error;
}
