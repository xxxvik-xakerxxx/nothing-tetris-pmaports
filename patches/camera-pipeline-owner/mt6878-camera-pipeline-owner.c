// SPDX-License-Identifier: GPL-2.0-only
/* Compile-only owner; no probe, video node, DT activation or module init. */
#include <linux/err.h>
#include <linux/file.h>
#include <linux/fcntl.h>
#include <linux/kernel.h>
#include <linux/scatterlist.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <media/media-entity.h>
#include "mt6878-camera-pipeline-owner.h"
#include "mt6878-seninf-contract.h"

void mt6878_pipeline_unmap(struct mt6878_pipeline_mapping *mapping)
{
	if (!mapping || WARN_ON(mapping->cpu_active))
		return;
	if (mapping->vmap_acquired)
		dma_buf_vunmap_unlocked(mapping->buffer, &mapping->va);
	if (mapping->sgt)
		dma_buf_unmap_attachment_unlocked(mapping->attachment, mapping->sgt, DMA_BIDIRECTIONAL);
	if (mapping->attachment)
		dma_buf_detach(mapping->buffer, mapping->attachment);
	if (mapping->buffer)
		dma_buf_put(mapping->buffer);
	memset(mapping, 0, sizeof(*mapping));
}

int mt6878_pipeline_map(struct mt6878_pipeline_mapping *mapping,
	struct dma_buf *buffer, struct device *device, unsigned int minimum)
{
	struct mt6878_pipeline_mapping value = { 0 };
	int ret;

	if (!mapping || !buffer || !device || !minimum || mapping->buffer ||
	    buffer->size < minimum || buffer->size > UINT_MAX)
		return -EINVAL;
	get_dma_buf(buffer);
	value.buffer = buffer;
	value.attachment = dma_buf_attach(buffer, device);
	if (IS_ERR(value.attachment)) {
		ret = PTR_ERR(value.attachment);
		value.attachment = NULL;
		goto fail;
	}
	value.sgt = dma_buf_map_attachment_unlocked(value.attachment, DMA_BIDIRECTIONAL);
	if (IS_ERR(value.sgt)) {
		ret = PTR_ERR(value.sgt);
		value.sgt = NULL;
		goto fail;
	}
	/* One contiguous mapped IOVA covering the entire exported allocation.
	 * Never assume that the first SG entry represents all of a multi-SG buffer.
	 */
	if (!value.sgt || value.sgt->nents != 1 || !value.sgt->sgl ||
	    sg_dma_len(value.sgt->sgl) < buffer->size) {
		ret = -ERANGE;
		goto fail;
	}
	value.range = (struct mt6878_camsv_buffer) {
		.dma = sg_dma_address(value.sgt->sgl), .size = buffer->size, .mapped = 1,
	};
	ret = mt6878_camsv_range(&value.range, value.range.size);
	if (ret)
		goto fail;
	ret = dma_buf_vmap_unlocked(buffer, &value.va);
	if (ret)
		goto fail;
	value.vmap_acquired = true;
	if (iosys_map_is_null(&value.va) || value.va.is_iomem) {
		ret = -EOPNOTSUPP;
		goto fail;
	}
	*mapping = value;
	return 0;
fail:
	mt6878_pipeline_unmap(&value);
	return ret;
}

int mt6878_pipeline_init(struct mt6878_pipeline_owner *owner,
	struct device *dma_owner, struct iommu_domain *domain, unsigned int session)
{
	if (!owner || !dma_owner || !domain || !current->mm || session > 3 ||
	    iommu_get_domain_for_dev(dma_owner) != domain)
		return -EINVAL;
	memset(owner, 0, sizeof(*owner));
	mutex_init(&owner->lock);
	spin_lock_init(&owner->callback_lock);
	get_task_struct(current);
	owner->consumer = current;
	owner->dma_owner = get_device(dma_owner);
	owner->domain = domain;
	mt6878_camera_ccd_init(&owner->ccd, session);
	return 0;
}

static int owner_task(struct mt6878_pipeline_owner *owner)
{
	if (!owner || owner->consumer != current || !current->mm)
		return -EPERM;
	if (iommu_get_domain_for_dev(owner->dma_owner) != owner->domain)
		return -EXDEV;
	return 0;
}

