/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMSV_CAPTURE_H
#define MT6878_CAMSV_CAPTURE_H

#ifdef __KERNEL__
#include <linux/errno.h>
#else
#include <errno.h>
#endif

/* isp7sp mtk_cam-sv.c/apply_camsv_cq, sv_reset and IRQ done groups;
 * Nothing modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835.
 * Resource/DMA aperture: device ee2be53cb75670b548948636a0db1d1ff112bf12.
 * The firmware CQ composer is NOT implemented here. Never construct a CQ
 * by guessing WDMA stride/format registers from debug-only definitions.
 */
enum mt6878_camsv_region { MT6878_SV_CENTRAL, MT6878_SV_DMA, MT6878_SV_CQ, MT6878_SV_SENINF };
enum mt6878_camsv_owner {
	MT6878_SV_RESOURCES, MT6878_SV_IOMMU, MT6878_SV_ROUTE,
	MT6878_SV_IRQ, MT6878_SV_COMPOSER, MT6878_SV_STOPPED
};

struct mt6878_camsv_buffer {
	unsigned long long dma;
	unsigned int size, mapped;
};

struct mt6878_camsv_dma_layout {
	unsigned int format, width, height, bytesperline, sizeimage, pixel_mode_shift;
};

#include "mt6878-camsv-registers.h"

/* Output DMA layout, NOT CSI packet layout. Exact restricted vendor
 * mtk_cam_dmao_xsize / mtk_cam_dma_bus_size formula. The composer owner
 * must prove the selected format/geometry/stride against its emitted CQ.
 */
static inline int mt6878_camsv_layout_validate(const struct mt6878_camsv_dma_layout *l,
	unsigned int capacity)
{
	unsigned int bits, bus, row;

	if (!l || !l->width || !l->height || l->width > 65535 || l->height > 65535 ||
	    l->pixel_mode_shift > 4)
		return -EINVAL;
	if (l->format == SV_DMA_FMT_BAYER8)
		bits = 8;
	else if (l->format == SV_DMA_FMT_BAYER10 || l->format == SV_DMA_FMT_BAYER10_MIPI)
		bits = 10;
	else
		return -EOPNOTSUPP;
	bus = (16U << l->pixel_mode_shift) / 8;
	row = (l->width * bits + 7) / 8;
	row = (row + bus - 1) / bus * bus;
	if (l->bytesperline < row || l->bytesperline > 65535 ||
	    l->bytesperline % bus || l->sizeimage != l->bytesperline * l->height ||
	    l->sizeimage > capacity)
		return -ERANGE;
	return 0;
}

struct mt6878_camsv_job {
	unsigned int sv_id, width, height, sequence;
	unsigned int raw_tag, pdaf_tag;
	unsigned int group_tags[4]; /* Composer-proven active_group_info. */
	struct mt6878_camsv_buffer raw, pdaf, cq;
	struct mt6878_camsv_dma_layout raw_layout, pdaf_layout;
};

struct mt6878_camsv_backend {
	/* No receiver MMIO during verification. Prove held CAM_MAIN/clocks,
	 * exclusive six-bank resource ownership and the exact live IOMMU domain
	 * for all three DMA mappings. ROUTE verifies CAMMUX tags and the frozen
	 * SENINF route; IRQ owns all four CAMSV lines and bounded acknowledgment.
	 * COMPOSER proves exact RAW10/PDAF output addresses/strides, tag groups,
	 * FH_SPARE sequence and CQ initialization, including DMA synchronization
	 * and no reuse of these mappings after their group completion.
	 * Unsupported => -EOPNOTSUPP.
	 * STOPPED proves sensor/CAMMUX/TG/VF stopped, IRQ synchronized, clocks held.
	 * A stub verifier is not a valid live implementation.
	 */
	int (*verify)(void *context, enum mt6878_camsv_owner owner,
		const struct mt6878_camsv_job *job);
	int (*read)(void *context, enum mt6878_camsv_region region,
		unsigned int offset, unsigned int *value);
	int (*write)(void *context, enum mt6878_camsv_region region,
		unsigned int offset, unsigned int value);
	int (*barrier)(void *context);
	int (*delay_us)(void *context, unsigned int us);
	/* MT6878 get_sv_smi_reset_setting requires common 31 clamp+lock.
	 * Callback must own that shared SMI interface, not reinterpret it as
	 * permission to touch unrelated larbs. Failure keeps all buffers pinned.
	 */
	int (*smi_clamp)(void *context, unsigned int common, unsigned int enable);
	void *context;
	unsigned long sizes[4];
};

