// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/media-bus-format.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <media/media-device.h>
#include <media/v4l2-async.h>
#include <media/v4l2-fh.h>
#include <media/v4l2-device.h>
#include <media/v4l2-ioctl.h>
#include "mt6878-native-video.h"

struct native_node {
	struct video_device vdev;
	struct media_pad pad;
	struct vb2_queue queue;
	struct mt6878_native_video *owner;
	struct vb2_v4l2_buffer *pending;
	struct completion released;
	unsigned int index;
	bool registered, initialized, streaming, release_expected;
};

struct mt6878_native_video {
	struct mt6878_native_video_suppliers suppliers;
	struct mt6878_native_capture capture;
	struct media_device media;
	struct v4l2_device v4l2;
	struct v4l2_async_notifier notifier;
	struct v4l2_subdev *receiver;
	struct native_node nodes[2];
	struct mutex registration;
	struct module *supplier_modules[4];
	struct work_struct frame_work;
	struct completion registration_done;
	unsigned int opens;
	bool ready, used, stopping, retired, quarantined, removing;
	int first_error, registration_error;
};

static struct native_node *file_node(struct file *file)
{
	return container_of(video_devdata(file), struct native_node, vdev);
}

static struct native_node *queue_node(struct vb2_queue *q)
{
	return container_of(q, struct native_node, queue);
}

static const struct mt6878_camsv_dma_layout *node_layout(struct native_node *node)
{
	return node->index ? &node->owner->suppliers.layout.pdaf_layout :
		&node->owner->suppliers.layout.raw_layout;
}

static int queue_setup(struct vb2_queue *q, unsigned int *count,
	unsigned int *planes, unsigned int sizes[], struct device *alloc_devs[])
{
	const struct mt6878_camsv_dma_layout *layout = node_layout(queue_node(q));

	if (*planes)
		return *planes == 1 && sizes[0] >= layout->sizeimage ? 0 : -EINVAL;
	*count = 1;
	*planes = 1;
	sizes[0] = layout->sizeimage;
	return 0;
}

static int buffer_prepare(struct vb2_buffer *vb)
{
	struct native_node *node = queue_node(vb->vb2_queue);

	if (node->owner->stopping || node->owner->used || vb->num_planes != 1 ||
	    vb->planes[0].data_offset ||
	    vb2_plane_size(vb, 0) < node_layout(node)->sizeimage)
		return -EINVAL;
	vb2_set_plane_payload(vb, 0, 0);
	return 0;
}

static void maybe_frame(struct mt6878_native_video *v)
{
	lockdep_assert_held(&v->capture.direct.lock);
	if (!v->stopping && !v->used && v->nodes[0].streaming &&
	    v->nodes[1].streaming && v->nodes[0].pending && v->nodes[1].pending) {
		v->used = true;
		schedule_work(&v->frame_work);
	}
}

static void buffer_queue(struct vb2_buffer *vb)
{
	struct native_node *node = queue_node(vb->vb2_queue);

	node->pending = to_vb2_v4l2_buffer(vb);
	maybe_frame(node->owner);
}

static int start_streaming(struct vb2_queue *q, unsigned int count)
{
	struct native_node *node = queue_node(q);

	/* Hardware errors are asynchronous. Never return a failed start callback
	 * with DMA-owned buffers: vb2 would forcibly reclaim them as QUEUED.
	 */
	node->streaming = true;
	maybe_frame(node->owner);
	return 0;
}

static void return_pending(struct native_node *node)
{
	if (node->pending && node->pending->vb2_buf.state == VB2_BUF_STATE_ACTIVE)
		vb2_buffer_done(&node->pending->vb2_buf, VB2_BUF_STATE_ERROR);
	node->pending = NULL;
}

static void stop_streaming(struct vb2_queue *q)
{
	struct native_node *node = queue_node(q);

	/* Only guarded streamoff/release enter vb2 cancellation. No IRQ drain or
	 * retirement while holding queue lock (stop worker needs that lock).
	 */
	node->streaming = false;
	return_pending(node);
}

static const struct vb2_ops queue_ops = {
	.queue_setup = queue_setup,
	.buf_prepare = buffer_prepare,
	.buf_queue = buffer_queue,
	.start_streaming = start_streaming,
	.stop_streaming = stop_streaming,
	.wait_prepare = vb2_ops_wait_prepare,
	.wait_finish = vb2_ops_wait_finish,
};

