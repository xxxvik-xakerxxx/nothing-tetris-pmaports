// SPDX-License-Identifier: GPL-2.0-only
/* Coherent CQ -> native vb2/control bridge. No firmware/session transport. */
#include <linux/dma-mapping.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/kernel.h>
#include <linux/lockdep.h>
#include <linux/slab.h>
#include "mt6878-camsv-direct.h"
#include "mt6878-camera-irq-registers.h"

#define DIRECT_CQ_BYTES ALIGN(MT6878_CAMSV_RECIPE_WRITES * 16U + 12U, 16U)

static int first_error(struct mt6878_camsv_direct *owner, int ret)
{
	if (ret && !owner->first_error)
		owner->first_error = ret;
	return owner->first_error;
}

static int verify(void *context, enum mt6878_camsv_owner stage,
	const struct mt6878_camsv_job *job)
{
	struct mt6878_camsv_direct *owner = context;
	const struct mt6878_camsv_job *prepared = &owner->job;

	if (stage != MT6878_SV_COMPOSER)
		return owner->hardware.verify(owner->hardware.context, stage, job);
	/* CQ VA is private, never exported to userspace/another writer. Encoder
	 * finish is concrete state from recipe generation, not an asserted ready bit.
	 * All other ownership stages still require the real hardware consumer.
	 */
	if (!owner->cq_cpu || owner->encoder.buffer != owner->cq_cpu ||
	    !owner->encoder.finished || owner->encoder.first_error ||
	    owner->encoder.head != owner->descriptor_bytes ||
	    owner->encoder.tail != owner->values_start ||
	    owner->encoder.iova != owner->cq_dma ||
	    owner->encoder.capacity != owner->cq_capacity ||
	    job->cq.dma != owner->cq_dma || job->cq.size != owner->descriptor_bytes ||
	    job->raw.dma != prepared->raw.dma || job->raw.size != prepared->raw.size ||
	    job->pdaf.dma != prepared->pdaf.dma || job->pdaf.size != prepared->pdaf.size ||
	    job->sequence != prepared->sequence ||
	    iommu_get_domain_for_dev(owner->dma_owner) != owner->resources.domain)
		return -ESTALE;
	return mt6878_camsv_recipe_inputs(job, &owner->config, &owner->recipe_resources);
}

static int read_reg(void *context, enum mt6878_camsv_region bank,
	unsigned int offset, unsigned int *value)
{
	struct mt6878_camsv_direct *owner = context;

	return owner->hardware.read(owner->hardware.context, bank, offset, value);
}

static int write_reg(void *context, enum mt6878_camsv_region bank,
	unsigned int offset, unsigned int value)
{
	struct mt6878_camsv_direct *owner = context;

	return owner->hardware.write(owner->hardware.context, bank, offset, value);
}

static int hardware_barrier(void *context)
{
	struct mt6878_camsv_direct *owner = context;

	return (owner->hardware.barrier)(owner->hardware.context);
}

static int delay_us(void *context, unsigned int us)
{
	struct mt6878_camsv_direct *owner = context;

	return owner->hardware.delay_us(owner->hardware.context, us);
}

static int smi_clamp(void *context, unsigned int common, unsigned int enable)
{
	struct mt6878_camsv_direct *owner = context;

	return owner->hardware.smi_clamp(owner->hardware.context, common, enable);
}