struct mt6878_camsv_transaction {
	struct mt6878_camsv_job job;
	unsigned int attempted, submitted, complete_tags, off_attempted, quiesced;
	unsigned int hw_attempted;
	int first_error;
};

static inline int mt6878_camsv_error(struct mt6878_camsv_transaction *tx, int ret)
{
	if (ret && !tx->first_error)
		tx->first_error = ret;
	return tx->first_error;
}

static inline int mt6878_camsv_range(const struct mt6878_camsv_buffer *buffer,
	unsigned int required)
{
	/* Exact MT6878 DT dma-ranges / vendor DMA_BIT_MASK(34). Zero DMA is legal. */
	if (buffer->mapped != 1 || buffer->size < required || !required ||
	    buffer->dma >= (1ULL << 34) || buffer->size > (1ULL << 34) - buffer->dma)
		return -EINVAL;
	return 0;
}

static inline int mt6878_camsv_overlap(const struct mt6878_camsv_buffer *a,
	const struct mt6878_camsv_buffer *b)
{
	return a->dma < b->dma + b->size && b->dma < a->dma + a->size;
}

static inline int mt6878_camsv_validate(const struct mt6878_camsv_backend *io,
	const struct mt6878_camsv_job *job)
{
	unsigned int tags, seen = 0, i;

	if (!io || !job || !io->verify || !io->read || !io->write ||
	    !io->barrier || !io->delay_us || !io->smi_clamp ||
	    io->sizes[0] != 0x1000 || io->sizes[1] != 0x1000 ||
	    io->sizes[2] != 0x1000 || io->sizes[3] != 0x18000 ||
	    job->sv_id > 1 || job->raw_tag > 7 || job->pdaf_tag > 7 ||
	    job->raw_tag == job->pdaf_tag ||
	    !((job->width == 4000 && job->height == 3000) ||
	      (job->width == 4096 && job->height == 2304)))
		return -EINVAL;
	if (job->raw_layout.width != job->width || job->raw_layout.height != job->height ||
	    (job->raw_layout.format != SV_DMA_FMT_BAYER10 &&
	     job->raw_layout.format != SV_DMA_FMT_BAYER10_MIPI) ||
	    mt6878_camsv_layout_validate(&job->raw_layout, job->raw.size) ||
	    mt6878_camsv_layout_validate(&job->pdaf_layout, job->pdaf.size) ||
	    mt6878_camsv_range(&job->raw, job->raw_layout.sizeimage) ||
	    mt6878_camsv_range(&job->pdaf, job->pdaf_layout.sizeimage) ||
	    mt6878_camsv_range(&job->cq, job->cq.size) || job->cq.size > 0xffff ||
	    mt6878_camsv_overlap(&job->raw, &job->pdaf) ||
	    mt6878_camsv_overlap(&job->raw, &job->cq) ||
	    mt6878_camsv_overlap(&job->pdaf, &job->cq))
		return -EINVAL;
	tags = (1U << job->raw_tag) | (1U << job->pdaf_tag);
	for (i = 0; i < 4; i++) {
		if ((job->group_tags[i] & ~tags) || (job->group_tags[i] & seen))
			return -EINVAL;
		seen |= job->group_tags[i];
	}
	return seen == tags ? 0 : -EINVAL;
}

static inline int mt6878_camsv_write(const struct mt6878_camsv_backend *io,
	struct mt6878_camsv_transaction *tx, enum mt6878_camsv_region region,
	unsigned int offset, unsigned int value)
{
	int ret;

	if ((unsigned int)region > MT6878_SV_SENINF || io->sizes[region] < 4 ||
	    (offset & 3) || offset > io->sizes[region] - 4)
		return mt6878_camsv_error(tx, -EINVAL);
	ret = io->write(io->context, region, offset, value);
	return ret ? mt6878_camsv_error(tx, ret) : 0;
}