int mt6878_pipeline_import(struct mt6878_pipeline_owner *owner, int work_fd, int message_fd)
{
	struct dma_buf *work, *message;
	int ret = owner_task(owner);

	if (ret)
		return ret;
	mutex_lock(&owner->lock);
	if (owner->work.buffer || owner->message.buffer || owner->published) {
		ret = -EALREADY;
		goto out;
	}
	work = dma_buf_get(work_fd);
	if (IS_ERR(work)) {
		ret = PTR_ERR(work);
		goto out;
	}
	message = dma_buf_get(message_fd);
	if (IS_ERR(message)) {
		ret = PTR_ERR(message);
		goto put_work;
	}
	if (work == message) {
		ret = -EINVAL;
		goto put_both;
	}
	ret = mt6878_pipeline_map(&owner->work, work, owner->dma_owner,
		MT6878_CAMSV_RECIPE_WRITES * 16 + 12);
	if (!ret)
		ret = mt6878_pipeline_map(&owner->message, message, owner->dma_owner,
			sizeof(struct mtkcam_ipi_frame_param));
	if (!ret && ((owner->work.range.dma & 15) ||
	    (owner->work.range.size & 3) ||
	    mt6878_camsv_overlap(&owner->work.range, &owner->message.range)))
		ret = -ERANGE;
	if (ret) {
		mt6878_pipeline_unmap(&owner->message);
		mt6878_pipeline_unmap(&owner->work);
	}
put_both:
	dma_buf_put(message);
put_work:
	dma_buf_put(work);
out:
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_pipeline_export(struct mt6878_pipeline_owner *owner, bool message)
{
	struct dma_buf *buffer;
	int ret = owner_task(owner);

	if (ret)
		return ret;
	mutex_lock(&owner->lock);
	buffer = message ? owner->message.buffer : owner->work.buffer;
	if (!buffer || owner->published) {
		ret = -EINVAL;
		goto out;
	}
	/* dma_buf_fd transfers this extra reference on success, in current's table. */
	get_dma_buf(buffer);
	ret = dma_buf_fd(buffer, O_RDWR | O_CLOEXEC);
	if (ret < 0)
		dma_buf_put(buffer);
out:
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_pipeline_endpoint(struct mt6878_pipeline_owner *owner, struct rpmsg_device *client)
{
	struct rpmsg_channel_info info = { .dst = RPMSG_ADDR_ANY };
	unsigned long flags;
	int ret = owner_task(owner);

	if (ret || !client)
		return ret ? ret : -EINVAL;
	mutex_lock(&owner->lock);
	info.src = owner->ccd.session + 1;
	snprintf(info.name, sizeof(info.name), "mtk-camsys%u", owner->ccd.session);
	if (owner->endpoint || client->ept || strcmp(client->id.name, info.name)) {
		ret = -EINVAL;
		goto out;
	}
	owner->endpoint = rpmsg_create_ept(client, mt6878_pipeline_rx, owner, info);
	if (!owner->endpoint) {
		ret = -ENOMEM;
		goto out;
	}
	/* Pinned CCD READ/WRITE resolve client->ept, not an arbitrary extra endpoint.
	 * The bus driver's remove lock must cover this assignment and all callers.
	 */
	client->ept = owner->endpoint;
	/* Frozen bind requires its direct callback, so bind this wrapper under the
	 * same lock/identity rules without replacing a live callback or its priv.
	 */
	spin_lock_irqsave(&owner->ccd.reply_lock, flags);
	owner->ccd.client = client;
	owner->ccd.endpoint = owner->endpoint;
	spin_unlock_irqrestore(&owner->ccd.reply_lock, flags);
	ret = 0;
out:
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_pipeline_bind(struct mt6878_pipeline_owner *owner,
	struct v4l2_subdev *sensor, unsigned int sensor_pad,
	struct v4l2_subdev *receiver, struct mt6878_camera_capture_owner *capture)
{
	struct media_link *link;
	struct v4l2_subdev_format format = { .which = V4L2_SUBDEV_FORMAT_ACTIVE };
	struct v4l2_mbus_frame_desc desc;
	struct v4l2_mbus_config bus;
	struct mt6878_seninf_packet packets[2];
	unsigned int i;
	int ret = owner_task(owner);

	if (ret || !sensor || !receiver || !capture || !capture->resources ||
	    sensor_pad >= sensor->entity.num_pads || !receiver->entity.num_pads)
		return ret ? ret : -EINVAL;
	/* Caller holds media graph and subdevice unbind serialization. */
	link = media_entity_find_link(&sensor->entity.pads[sensor_pad], &receiver->entity.pads[0]);
	if (!link || !(link->flags & MEDIA_LNK_FL_ENABLED) ||
	    capture->allocator != owner->dma_owner || capture->resources->domain != owner->domain)
		return -EXDEV;
	if (!receiver->entity.ops || !receiver->entity.ops->link_validate)
		return -EOPNOTSUPP;
	/* Run the concrete receiver's endpoint/format/trio validation, not a
	 * generic link helper that can accept an unsupported provider silently.
	 */
	ret = receiver->entity.ops->link_validate(link);
	if (ret)
		return ret;
	format.pad = sensor_pad;
	ret = v4l2_subdev_call_state_active(sensor, pad, get_fmt, &format);
	if (ret)
		return ret;
	ret = v4l2_subdev_call(sensor, pad, get_frame_desc, sensor_pad, &desc);
	if (ret)
		return ret;
	if (format.format.code != MEDIA_BUS_FMT_SRGGB10_1X10 ||
	    format.format.field != V4L2_FIELD_NONE ||
	    desc.type != V4L2_MBUS_FRAME_DESC_TYPE_CSI2 || desc.num_entries != 2)
		return -EINVAL;
	ret = v4l2_subdev_call(sensor, pad, get_mbus_config, sensor_pad, &bus);
	if (ret)
		return ret;
	if (bus.type != V4L2_MBUS_CSI2_CPHY || bus.bus.mipi_csi2.num_data_lanes != 3 ||
	    bus.bus.mipi_csi2.data_lanes[0] != 0 || bus.bus.mipi_csi2.data_lanes[1] != 1 ||
	    bus.bus.mipi_csi2.data_lanes[2] != 2)
		return -EINVAL;
	for (i = 0; i < 2; i++) {
		if (!(desc.entry[i].flags & V4L2_MBUS_FRAME_DESC_FL_LEN_MAX) || desc.entry[i].stream)
			return -EINVAL;
		packets[i] = (struct mt6878_seninf_packet) {
			.vc = desc.entry[i].bus.csi2.vc, .dt = desc.entry[i].bus.csi2.dt,
			.length = desc.entry[i].length,
		};
	}
	ret = mt6878_seninf_check_packets(format.format.width, format.format.height, 2, packets);
	if (ret)
		return ret;
	mutex_lock(&owner->lock);
	if (owner->sensor || owner->published)
		ret = -EALREADY;
	else {
		owner->sensor = sensor;
		owner->sensor_pad = sensor_pad;
		owner->receiver = receiver;
		owner->capture = capture;
		owner->width = format.format.width;
		owner->height = format.format.height;
	}
	mutex_unlock(&owner->lock);
	return ret;
}

static int plane_matches(struct mt6878_pipeline_owner *owner,
	struct vb2_v4l2_buffer *buffer, const struct mt6878_camsv_buffer *range)
{
	if (!buffer || !buffer->vb2_buf.vb2_queue || buffer->vb2_buf.num_planes != 1 ||
	    buffer->vb2_buf.state != VB2_BUF_STATE_ACTIVE ||
	    buffer->vb2_buf.vb2_queue->dev != owner->dma_owner ||
	    buffer->vb2_buf.vb2_queue->mem_ops != &vb2_dma_contig_memops ||
	    !vb2_plane_cookie(&buffer->vb2_buf, 0) ||
	    vb2_plane_size(&buffer->vb2_buf, 0) != range->size ||
	    vb2_dma_contig_plane_dma_addr(&buffer->vb2_buf, 0) != range->dma)
		return -EXDEV;
	return 0;
}

static int fill_message(struct mt6878_pipeline_owner *owner, const struct mt6878_camsv_job *job)
{
	struct mtkcam_ipi_img_output *outputs;
	const struct mt6878_camsv_dma_layout *layout;
	const struct mt6878_camsv_buffer *buffer;
	unsigned int i;
	int ret, cleanup;

	/* Large packed ABI objects never belong on the kernel stack. */
	outputs = kcalloc(2, sizeof(*outputs), GFP_KERNEL);
	if (!outputs)
		return -ENOMEM;
	for (i = 0; i < 2; i++) {
		layout = i ? &job->pdaf_layout : &job->raw_layout;
		buffer = i ? &job->pdaf : &job->raw;
		outputs[i].uid.pipe_id = job->sv_id + MTKCAM_SUBDEV_CAMSV_START;
		outputs[i].uid.id = MTKCAM_IPI_CAMSV_MAIN_OUT;
		outputs[i].fmt.format = layout->format;
		outputs[i].fmt.s.w = layout->width;
		outputs[i].fmt.s.h = layout->height;
		outputs[i].fmt.stride[0] = layout->bytesperline;
		outputs[i].buf[0][0].iova = buffer->dma;
		outputs[i].buf[0][0].size = buffer->size;
	}
	ret = dma_buf_begin_cpu_access(owner->message.buffer, DMA_TO_DEVICE);
	if (ret)
		goto out;
	owner->message.cpu_active = true;
	ret = mt6878_camera_frame(owner->message.va.vaddr, job, 0, owner->work.range.size,
		owner->work.range.size, &outputs[0], &outputs[1]);
	cleanup = dma_buf_end_cpu_access(owner->message.buffer, DMA_TO_DEVICE);
	if (!cleanup)
		owner->message.cpu_active = false;
	if (!ret)
		ret = cleanup;
out:
	kfree(outputs);
	return ret;
}

int mt6878_pipeline_publish(struct mt6878_pipeline_owner *owner,
	const struct mtkcam_ipi_config_param *config, const struct mt6878_camsv_job *job,
	const struct mt6878_camsv_recipe_resources *resources, int work_fd, int message_fd,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf)
{
	struct mtkcam_ipi_session_param params = { 0 };
	struct dma_buf *work, *message;
	int ret = owner_task(owner);

	if (ret)
		return ret;
	mutex_lock(&owner->lock);
	if (!owner->sensor || !owner->endpoint || owner->callbacks_detached ||
	    READ_ONCE(owner->callback_closed) ||
	    owner->published || owner->first_error ||
	    !owner->work.buffer || !owner->message.buffer) {
		ret = -EINVAL;
		goto out;
	}
	ret = mt6878_camsv_recipe_inputs(job, config, resources);
	if (ret)
		goto out;
	work = dma_buf_get(work_fd);
	if (IS_ERR(work)) {
		ret = PTR_ERR(work);
		goto out;
	}
	message = dma_buf_get(message_fd);
	if (IS_ERR(message)) {
		ret = PTR_ERR(message);
		goto put_work;
	}
	if (work != owner->work.buffer || message != owner->message.buffer ||
	    job->width != owner->width || job->height != owner->height ||
	    plane_matches(owner, raw, &job->raw) || plane_matches(owner, pdaf, &job->pdaf) ||
	    job->sv_id != owner->capture->resources->sv_id ||
	    job->sequence >> 24 != owner->ccd.session ||
	    mt6878_camsv_overlap(&owner->work.range, &job->raw) ||
	    mt6878_camsv_overlap(&owner->work.range, &job->pdaf) ||
	    mt6878_camsv_overlap(&owner->message.range, &job->raw) ||
	    mt6878_camsv_overlap(&owner->message.range, &job->pdaf)) {
		ret = -EXDEV;
		goto put_both;
	}
	ret = fill_message(owner, job);
	if (ret) {
		if (!owner->first_error)
			owner->first_error = ret;
		goto put_both;
	}
	params.workbuf.iova = owner->work.range.dma;
	params.workbuf.size = owner->work.range.size;
	params.workbuf.ccd_fd = work_fd;
	params.msg_buf.size = owner->message.range.size;
	params.msg_buf.ccd_fd = message_fd;
	/* Queue publication pins both mappings even on an ambiguous send failure. */
	owner->published = true;
	owner->job = *job;
	ret = mt6878_camera_ccd_create(&owner->ccd, &params);
	if (!ret)
		ret = mt6878_camera_ccd_config(&owner->ccd, config);
	if (ret && !owner->first_error)
		owner->first_error = ret;
put_both:
	dma_buf_put(message);
put_work:
	dma_buf_put(work);
out:
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_pipeline_compose(struct mt6878_pipeline_owner *owner,
	unsigned int timeout_ms, struct mt6878_camsv_buffer *cq)
{
	struct mt6878_camera_reply gate = { 0 };
	struct mt6878_camsv_buffer result;
	unsigned char reply[75];
	int ret = owner_task(owner);

	if (ret || !cq)
		return ret ? ret : -EINVAL;
	mutex_lock(&owner->lock);
	if (!owner->published || owner->callbacks_detached || READ_ONCE(owner->callback_closed) ||
	    owner->first_error) {
		ret = owner->first_error ? owner->first_error : -ENOTCONN;
		goto out;
	}
	ret = mt6878_camera_ccd_frame(&owner->ccd, owner->job.sequence, 0,
		sizeof(struct mtkcam_ipi_frame_param), timeout_ms, reply);
	if (ret)
		goto fail;
	gate.session = owner->ccd.session;
	gate.cookie = owner->job.sequence;
	ret = mt6878_camera_ack(&gate, reply, sizeof(reply), &owner->work.range, &result);
	if (ret)
		goto fail;
	/* Restricted recipe result: END included, value tail remains mapped. */
	if (result.dma != owner->work.range.dma ||
	    result.size != MT6878_CAMSV_RECIPE_WRITES * 12 + 12) {
		ret = -EPROTO;
		goto fail;
	}
	*cq = result;
	ret = 0; /* Transport composition only: not a CAMSV submit or capture. */
	goto out;
fail:
	if (!owner->first_error)
		owner->first_error = ret;
out:
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_pipeline_rx(struct rpmsg_device *client, void *data, int length, void *priv, u32 src)
{
	struct mt6878_pipeline_owner *owner = priv;
	unsigned long flags;
	int ret;

	if (!owner)
		return -EINVAL;
	spin_lock_irqsave(&owner->callback_lock, flags);
	if (owner->callback_closed || owner->callback_users == UINT_MAX) {
		spin_unlock_irqrestore(&owner->callback_lock, flags);
		return -ESHUTDOWN;
	}
	owner->callback_users++;
	spin_unlock_irqrestore(&owner->callback_lock, flags);
	ret = mt6878_camera_ccd_rx(client, data, length, &owner->ccd, src);
	spin_lock_irqsave(&owner->callback_lock, flags);
	owner->callback_users--;
	spin_unlock_irqrestore(&owner->callback_lock, flags);
	return ret;
}

int mt6878_pipeline_close_callback_gate(struct mt6878_pipeline_owner *owner)
{
	unsigned long flags;
	int ret;

	if (!owner)
		return -EINVAL;
	spin_lock_irqsave(&owner->callback_lock, flags);
	owner->callback_closed = true;
	ret = owner->callback_users ? -EBUSY : 0;
	spin_unlock_irqrestore(&owner->callback_lock, flags);
	return ret;
}

int mt6878_pipeline_detach_callbacks(struct mt6878_pipeline_owner *owner)
{
	unsigned long flags;
	int ret = owner_task(owner);

	if (ret)
		return ret;
	if (!mutex_trylock(&owner->lock))
		return -EBUSY;
	if (!owner->endpoint || owner->callbacks_detached) {
		ret = -EINVAL;
		goto out;
	}
	/* No wait behind an exchange. The callback gate covers both locked worker
	 * WRITE and vendor's unlocked mtk_rpmsg_ipi_handler, without nulling ept->cb.
	 */
	if (!mutex_trylock(&owner->ccd.lock)) {
		ret = -EBUSY;
		goto out;
	}
	if (owner->endpoint->cb != mt6878_pipeline_rx || owner->endpoint->priv != owner)
		ret = -ESTALE;
	else
		ret = mt6878_pipeline_close_callback_gate(owner);
	if (!ret) {
		spin_lock_irqsave(&owner->ccd.reply_lock, flags);
		owner->ccd.gate.closed = 1;
		owner->ccd.endpoint = NULL;
		spin_unlock_irqrestore(&owner->ccd.reply_lock, flags);
		owner->callbacks_detached = true;
		ret = 0;
	}
	mutex_unlock(&owner->ccd.lock);
out:
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_pipeline_release(struct mt6878_pipeline_owner *owner)
{
	int ret = owner_task(owner);

	if (ret)
		return ret;
	mutex_lock(&owner->lock);
	/* Callback exclusion is not READ quiescence. No API currently proves bus
	 * removal/worker exit, so published or endpoint-owned mappings stay pinned.
	 */
	if (owner->endpoint || owner->published || owner->work.cpu_active || owner->message.cpu_active ||
	    (owner->capture && owner->capture->pair && owner->capture->pair->tx.hw_attempted)) {
		ret = -EBUSY;
		goto out;
	}
	mt6878_pipeline_unmap(&owner->message);
	mt6878_pipeline_unmap(&owner->work);
	put_device(owner->dma_owner);
	owner->dma_owner = NULL;
	put_task_struct(owner->consumer);
	owner->consumer = NULL;
out:
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_pipeline_start(struct mt6878_pipeline_owner *owner)
{
	/* Frozen graph has no safe stream provider, TSREC/VC owner or DONE ACK.
	 * Do not start the IMX882 first or turn ownership flags into permission.
	 */
	return owner ? -EOPNOTSUPP : -EINVAL;
}