/* Actual vb2 allocation cookies, never placeholders to make recipe validation
 * pass. Perform the frozen composer's pure checks BEFORE power/reset/PHY.
 */
static int preflight_buffer(struct mt6878_native_video *v,
	struct vb2_v4l2_buffer *buffer, unsigned int index,
	struct mt6878_camsv_buffer *mapped)
{
	struct vb2_buffer *vb;
	unsigned long capacity;

	if (!buffer || index > 1)
		return -EINVAL;
	vb = &buffer->vb2_buf;
	if (vb->vb2_queue != &v->nodes[index].queue || vb->num_planes != 1 ||
	    vb->state != VB2_BUF_STATE_ACTIVE || vb->planes[0].data_offset ||
	    vb->vb2_queue->dev != v->capture.direct.dma_owner ||
	    vb->vb2_queue->mem_ops != &vb2_dma_contig_memops ||
	    !vb2_plane_cookie(vb, 0))
		return -EINVAL;
	capacity = vb2_plane_size(vb, 0);
	if (!capacity || capacity > U32_MAX)
		return -ERANGE;
	*mapped = (struct mt6878_camsv_buffer) {
		.dma = vb2_dma_contig_plane_dma_addr(vb, 0), .size = capacity, .mapped = 1,
	};
	return 0;
}

static int preflight(struct mt6878_native_video *v,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf)
{
	struct mt6878_camsv_direct *d = &v->capture.direct;
	struct mt6878_camsv_job mapped = v->suppliers.layout;
	struct mt6878_camsv_buffer cq = { d->cq_dma, d->cq_capacity, 1 };
	int ret;

	lockdep_assert_held(&d->lock);
	ret = preflight_buffer(v, raw, 0, &mapped.raw);
	if (!ret)
		ret = preflight_buffer(v, pdaf, 1, &mapped.pdaf);
	if (ret)
		return ret;
	if (!d->cq_cpu || !d->dma_owner ||
	    iommu_get_domain_for_dev(d->dma_owner) != d->resources.domain)
		return -ESTALE;
	if (mt6878_camsv_overlap(&cq, &mapped.raw) || mt6878_camsv_overlap(&cq, &mapped.pdaf))
		return -ERANGE;
	if ((mapped.sequence >> 24) > 3)
		return -ESTALE;
	return mt6878_camsv_recipe_inputs(&mapped, &v->suppliers.config, &d->recipe_resources);
}

static void frame_work(struct work_struct *work)
{
	struct mt6878_native_video *v = container_of(work, struct mt6878_native_video, frame_work);
	struct vb2_v4l2_buffer *raw, *pdaf;
	int ret;

	mutex_lock(&v->capture.direct.lock);
	if (v->stopping) {
		mutex_unlock(&v->capture.direct.lock);
		return;
	}
	raw = v->nodes[0].pending;
	pdaf = v->nodes[1].pending;
	ret = preflight(v, raw, pdaf);
	if (ret) {
		/* No frame call and no HW attempt: return both buffers immediately.
		 * Bound sensor/receiver resource ownership still retires normally.
		 */
		if (!v->first_error)
			v->first_error = ret;
		return_pending(&v->nodes[0]);
		return_pending(&v->nodes[1]);
		vb2_queue_error(&v->nodes[0].queue);
		vb2_queue_error(&v->nodes[1].queue);
		mutex_unlock(&v->capture.direct.lock);
		return;
	}
	mutex_unlock(&v->capture.direct.lock);
	ret = mt6878_native_capture_frame(&v->capture, raw, pdaf,
		&v->suppliers.layout, &v->suppliers.config, v->suppliers.port, 0);
	if (!ret && !wait_for_completion_timeout(&v->capture.platform.stopped,
		msecs_to_jiffies(1000))) {
		ret = -ETIMEDOUT;
		mt6878_camsv_platform_stop_async(&v->capture.platform);
	}
	mutex_lock(&v->capture.direct.lock);
	if (!ret)
		ret = v->capture.platform.stop_error;
	if (ret && !v->first_error)
		v->first_error = ret;
	if (ret) {
		vb2_queue_error(&v->nodes[0].queue);
		vb2_queue_error(&v->nodes[1].queue);
	}
	mutex_unlock(&v->capture.direct.lock);
}

/* Caller holds registration, NOT queue lock. Successful cleanup is separate
 * from first frame failure; native retire retains that failure in capture.
 */