static inline int mt6878_camsv_update(const struct mt6878_camsv_backend *io,
	struct mt6878_camsv_transaction *tx, enum mt6878_camsv_region region,
	unsigned int offset, unsigned int mask, unsigned int value)
{
	unsigned int old;
	int ret;

	if ((unsigned int)region > MT6878_SV_SENINF || io->sizes[region] < 4 ||
	    (offset & 3) || offset > io->sizes[region] - 4 || (value & ~mask))
		return mt6878_camsv_error(tx, -EINVAL);
	ret = io->read(io->context, region, offset, &old);

	if (ret)
		return mt6878_camsv_error(tx, ret);
	return mt6878_camsv_write(io, tx, region, offset, (old & ~mask) | value);
}

static inline int mt6878_camsv_submit(const struct mt6878_camsv_backend *io,
	struct mt6878_camsv_transaction *tx, const struct mt6878_camsv_job *job)
{
	unsigned int owner, output, offset, dt;
	int ret;

	if (!tx)
		return -EINVAL;
	if (tx->first_error)
		return tx->first_error;
	if (tx->attempted || tx->off_attempted)
		return -EALREADY;
	ret = mt6878_camsv_validate(io, job);
	if (ret)
		return mt6878_camsv_error(tx, ret);
	tx->attempted = 1;
	tx->job = *job;
	job = &tx->job;
	for (owner = MT6878_SV_RESOURCES; owner <= MT6878_SV_COMPOSER; owner++) {
		ret = io->verify(io->context, owner, &tx->job);
		if (ret)
			return mt6878_camsv_error(tx, ret);
	}
	tx->hw_attempted = 1;
	/* Exact set_cammux_vc field order. Does NOT enable CAMMUX or its tag page. */
	for (output = 0; output < 2; output++) {
		unsigned int tag = output ? job->pdaf_tag : job->raw_tag;

		offset = 0x17000 + 0x40 * (job->sv_id * 8 + tag) + SV_CAMMUX_OPT;
		dt = output ? 0x30 : 0x2b;
		ret = mt6878_camsv_update(io, tx, MT6878_SV_SENINF, offset, SV_VC_MASK, 0);
		if (!ret)
			ret = mt6878_camsv_update(io, tx, MT6878_SV_SENINF, offset,
				SV_DT_MASK, dt << SV_DT_SHIFT);
		if (!ret)
			ret = mt6878_camsv_update(io, tx, MT6878_SV_SENINF, offset,
				SV_VC_EN_MASK, SV_VC_EN_MASK);
		if (!ret)
			ret = mt6878_camsv_update(io, tx, MT6878_SV_SENINF, offset,
				SV_DT_EN_MASK, SV_DT_EN_MASK);
		if (ret)
			return ret;
	}
	/* apply_camsv_cq descriptor size -> MSB -> LSB -> start -> barrier. */
	ret = mt6878_camsv_write(io, tx, MT6878_SV_CQ, SV_CQ_SIZE, job->cq.size);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CQ, SV_CQ_MSB, job->cq.dma >> 32);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CQ, SV_CQ_LSB, job->cq.dma);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CQ, SV_CQ_START, 1);
	if (!ret)
		ret = io->barrier(io->context);
	if (!ret)
		ret = mt6878_camsv_update(io, tx, MT6878_SV_CQ, SV_CQ_EN, 1U << 12, 1U << 12);
	if (ret)
		return mt6878_camsv_error(tx, ret);
	tx->submitted = 1;
	return 0;
}

/* Threaded IRQ owner passes the vendor DONE_STATUS plus inner FH_SPARE
 * sequence after its bounded read/ack. No guessed W1C write here. A group
 * completion completes its mapped tags, NOT every tag on any interrupt.
 */