int mt6878_camsv_direct_init(struct mt6878_camsv_direct *owner,
	struct platform_device *pdev, struct device *port_owner,
	const struct mt6878_camsv_backend *hardware)
{
	struct resource *central, *dma;
	struct mt6878_camsv_buffer allocation;
	int ret;

	if (!owner || !pdev || !port_owner || !hardware || owner->cq_cpu || owner->cq_capacity ||
	    owner->consumer || !hardware->verify || !hardware->read || !hardware->write ||
	    !hardware->barrier || !hardware->delay_us || !hardware->smi_clamp)
		return -EINVAL;
	mutex_init(&owner->lock);
	ret = mt6878_camsv_get_resources(pdev, port_owner, &owner->resources);
	if (ret)
		return ret;
	central = platform_get_resource_byname(pdev, IORESOURCE_MEM, "base");
	dma = platform_get_resource_byname(pdev, IORESOURCE_MEM, "base_DMA");
	if (!central || !dma || upper_32_bits(central->start) || upper_32_bits(dma->start) ||
	    resource_size(central) != 0x1000 || resource_size(dma) != 0x1000 ||
	    dma->start != central->start + 0x10000)
		return -ERANGE;
	owner->recipe_resources = (struct mt6878_camsv_recipe_resources) {
		central->start, dma->start, resource_size(central), resource_size(dma),
		owner->resources.sv_id,
	};
	owner->cq_capacity = DIRECT_CQ_BYTES;
	owner->cq_cpu = dma_alloc_coherent(port_owner, owner->cq_capacity, &owner->cq_dma, GFP_KERNEL);
	if (!owner->cq_cpu)
		return -ENOMEM;
	allocation = (struct mt6878_camsv_buffer) { owner->cq_dma, owner->cq_capacity, 1 };
	ret = mt6878_camsv_range(&allocation, owner->cq_capacity);
	if (ret || (owner->cq_dma & 15)) {
		dma_free_coherent(port_owner, owner->cq_capacity, owner->cq_cpu, owner->cq_dma);
		owner->cq_cpu = NULL;
		return -ERANGE;
	}
	owner->consumer = get_device(&pdev->dev);
	owner->dma_owner = get_device(port_owner);
	owner->hardware = *hardware;
	owner->io = *hardware;
	owner->io.context = owner;
	owner->io.verify = verify;
	owner->io.read = read_reg;
	owner->io.write = write_reg;
	owner->io.barrier = hardware_barrier;
	owner->io.delay_us = delay_us;
	owner->io.smi_clamp = smi_clamp;
	return 0;
}

int mt6878_camsv_direct_queue_init(struct mt6878_camsv_direct *owner,
	struct vb2_queue *queue, const struct vb2_ops *ops,
	enum v4l2_buf_type type, unsigned int buffer_bytes)
{
	if (!owner || !owner->cq_cpu || !queue || !ops ||
	    buffer_bytes < sizeof(struct vb2_v4l2_buffer) ||
	    (type != V4L2_BUF_TYPE_VIDEO_CAPTURE && type != V4L2_BUF_TYPE_META_CAPTURE))
		return -EINVAL;
	queue->type = type;
	queue->io_modes = VB2_MMAP | VB2_DMABUF;
	queue->dev = owner->dma_owner;
	queue->lock = &owner->lock;
	queue->drv_priv = owner;
	queue->ops = ops;
	queue->mem_ops = &vb2_dma_contig_memops;
	queue->buf_struct_size = buffer_bytes;
	queue->timestamp_flags = V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC;
	return vb2_queue_init(queue);
}

static int buffer_dma(struct mt6878_camsv_direct *owner, struct vb2_v4l2_buffer *buffer,
	enum v4l2_buf_type type, struct mt6878_camsv_buffer *dma)
{
	struct vb2_buffer *vb;
	struct vb2_queue *queue;
	unsigned long size;

	if (!buffer)
		return -EINVAL;
	vb = &buffer->vb2_buf;
	queue = vb->vb2_queue;
	if (!queue || queue->lock != &owner->lock || queue->dev != owner->dma_owner ||
	    queue->type != type || queue->mem_ops != &vb2_dma_contig_memops ||
	    vb->state != VB2_BUF_STATE_ACTIVE || vb->num_planes != 1 ||
	    vb->planes[0].data_offset || !vb2_plane_cookie(vb, 0))
		return -EINVAL;
	size = vb2_plane_size(vb, 0);
	if (!size || size > U32_MAX)
		return -ERANGE;
	*dma = (struct mt6878_camsv_buffer) { vb2_dma_contig_plane_dma_addr(vb, 0), size, 1 };
	return 0;
}