static int retire(struct mt6878_native_video *v)
{
	int ret;

	if (v->retired)
		return 0;
	if (v->quarantined)
		return -EBUSY;
	mutex_lock(&v->capture.direct.lock);
	v->stopping = true;
	v->ready = false;
	mutex_unlock(&v->capture.direct.lock);
	cancel_work_sync(&v->frame_work);
	ret = mt6878_native_capture_retire(&v->capture, msecs_to_jiffies(1500));
	if (ret) {
		v->quarantined = true;
		dev_err(&v->suppliers.pdev->dev,
			"camera retirement failed %d; retaining queues and supplier lease\n", ret);
		return ret;
	}
	mutex_lock(&v->capture.direct.lock);
	v->retired = true;
	mutex_unlock(&v->capture.direct.lock);
	return 0;
}

/* Frozen probe can retain CQ/platform resources after controller bind fails.
 * Resolve only that exact resource-only case. A stream attempt belongs to
 * native_capture_retire, not this unwind, even if its later flags look idle.
 */
static int retire_partial(struct mt6878_native_video *v)
{
	struct mt6878_native_capture *n = &v->capture;
	struct mt6878_camsv_platform *p = &n->platform;
	int ret;

	lockdep_assert_held(&v->registration);
	if (v->quarantined || n->bound || n->receiver_ref || n->smi_ref ||
	    n->reset_attempted || n->direct.pair.tx.attempted ||
	    n->controller.requested || n->controller.allocated ||
	    n->controller.route.phy.attempted || n->controller.route.route.attempted || p->powered)
		return -EBUSY;
	if (!n->direct.cq_cpu) {
		/* Fully unwound failed bind leaves p->direct pointing at this owner,
		 * but retired proves its IRQ/work/media/device references were released.
		 */
		return !n->direct.consumer && !n->direct.dma_owner &&
			(!p->direct || (p->retired && !p->requested)) ? 0 : -EBUSY;
	}
	if (p->direct) {
		if (p->direct != &n->direct)
			return -EINVAL;
		if (!p->retired) {
			ret = mt6878_camsv_platform_retire(p, msecs_to_jiffies(1500));
			if (ret && !p->retired)
				goto quarantine;
		}
	}
	mutex_lock(&n->direct.lock);
	ret = mt6878_camsv_direct_release(&n->direct);
	mutex_unlock(&n->direct.lock);
	if (!ret)
		return 0;
quarantine:
	v->quarantined = true;
	return ret;
}

static int querycap(struct file *file, void *priv, struct v4l2_capability *cap)
{
	strscpy(cap->driver, "mt6878-native-video", sizeof(cap->driver));
	strscpy(cap->card, "MT6878 first-frame", sizeof(cap->card));
	snprintf(cap->bus_info, sizeof(cap->bus_info), "platform:%s",
		dev_name(&file_node(file)->owner->suppliers.pdev->dev));
	return 0;
}

static int enum_format(struct file *file, void *priv, struct v4l2_fmtdesc *fmt)
{
	if (fmt->index)
		return -EINVAL;
	fmt->pixelformat = file_node(file)->index ? V4L2_META_FMT_GENERIC_8 : V4L2_PIX_FMT_SRGGB10P;
	return 0;
}

static int get_format(struct file *file, void *priv, struct v4l2_format *fmt)
{
	struct native_node *node = file_node(file);
	const struct mt6878_camsv_dma_layout *l = node_layout(node);

	if (fmt->type != node->queue.type)
		return -EINVAL;
	if (node->index) {
		fmt->fmt.meta = (struct v4l2_meta_format) {
			.dataformat = V4L2_META_FMT_GENERIC_8, .buffersize = l->sizeimage,
			.width = l->width, .height = l->height, .bytesperline = l->bytesperline,
		};
	} else {
		fmt->fmt.pix = (struct v4l2_pix_format) {
			.width = l->width, .height = l->height, .pixelformat = V4L2_PIX_FMT_SRGGB10P,
			.field = V4L2_FIELD_NONE, .bytesperline = l->bytesperline,
			.sizeimage = l->sizeimage, .colorspace = V4L2_COLORSPACE_RAW,
		};
	}
	return 0;
}

