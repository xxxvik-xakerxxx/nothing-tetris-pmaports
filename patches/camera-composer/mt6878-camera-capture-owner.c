// SPDX-License-Identifier: GPL-2.0-only
#include <linux/build_bug.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/stddef.h>
#include "mt6878-camera-capture-owner.h"
#include "mt6878-camera-irq-registers.h"

static_assert(sizeof(struct mtkcam_ipi_session_cookie) == 5);
static_assert(sizeof(struct mtkcam_ipi_ack_info) == 69);
static_assert(offsetof(struct mtkcam_ipi_event, ack_data) == 6);
static_assert(offsetof(struct mtkcam_ipi_frame_ack_result, camsv) == 48);
static_assert(sizeof(struct mtkcam_ipi_camsv_frame_param) == 2083);
static_assert(sizeof(struct mtkcam_ipi_frame_param) == 92291);
static_assert(offsetof(struct mtkcam_ipi_frame_param, camsv_param) == 25005);

int mt6878_camera_capture_ack(struct mt6878_camera_capture_owner *owner,
	const void *message, unsigned int length,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf)
{
	struct mt6878_camsv_job job;
	int ret;

	if (!owner || !owner->pair || !owner->backend || !owner->resources ||
	    !owner->allocator || !raw || !pdaf ||
	    owner->job.sv_id != owner->resources->sv_id)
		return -EINVAL;
	job = owner->job;
	if (!raw->vb2_buf.vb2_queue || !pdaf->vb2_buf.vb2_queue ||
	    raw->vb2_buf.vb2_queue->mem_ops != &vb2_dma_contig_memops ||
	    pdaf->vb2_buf.vb2_queue->mem_ops != &vb2_dma_contig_memops ||
	    raw->vb2_buf.num_planes != 1 || pdaf->vb2_buf.num_planes != 1 ||
	    !vb2_plane_cookie(&raw->vb2_buf, 0) || !vb2_plane_cookie(&pdaf->vb2_buf, 0) ||
	    vb2_dma_contig_plane_dma_addr(&raw->vb2_buf, 0) != job.raw.dma ||
	    vb2_dma_contig_plane_dma_addr(&pdaf->vb2_buf, 0) != job.pdaf.dma)
		return -EINVAL;
	if (mt6878_camsv_layout_validate(&job.raw_layout, job.raw.size) ||
	    mt6878_camsv_layout_validate(&job.pdaf_layout, job.pdaf.size) ||
	    vb2_plane_size(&raw->vb2_buf, 0) < job.raw_layout.sizeimage ||
	    vb2_plane_size(&pdaf->vb2_buf, 0) < job.pdaf_layout.sizeimage)
		return -ERANGE;
	ret = mt6878_camera_ack(&owner->reply, message, length, &owner->workbuf, &job.cq);
	if (ret)
		return ret;
	/* ACK is not proof of CQ contents or cache synchronization. Frozen 0117
	 * still verifies COMPOSER/ROUTE/IRQ/IOMMU before the first write.
	 */
	ret = mt6878_camsv_vb2_submit(owner->pair, raw, pdaf, owner->allocator,
		owner->resources->domain, owner->backend, &job);
	if (ret)
		owner->reply.first_error = ret;
	return ret;
}

int mt6878_camera_done_snapshot(struct mt6878_camera_capture_owner *owner,
	struct mt6878_camera_done_snapshot *snapshot)
{
	struct mt6878_camsv_resources *res;
	struct mt6878_camera_done_snapshot value;
	u32 tags, offset = CAMERA_FH_SPARE_TAG1;
	unsigned int i;
	int ret;

	if (!owner || !snapshot || !owner->resources || !owner->verify_irq_read)
		return -EINVAL;
	res = owner->resources;
	if (!res->banks[0] || !res->banks[3])
		return -EINVAL;
	ret = owner->verify_irq_read(owner);
	if (ret)
		return ret;
	/* Exact vendor DONE-handler read order. No write-clear is evidenced.
	 * Four reads, at most eight tag checks, no polls or waits in IRQ context.
	 */
	tags = readl_relaxed(res->banks[3] + CAMERA_FIRST_TAG);
	for (i = 0; i < 8; i++)
		if (tags & BIT(i)) {
			offset += CAMERA_FH_SPARE_SHIFT * i;
			break;
		}
	value.outer_sequence = readl_relaxed(res->banks[0] + offset);
	value.inner_sequence = readl_relaxed(res->banks[3] + offset);
	value.status = readl_relaxed(res->banks[0] + CAMERA_DONE_STATUS);
	value.timestamp_ns = ktime_get_boottime_ns();
	*snapshot = value;
	return 0;
}

int mt6878_camera_done_dispatch(struct mt6878_camera_capture_owner *owner,
	const struct mt6878_camera_done_snapshot *snapshot)
{
	if (!owner || !owner->pair || !snapshot)
		return -EINVAL;
	/* Only inner frame identity can release buffers. Outer may already refer
	 * to the next queued CQ. Partial groups are accumulated by 0117.
	 */
	return mt6878_camsv_vb2_done(owner->pair, snapshot->status,
		snapshot->inner_sequence, snapshot->timestamp_ns);
}