int mt6878_camsv_direct_submit(struct mt6878_camsv_direct *owner,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	const struct mt6878_camsv_job *layout,
	const struct mtkcam_ipi_config_param *config)
{
	struct mt6878_camsv_buffer full_cq;
	int ret;

	if (!owner || !owner->cq_cpu || !layout || !config)
		return -EINVAL;
	lockdep_assert_held(&owner->lock);
	if (owner->first_error)
		return owner->first_error;
	if (owner->pair.tx.attempted || owner->encoder.finished || owner->pair.raw || owner->pair.pdaf)
		return -EALREADY;
	if (layout->sv_id != owner->resources.sv_id ||
	    iommu_get_domain_for_dev(owner->dma_owner) != owner->resources.domain)
		return first_error(owner, -ESTALE);
	owner->job = *layout;
	owner->config = *config;
	ret = buffer_dma(owner, raw, V4L2_BUF_TYPE_VIDEO_CAPTURE, &owner->job.raw);
	if (!ret)
		ret = buffer_dma(owner, pdaf, V4L2_BUF_TYPE_META_CAPTURE, &owner->job.pdaf);
	full_cq = (struct mt6878_camsv_buffer) { owner->cq_dma, owner->cq_capacity, 1 };
	if (!ret && (mt6878_camsv_overlap(&full_cq, &owner->job.raw) ||
	    mt6878_camsv_overlap(&full_cq, &owner->job.pdaf)))
		ret = -ERANGE;
	if (!ret)
		ret = mt6878_ccd_cq_init(&owner->encoder, owner->cq_cpu, owner->cq_capacity,
			owner->cq_dma, owner->recipe_resources.central,
			owner->recipe_resources.dma + owner->recipe_resources.dma_size -
			owner->recipe_resources.central);
	if (!ret)
		ret = mt6878_camsv_recipe(&owner->encoder, &owner->job, &owner->config,
			&owner->recipe_resources, owner->job.sequence >> 24,
			&owner->descriptor_bytes, &owner->values_start);
	if (ret)
		return first_error(owner, ret);
	owner->job.cq = (struct mt6878_camsv_buffer) { owner->cq_dma, owner->descriptor_bytes, 1 };
	/* Entire coherent allocation, including tail values, remains owned. Coherent
	 * does not remove the ordering requirement before hardware sees CQ START.
	 */
	dma_wmb();
	ret = mt6878_camsv_vb2_submit(&owner->pair, raw, pdaf, owner->dma_owner,
		owner->resources.domain, &owner->io, &owner->job);
	return ret ? first_error(owner, ret) : 0;
}

static void complete_pair(struct mt6878_camsv_direct *owner, enum vb2_buffer_state state,
	u64 timestamp)
{
	struct vb2_v4l2_buffer *raw = owner->pair.raw, *pdaf = owner->pair.pdaf;
	bool done = state == VB2_BUF_STATE_DONE;

	owner->pair.completed = 1;
	raw->sequence = pdaf->sequence = owner->job.sequence;
	raw->vb2_buf.timestamp = pdaf->vb2_buf.timestamp = timestamp;
	vb2_set_plane_payload(&raw->vb2_buf, 0, done ? owner->job.raw_layout.sizeimage : 0);
	vb2_set_plane_payload(&pdaf->vb2_buf, 0, done ? owner->job.pdaf_layout.sizeimage : 0);
	vb2_buffer_done(&raw->vb2_buf, state);
	vb2_buffer_done(&pdaf->vb2_buf, state);
	owner->pair.raw = NULL;
	owner->pair.pdaf = NULL;
}