static int set_format(struct file *file, void *priv, struct v4l2_format *fmt)
{
	struct native_node *node = file_node(file);
	struct mt6878_native_video *v = node->owner;
	int ret;

	/* S_FMT dispatch holds registration, not the INFO_FL_QUEUE lock.
	 * Fixed sensor mode is already pipeline-owned: normalize to its emitted
	 * layout only before buffer allocation, never mutate ACTIVE subdev state.
	 */
	mutex_lock(&v->capture.direct.lock);
	ret = vb2_is_busy(&node->queue) || v->stopping ? -EBUSY : get_format(file, priv, fmt);
	mutex_unlock(&v->capture.direct.lock);
	return ret;
}

static int request_buffers(struct file *file, void *priv, struct v4l2_requestbuffers *req)
{
	struct mt6878_native_video *v = file_node(file)->owner;

	/* count=0 is destructive too. After frame submission only guarded close
	 * or streamoff may release memory, including pre-DMA failed submission.
	 */
	if (req->memory != V4L2_MEMORY_MMAP)
		return -EINVAL;
	if (!req->count && v->retired)
		return vb2_ioctl_reqbufs(file, priv, req);
	if (v->stopping || v->used)
		return -EBUSY;
	return vb2_ioctl_reqbufs(file, priv, req);
}

static int queue_buffer(struct file *file, void *priv, struct v4l2_buffer *buf)
{
	struct mt6878_native_video *v = file_node(file)->owner;

	if (v->stopping || v->used)
		return -ESHUTDOWN;
	return vb2_ioctl_qbuf(file, priv, buf);
}

static int stream_on(struct file *file, void *priv, enum v4l2_buf_type type)
{
	struct mt6878_native_video *v = file_node(file)->owner;

	if (v->stopping || v->used)
		return -ESHUTDOWN;
	return vb2_ioctl_streamon(file, priv, type);
}

static int stream_off(struct file *file, void *priv, enum v4l2_buf_type type)
{
	struct native_node *node = file_node(file);
	struct mt6878_native_video *v = node->owner;
	int ret;

	if (type != node->queue.type || node->queue.owner != file->private_data)
		return -EINVAL;
	/* V4L2 INFO_FL_QUEUE ioctl dispatch holds direct.lock. Drop it before
	 * cancel/drain, then reacquire before native vb2 streamoff. registration
	 * serializes concurrent closes and unregister; stopping blocks new queues.
	 */
	v->stopping = true;
	mutex_unlock(&v->capture.direct.lock);
	mutex_lock(&v->registration);
	ret = retire(v);
	mutex_unlock(&v->registration);
	mutex_lock(&v->capture.direct.lock);
	if (ret)
		return ret;
	return vb2_ioctl_streamoff(file, priv, type);
}

static const struct v4l2_ioctl_ops ioctl_ops = {
	.vidioc_querycap = querycap,
	.vidioc_enum_fmt_vid_cap = enum_format,
	.vidioc_enum_fmt_meta_cap = enum_format,
	.vidioc_g_fmt_vid_cap = get_format,
	.vidioc_g_fmt_meta_cap = get_format,
	.vidioc_try_fmt_vid_cap = get_format,
	.vidioc_try_fmt_meta_cap = get_format,
	.vidioc_s_fmt_vid_cap = set_format,
	.vidioc_s_fmt_meta_cap = set_format,
	.vidioc_reqbufs = request_buffers,
	.vidioc_querybuf = vb2_ioctl_querybuf,
	.vidioc_qbuf = queue_buffer,
	.vidioc_dqbuf = vb2_ioctl_dqbuf,
	.vidioc_streamon = stream_on,
	.vidioc_streamoff = stream_off,
};

static int node_open(struct native_node *node, struct file *file)
{
	struct mt6878_native_video *v = node->owner;
	int ret;

	mutex_lock(&v->registration);
	ret = -ENODEV;
	if (v->ready && !v->quarantined) {
		mutex_lock(&v->capture.direct.lock);
		if (!v->stopping)
			ret = v4l2_fh_open(file);
		mutex_unlock(&v->capture.direct.lock);
	}
	if (!ret)
		v->opens++;
	mutex_unlock(&v->registration);
	return ret;
}

static int video_open(struct file *file)
{
	return node_open(file_node(file), file);
}

static int video_release(struct file *file)
{
	struct native_node *node = file_node(file);
	struct mt6878_native_video *v = node->owner;
	int ret = 0;

	mutex_lock(&v->registration);
	/* An unrelated open never owns the queue and must not retire its frame. */
	if (node->queue.owner == file->private_data)
		ret = retire(v);
	if (!ret) {
		ret = vb2_fop_release(file);
		v->opens--;
	} else {
		/* release cannot veto close. Retain the independent v4l2_fh and vb2
		 * queue.owner instead of freeing DMA or buffer metadata under hardware.
		 * Registration's module pin and nonzero opens prohibit unregister.
		 */
		file->private_data = NULL;
	}
	mutex_unlock(&v->registration);
	return ret;
}