static inline int mt6878_camsv_done(struct mt6878_camsv_transaction *tx,
	unsigned int done_status, unsigned int inner_sequence)
{
	unsigned int group, tags = 0;

	if (!tx || !tx->submitted || tx->off_attempted || tx->first_error)
		return -EINVAL;
	if (inner_sequence != tx->job.sequence)
		return -ESTALE;
	for (group = 0; group < 4; group++)
		if (done_status & (1U << (16 + group)))
			tags |= tx->job.group_tags[group];
	if (!tags)
		return 0;
	if ((tx->complete_tags & tags) == tags)
		return -EALREADY;
	tx->complete_tags |= tags;
	return tx->complete_tags == ((1U << tx->job.raw_tag) | (1U << tx->job.pdaf_tag));
}

static inline int mt6878_camsv_poll_idle(const struct mt6878_camsv_backend *io,
	struct mt6878_camsv_transaction *tx, enum mt6878_camsv_region region,
	unsigned int offset)
{
	unsigned int value, count;
	int ret;

	/* Exact vendor SW_RST_CTL idle bit=2, delay=1us, timeout=100000us. */
	for (count = 0; count < 100000; count++) {
		ret = io->read(io->context, region, offset, &value);
		if (ret)
			return mt6878_camsv_error(tx, ret);
		if (value & 2)
			return 0;
		ret = io->delay_us(io->context, 1);
		if (ret)
			return mt6878_camsv_error(tx, ret);
	}
	return mt6878_camsv_error(tx, -ETIMEDOUT);
}

static inline int mt6878_camsv_stop(const struct mt6878_camsv_backend *io,
	struct mt6878_camsv_transaction *tx)
{
	int ret;

	if (!tx || !tx->attempted || mt6878_camsv_validate(io, &tx->job))
		return -EINVAL;
	if (tx->off_attempted)
		return tx->first_error ? tx->first_error : -EALREADY;
	tx->off_attempted = 1;
	ret = io->verify(io->context, MT6878_SV_STOPPED, &tx->job);
	if (!ret)
		ret = io->smi_clamp(io->context, 31, 1);
	if (ret)
		return mt6878_camsv_error(tx, ret);
	ret = mt6878_camsv_write(io, tx, MT6878_SV_DMA, SV_DMA_RESET, 0);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_DMA, SV_DMA_RESET, 1);
	if (!ret)
		ret = io->barrier(io->context);
	if (!ret)
		ret = mt6878_camsv_poll_idle(io, tx, MT6878_SV_DMA, SV_DMA_RESET);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CENTRAL, SV_DCM_DIS, 0);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CENTRAL, SV_SW_CTL, 0);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CENTRAL, SV_SW_CTL, 1);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_DMA, SV_DMA_RESET, 0);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CENTRAL, SV_SW_CTL, 0);
	if (!ret)
		ret = io->barrier(io->context);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CQ, SV_CQ_RESET, 0);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CQ, SV_CQ_RESET, 1);
	if (!ret)
		ret = io->barrier(io->context);
	if (!ret)
		ret = mt6878_camsv_poll_idle(io, tx, MT6878_SV_CQ, SV_CQ_RESET);
	if (!ret)
		ret = mt6878_camsv_write(io, tx, MT6878_SV_CQ, SV_CQ_RESET, 0);
	if (!ret)
		ret = io->barrier(io->context);
	if (!ret)
		ret = mt6878_camsv_update(io, tx, MT6878_SV_CQ, SV_CQ_EN, 1U << 16, 1U << 16);
	if (!ret)
		ret = mt6878_camsv_update(io, tx, MT6878_SV_CQ, SV_CQ_SUB_EN, 1U << 16, 1U << 16);
	if (!ret)
		ret = mt6878_camsv_update(io, tx, MT6878_SV_CQ, SV_CQ_SUB_EN, 1U << 16, 0);
	if (!ret)
		ret = mt6878_camsv_update(io, tx, MT6878_SV_CQ, SV_CQ_EN, 1U << 16, 0);
	if (!ret)
		ret = io->barrier(io->context);
	if (!ret)
		ret = io->smi_clamp(io->context, 31, 0);
	if (ret)
		return mt6878_camsv_error(tx, ret);
	tx->quiesced = 1;
	tx->submitted = 0;
	return tx->first_error;
}

#endif