int mt6878_camsv_direct_stop(struct mt6878_camsv_direct *owner)
{
	unsigned int tags;
	bool frame_done;
	int ret;

	if (!owner || !owner->cq_cpu)
		return -EINVAL;
	lockdep_assert_held(&owner->lock);
	if (!owner->pair.tx.hw_attempted)
		return owner->first_error;
	if (owner->pair.tx.quiesced)
		return owner->first_error;
	/* Do not consume the frozen one-shot reset transaction until the real
	 * consumer has actually stopped the route and drained IRQ outside lock.
	 */
	ret = owner->hardware.verify(owner->hardware.context, MT6878_SV_STOPPED, &owner->pair.tx.job);
	if (ret)
		return first_error(owner, ret);
	tags = BIT(owner->job.raw_tag) | BIT(owner->job.pdaf_tag);
	frame_done = owner->completion_observed && owner->pair.tx.complete_tags == tags;
	ret = mt6878_camsv_stop(&owner->io, &owner->pair.tx);
	if (owner->pair.tx.quiesced && !owner->pair.completed && owner->pair.raw && owner->pair.pdaf) {
		if (!ret && !owner->first_error && frame_done)
			complete_pair(owner, VB2_BUF_STATE_DONE, owner->completion_timestamp);
		else
			complete_pair(owner, VB2_BUF_STATE_ERROR,
				owner->completion_observed ? owner->completion_timestamp : ktime_get_ns());
	}
	return ret ? first_error(owner, ret) : owner->first_error;
}

int mt6878_camsv_direct_done(struct mt6878_camsv_direct *owner)
{
	unsigned int tags, inner_sequence, status, offset = CAMERA_FH_SPARE_TAG1, i;
	u64 timestamp;
	int ret;

	if (!owner || !owner->cq_cpu)
		return -EINVAL;
	lockdep_assert_held(&owner->lock);
	if (owner->first_error)
		return owner->first_error; /* Never reread MMIO after the first causal failure. */
	if (owner->completion_observed)
		return -EALREADY;
	if (!owner->pair.tx.submitted || !owner->pair.raw || !owner->pair.pdaf || owner->pair.completed)
		return -EINVAL;
	ret = owner->hardware.verify(owner->hardware.context, MT6878_SV_RESOURCES, &owner->job);
	if (!ret)
		ret = owner->hardware.verify(owner->hardware.context, MT6878_SV_IRQ, &owner->job);
	if (ret)
		return first_error(owner, ret);
	/* Pinned DONE-handler read order, no inferred W1C acknowledgment. */
	tags = readl_relaxed(owner->resources.banks[3] + CAMERA_FIRST_TAG);
	for (i = 0; i < 8; i++)
		if (tags & BIT(i)) {
			offset += CAMERA_FH_SPARE_SHIFT * i;
			break;
		}
	readl_relaxed(owner->resources.banks[0] + offset); /* Outer may refer to a subsequent frame. */
	inner_sequence = readl_relaxed(owner->resources.banks[3] + offset);
	status = readl_relaxed(owner->resources.banks[0] + CAMERA_DONE_STATUS);
	timestamp = ktime_get_ns();
	ret = mt6878_camsv_done(&owner->pair.tx, status, inner_sequence);
	if (ret != 1)
		return ret;
	/* Full completion is recorded, but DMA remains owned until native consumer
	 * stops sensor/route and IRQ, then stop proves reset completion.
	 */
	owner->completion_timestamp = timestamp;
	owner->completion_observed = true;
	return 1;
}

int mt6878_camsv_direct_release(struct mt6878_camsv_direct *owner)
{
	if (!owner)
		return -EINVAL;
	lockdep_assert_held(&owner->lock);
	if (owner->pair.tx.hw_attempted && !owner->pair.tx.quiesced)
		return -EBUSY;
	if (owner->cq_cpu) {
		dma_free_coherent(owner->dma_owner, owner->cq_capacity, owner->cq_cpu, owner->cq_dma);
		owner->cq_cpu = NULL;
	}
	put_device(owner->dma_owner);
	put_device(owner->consumer);
	owner->dma_owner = NULL;
	owner->consumer = NULL;
	return 0;
}