static const struct v4l2_file_operations file_ops = {
	.owner = THIS_MODULE,
	.open = video_open,
	.release = video_release,
	.unlocked_ioctl = video_ioctl2,
	.poll = vb2_fop_poll,
	.mmap = vb2_fop_mmap,
};

static int notifier_bound(struct v4l2_async_notifier *nf, struct v4l2_subdev *sd,
	struct v4l2_async_connection *connection)
{
	struct mt6878_native_video *v = container_of(nf, struct mt6878_native_video, notifier);
	int ret = 0;

	mutex_lock(&v->registration);
	if (v->removing)
		ret = -ESHUTDOWN;
	else if (sd->entity.num_pads != 2 || !mt6878_seninf_native_base(sd))
		ret = -EINVAL;
	else
		v->receiver = sd;
	mutex_unlock(&v->registration);
	return ret;
}

static int video_link_validate(struct media_link *link)
{
	struct native_node *node = container_of(link->sink->entity, struct native_node, vdev.entity);
	struct mt6878_native_video *v = node->owner;
	struct v4l2_subdev_format fmt = {
		.which = V4L2_SUBDEV_FORMAT_ACTIVE, .pad = 1,
	};
	struct v4l2_subdev *sd;
	int ret;

	if (link->sink->index || link->source->index != 1 ||
	    !is_media_entity_v4l2_subdev(link->source->entity))
		return -EINVAL;
	sd = media_entity_to_v4l2_subdev(link->source->entity);
	if (sd != v->receiver)
		return -ENOLINK;
	ret = v4l2_subdev_call_state_active(sd, pad, get_fmt, &fmt);
	if (ret)
		return ret;
	/* Both outputs belong to the same active sensor mode. Metadata geometry
	 * is separately validated at registration, not compared to RAW height.
	 */
	return fmt.format.code == MEDIA_BUS_FMT_SRGGB10_1X10 &&
		fmt.format.field == V4L2_FIELD_NONE &&
		fmt.format.width == v->suppliers.layout.width &&
		fmt.format.height == v->suppliers.layout.height ? 0 : -EPIPE;
}

static const struct media_entity_operations video_entity_ops = {
	.link_validate = video_link_validate,
};

/* V4L2 core has already removed this node's interfaces/entity here. Its local
 * v4l2_dev is NULL because this owner never installs v4l2.release. Signal only:
 * both nodes and the entire root remain alive until the caller drains them.
 */
static void video_final_release(struct video_device *vdev)
{
	struct native_node *node = container_of(vdev, struct native_node, vdev);

	complete_all(&node->released);
}

static int register_node(struct native_node *node)
{
	int ret;

	init_completion(&node->released);
	node->release_expected = true;
	ret = video_register_device(&node->vdev, VFL_TYPE_VIDEO, -1);
	if (!ret)
		node->registered = true;
	else if (!node->vdev.dev.release)
		/* Failure before device_register: no device ref or core release exists.
		 * device_register failure, in contrast, runs the real final callback.
		 */
		video_final_release(&node->vdev);
	return ret;
}

static void detach_nodes(struct mt6878_native_video *v)
{
	unsigned int i;

	for (i = 0; i < 2; i++) {
		if (v->nodes[i].registered) {
			v->nodes[i].registered = false;
			video_unregister_device(&v->nodes[i].vdev);
		}
	}
}

static int drain_nodes(struct mt6878_native_video *v, unsigned long timeout)
{
	unsigned long deadline = jiffies + timeout;
	unsigned int i;

	lockdep_assert_not_held(&v->registration);
	if (!timeout)
		return -EINVAL;
	for (i = 0; i < 2; i++) {
		struct native_node *node = &v->nodes[i];
		unsigned long now = jiffies;

		if (!node->release_expected || completion_done(&node->released))
			continue;
		if (time_after_eq(now, deadline) ||
		    !wait_for_completion_timeout(&node->released, deadline - now))
			return -ETIMEDOUT;
	}
	return 0;
}

static void cleanup_nodes(struct mt6878_native_video *v)
{
	unsigned int i;

	for (i = 0; i < 2; i++) {
		if (v->nodes[i].initialized) {
			vb2_queue_release(&v->nodes[i].queue);
			media_entity_cleanup(&v->nodes[i].vdev.entity);
			v->nodes[i].initialized = false;
		}
	}
}

static int notifier_complete(struct v4l2_async_notifier *nf)
{
	struct mt6878_native_video *v = container_of(nf, struct mt6878_native_video, notifier);
	struct mt6878_native_video_suppliers *s = &v->suppliers;
	struct v4l2_subdev_format fmt = { .which = V4L2_SUBDEV_FORMAT_ACTIVE };
	struct media_pad *source;
	struct v4l2_subdev *sensor;
	unsigned int i;
	int ret;

	mutex_lock(&v->registration);
	if (v->removing || v->ready || v->registration_error || v->retired ||
	    v->quarantined || v->capture.direct.consumer) {
		ret = -EALREADY;
		goto out;
	}
	source = media_pad_remote_pad_unique(&v->receiver->entity.pads[0]);
	if (IS_ERR_OR_NULL(source) || !is_media_entity_v4l2_subdev(source->entity)) {
		ret = -ENOLINK;
		goto fail;
	}
	sensor = media_entity_to_v4l2_subdev(source->entity);
	/* Native capture pins these modules. Manual unbind must also be hidden:
	 * supplier remove callbacks cannot veto freeing their borrowed devres.
	 */
	if (!sensor->dev->driver || !sensor->dev->driver->suppress_bind_attrs ||
	    !v->receiver->dev->driver || !v->receiver->dev->driver->suppress_bind_attrs ||
	    !sensor->dev->of_node || of_node_check_flag(sensor->dev->of_node, OF_DYNAMIC) ||
	    !v->receiver->dev->of_node ||
	    of_node_check_flag(v->receiver->dev->of_node, OF_DYNAMIC)) {
		ret = -EOPNOTSUPP;
		goto fail;
	}
	fmt.pad = source->index;
	ret = v4l2_subdev_call_state_active(sensor, pad, get_fmt, &fmt);
	if (ret)
		goto fail;
	if (fmt.format.code != MEDIA_BUS_FMT_SRGGB10_1X10 ||
	    fmt.format.width != s->layout.width || fmt.format.height != s->layout.height) {
		ret = -EINVAL;
		goto fail;
	}
	ret = mt6878_native_capture_probe(&v->capture, s->pdev, s->dma, s->cam_main,
		s->smi, v->receiver, sensor, source->index, s->cam_main_base, s->cam_main_size);
	if (ret)
		goto fail;
	/* Resource-only bind acquired the existing sensor/receiver pipeline.
	 * Extend it with the real video sinks before any PM/MMIO/stream attempt.
	 */
	media_pipeline_stop(v->capture.platform.origin);
	v->capture.platform.media_owned = false;
	for (i = 0; i < 2; i++) {
		struct native_node *node = &v->nodes[i];

		node->owner = v;
		node->index = i;
		ret = mt6878_camsv_direct_queue_init(&v->capture.direct, &node->queue,
			&queue_ops, i ? V4L2_BUF_TYPE_META_CAPTURE : V4L2_BUF_TYPE_VIDEO_CAPTURE,
			sizeof(struct vb2_v4l2_buffer));
		if (ret)
			goto fail;
		node->queue.io_modes = VB2_MMAP;
		node->queue.max_num_buffers = 1;
		node->queue.min_queued_buffers = 1;
		node->vdev = (struct video_device) {
			.v4l2_dev = &v->v4l2, .fops = &file_ops, .ioctl_ops = &ioctl_ops,
			.release = video_final_release, .queue = &node->queue,
			.lock = &v->registration, .vfl_dir = VFL_DIR_RX,
			.device_caps = V4L2_CAP_STREAMING |
				(i ? V4L2_CAP_META_CAPTURE : V4L2_CAP_VIDEO_CAPTURE),
		};
		strscpy(node->vdev.name, i ? "MT6878 PDAF first-frame" : "MT6878 RAW10 first-frame",
			sizeof(node->vdev.name));
		node->vdev.entity.ops = &video_entity_ops;
		node->pad.flags = MEDIA_PAD_FL_SINK;
		ret = media_entity_pads_init(&node->vdev.entity, 1, &node->pad);
		if (ret) {
			vb2_queue_release(&node->queue);
			goto fail;
		}
		node->initialized = true;
		ret = register_node(node);
		if (ret)
			goto fail;
		ret = media_create_pad_link(&v->receiver->entity, 1,
			&node->vdev.entity, 0, MEDIA_LNK_FL_ENABLED | MEDIA_LNK_FL_IMMUTABLE);
		if (ret)
			goto fail;
	}
	ret = media_pipeline_start(v->capture.platform.origin, &v->capture.platform.pipeline);
	if (ret)
		goto fail;
	v->capture.platform.media_owned = true;
	v->ready = true;
	complete_all(&v->registration_done);
	ret = 0;
	goto out;
fail:
	v->registration_error = v->capture.first_error ? v->capture.first_error : ret;
	complete_all(&v->registration_done);
	/* Registration remains owned even if a partial capture bind cannot retire.
	 * Do not trigger async-core unwinding of a live capture graph here.
	 */
	dev_err(&s->pdev->dev, "camera video registration incomplete: %d\n", ret);
	ret = 0;
out:
	mutex_unlock(&v->registration);
	return ret;
}

static void notifier_unbind(struct v4l2_async_notifier *nf, struct v4l2_subdev *sd,
	struct v4l2_async_connection *connection)
{
	struct mt6878_native_video *v = container_of(nf, struct mt6878_native_video, notifier);

	mutex_lock(&v->registration);
	v->ready = false;
	complete_all(&v->registration_done);
	if (v->capture.bound && retire(v))
		dev_err(&v->suppliers.pdev->dev, "unsafe forced receiver removal\n");
	v->receiver = NULL;
	mutex_unlock(&v->registration);
}

static const struct v4l2_async_notifier_operations notifier_ops = {
	.bound = notifier_bound, .complete = notifier_complete, .unbind = notifier_unbind,
};

static int pin_supplier(struct device *dev, struct module **owner)
{
	int ret = -EOPNOTSUPP;

	device_lock(dev);
	if (dev->driver && device_is_bound(dev) && dev->driver->suppress_bind_attrs &&
	    dev->of_node && !of_node_check_flag(dev->of_node, OF_DYNAMIC) &&
	    try_module_get(dev->driver->owner)) {
		*owner = dev->driver->owner;
		get_device(dev);
		ret = 0;
	}
	device_unlock(dev);
	return ret;
}

static struct device *supplier_device(struct mt6878_native_video *v, unsigned int index)
{
	switch (index) {
	case 0:
		return &v->suppliers.pdev->dev;
	case 1:
		return v->suppliers.dma;
	case 2:
		return v->suppliers.cam_main;
	default:
		return v->suppliers.smi;
	}
}

int mt6878_native_video_register(const struct mt6878_native_video_suppliers *s,
	struct mt6878_native_video **result)
{
	struct v4l2_async_connection *connection;
	struct mt6878_native_video *v;
	unsigned int pinned = 0;
	int ret;

	if (!result)
		return -EINVAL;
	*result = NULL;
	if (!s || !s->pdev || !s->dma || !s->cam_main || !s->smi || !s->receiver ||
	    IS_ERR_OR_NULL(s->cam_main_base) || s->cam_main_size < 0x5c || s->port > 1 ||
	    s->dma == &s->pdev->dev || !device_is_bound(&s->pdev->dev) ||
	    !device_is_bound(s->dma) || !device_is_bound(s->cam_main) ||
	    !device_is_bound(s->smi) ||
	    s->layout.raw_layout.format != SV_DMA_FMT_BAYER10_MIPI ||
	    s->layout.pdaf_layout.format != SV_DMA_FMT_BAYER8 ||
	    !((s->layout.width == 4000 && s->layout.height == 3000) ||
	      (s->layout.width == 4096 && s->layout.height == 2304)) ||
	    s->layout.raw_layout.width != s->layout.width ||
	    s->layout.raw_layout.height != s->layout.height ||
	    s->layout.pdaf_layout.width != s->layout.width ||
	    s->layout.pdaf_layout.height != s->layout.height / 4 ||
	    mt6878_camsv_layout_validate(&s->layout.raw_layout, s->layout.raw_layout.sizeimage) ||
	    mt6878_camsv_layout_validate(&s->layout.pdaf_layout, s->layout.pdaf_layout.sizeimage))
		return -EINVAL;
	if (!try_module_get(THIS_MODULE))
		return -ENODEV;
	v = kzalloc(sizeof(*v), GFP_KERNEL);
	if (!v) {
		module_put(THIS_MODULE);
		return -ENOMEM;
	}
	v->suppliers = *s;
	for (pinned = 0; pinned < 4; pinned++) {
		ret = pin_supplier(supplier_device(v, pinned), &v->supplier_modules[pinned]);
		if (ret)
			goto unpin;
	}
	fwnode_handle_get(s->receiver);
	mutex_init(&v->registration);
	init_completion(&v->registration_done);
	INIT_WORK(&v->frame_work, frame_work);
	v->media.dev = &s->pdev->dev;
	strscpy(v->media.model, "MT6878 native first-frame", sizeof(v->media.model));
	media_device_init(&v->media);
	v->v4l2.mdev = &v->media;
	ret = v4l2_device_register(&s->pdev->dev, &v->v4l2);
	if (ret)
		goto cleanup;
	ret = media_device_register(&v->media);
	if (ret)
		goto unregister_v4l2;
	v4l2_async_nf_init(&v->notifier, &v->v4l2);
	v->notifier.ops = &notifier_ops;
	connection = v4l2_async_nf_add_fwnode(&v->notifier, s->receiver,
		struct v4l2_async_connection);
	ret = IS_ERR(connection) ? PTR_ERR(connection) : v4l2_async_nf_register(&v->notifier);
	if (ret) {
		/* Even a failed async registration may have published one video node.
		 * Route through the same ref-draining teardown, never direct kfree.
		 */
		v->registration_error = ret;
		*result = v;
		if (!mt6878_native_video_unregister(v))
			*result = NULL;
		return ret;
	}
	*result = v;
	return 0;
unregister_v4l2:
	v4l2_device_unregister(&v->v4l2);
cleanup:
	media_device_cleanup(&v->media);
	fwnode_handle_put(s->receiver);
unpin:
	while (pinned) {
		pinned--;
		put_device(supplier_device(v, pinned));
		module_put(v->supplier_modules[pinned]);
	}
	kfree(v);
	module_put(THIS_MODULE);
	return ret;
}

int mt6878_native_video_wait_ready(struct mt6878_native_video *v, unsigned long timeout)
{
	int ret;

	if (!v || !timeout)
		return -EINVAL;
	if (!wait_for_completion_timeout(&v->registration_done, timeout))
		return -ETIMEDOUT;
	mutex_lock(&v->registration);
	ret = v->registration_error ? v->registration_error :
		(v->ready && !v->removing ? 0 : -ESHUTDOWN);
	mutex_unlock(&v->registration);
	return ret;
}

int mt6878_native_video_unregister(struct mt6878_native_video *v)
{
	unsigned int i;
	int ret = 0;

	if (!v)
		return -EINVAL;
	mutex_lock(&v->registration);
	v->ready = false;
	v->removing = true;
	complete_all(&v->registration_done);
	if (v->capture.bound) {
		mutex_lock(&v->capture.direct.lock);
		v->stopping = true;
		mutex_unlock(&v->capture.direct.lock);
	}
	if (v->opens || v->quarantined)
		ret = -EBUSY;
	else if (v->capture.bound)
		ret = retire(v);
	else if (v->retired)
		ret = 0;
	else
		ret = retire_partial(v);
	if (ret) {
		mutex_unlock(&v->registration);
		return ret;
	}
	v->retired = true;
	detach_nodes(v);
	mutex_unlock(&v->registration);
	/* video_get precedes open callback; video_put follows close callback.
	 * opens==0 is therefore NOT a lifetime proof. Do not block pending opens
	 * on registration while waiting for their actual device reference to drop.
	 */
	ret = drain_nodes(v, msecs_to_jiffies(1500));
	if (ret)
		return ret; /* Entire root/lease retained; caller may retry this drain. */
	cleanup_nodes(v);
	/* Async unbind callback takes registration: never unregister under it. */
	v4l2_async_nf_unregister(&v->notifier);
	v4l2_async_nf_cleanup(&v->notifier);
	media_device_unregister(&v->media);
	v4l2_device_unregister(&v->v4l2);
	media_device_cleanup(&v->media);
	fwnode_handle_put(v->suppliers.receiver);
	for (i = 0; i < 4; i++) {
		put_device(supplier_device(v, i));
		module_put(v->supplier_modules[i]);
	}
	kfree(v);
	module_put(THIS_MODULE);
	return 0;
}

#if IS_ENABLED(CONFIG_KUNIT)
#include "video-lifetime-test.inc"
#endif
