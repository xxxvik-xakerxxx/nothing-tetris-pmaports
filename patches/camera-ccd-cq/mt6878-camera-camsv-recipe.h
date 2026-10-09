/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_CAMSV_RECIPE_H
#define MT6878_CAMERA_CAMSV_RECIPE_H

#include "mt6878-camera-ccd-cq.h"
#include "mt6878-camsv-capture.h"
#include "mt6878-camera-ipi-abi.h"

/* Matching B4.1 libccd camsys_sv_compose, linear first-frame branch. This
 * generates memory, never MMIO. Resource starts are supplied by the owner.
 * A source-valid recipe does not establish live power/IOMMU/IRQ ownership.
 */
struct mt6878_camsv_recipe_resources {
	unsigned int central, dma, central_size, dma_size;
	unsigned int sv_id;
};

struct mt6878_camsv_recipe_write {
	unsigned int address, value;
};

#define MT6878_CAMSV_RECIPE_WRITES 59U

static inline int mt6878_camsv_recipe_inputs(const struct mt6878_camsv_job *job,
	const struct mtkcam_ipi_config_param *config,
	const struct mt6878_camsv_recipe_resources *resources)
{
	const struct mtkcam_ipi_sv_input_param *input;
	const struct mt6878_camsv_dma_layout *layout;
	unsigned int slot, tag, active, mask;

	if (!job || !config || !resources || job->sv_id > 1 ||
	    job->raw_tag > 3 || job->pdaf_tag > 3 || job->raw_tag == job->pdaf_tag)
		return -EINVAL;
	if (resources->sv_id != job->sv_id || resources->central_size != 0x1000 ||
	    resources->dma_size != 0x1000 ||
	    resources->central < MT6878_CQ_REG_BASE || (resources->central & 0xfff) ||
	    resources->central > MT6878_CQ_REG_BASE + MT6878_CQ_REG_SIZE - 0x11000 ||
	    resources->dma != resources->central + 0x10000)
		return -ERANGE;
	/* No RAW engine, subsampling, special scenario, second SMI or frame reuse. */
	if (config->flags || config->input.subsample || config->sw_feature ||
	    config->exp_order || config->frame_order || config->vsync_order ||
	    config->w_cac_table.size || job->raw_layout.pixel_mode_shift ||
	    job->pdaf_layout.pixel_mode_shift)
		return -EOPNOTSUPP;
	if (config->n_maps > 6)
		return -EINVAL;
	for (slot = 0; slot < config->n_maps; slot++)
		if (config->maps[slot].pipe_id != job->sv_id + MTKCAM_SUBDEV_CAMSV_START)
			return -EOPNOTSUPP;
	if (!((job->width == 4000 && job->height == 3000) ||
	      (job->width == 4096 && job->height == 2304)) ||
	    job->raw_layout.width != job->width || job->raw_layout.height != job->height ||
	    (job->raw_layout.format != SV_DMA_FMT_BAYER10 &&
	     job->raw_layout.format != SV_DMA_FMT_BAYER10_MIPI) ||
	    mt6878_camsv_layout_validate(&job->raw_layout, job->raw.size) ||
	    mt6878_camsv_layout_validate(&job->pdaf_layout, job->pdaf.size) ||
	    mt6878_camsv_range(&job->raw, job->raw_layout.sizeimage) ||
	    mt6878_camsv_range(&job->pdaf, job->pdaf_layout.sizeimage) ||
	    mt6878_camsv_overlap(&job->raw, &job->pdaf))
		return -ERANGE;
	/* No PDAF RAW10 ratio. The exact owner-negotiated emitted DMA layout wins. */
	mask = (1U << job->raw_tag) | (1U << job->pdaf_tag);
	if (job->group_tags[0] != mask || job->group_tags[1] ||
	    job->group_tags[2] || job->group_tags[3])
		return -EOPNOTSUPP;
	for (slot = 0; slot < CAMSV_MAX_PIPE_USED; slot++) {
		for (tag = 0; tag < CAMSV_MAX_TAGS; tag++) {
			input = &config->sv_input[slot][tag];
			active = slot == 0 && (mask & (1U << tag));
			if (!active) {
				if (input->pipe_id >= MTKCAM_SUBDEV_CAMSV_START &&
				    input->pipe_id < MTKCAM_SUBDEV_CAMSV_END)
					return -EOPNOTSUPP;
				continue;
			}
			layout = tag == job->raw_tag ? &job->raw_layout : &job->pdaf_layout;
			if (input->pipe_id != job->sv_id + MTKCAM_SUBDEV_CAMSV_START ||
			    input->tag_id != tag || input->tag_order != 3 ||
			    input->is_first_frame != 1 || input->is_two_smi_out ||
			    input->is_last_order_meta_off || input->input.subsample ||
			    input->input.data_pattern || input->input.raw_pixel_id ||
			    input->input.fmt != layout->format ||
			    input->input.pixel_mode != layout->pixel_mode_shift ||
			    input->input.in_crop.p.x || input->input.in_crop.p.y ||
			    input->input.in_crop.s.w != layout->width ||
			    input->input.in_crop.s.h != layout->height)
				return -EOPNOTSUPP;
		}
	}
	for (slot = 0; slot < MRAW_MAX_PIPE_USED; slot++)
		if (config->mraw_input[slot].pipe_id >= MTKCAM_SUBDEV_MRAW_START &&
		    config->mraw_input[slot].pipe_id < MTKCAM_SUBDEV_MRAW_END)
			return -EOPNOTSUPP;
	return 0;
}

static inline void mt6878_camsv_recipe_add(struct mt6878_camsv_recipe_write *writes,
	unsigned int *count, unsigned int base, unsigned int offset, unsigned int value)
{
	writes[*count].address = base + offset;
	writes[*count].value = value;
	(*count)++;
}

/* Complete linear first-frame descriptor recipe, not sensor/PHY/IRQ startup.
 * The two buffers and full CQ mapping must belong to the same verified owner.
 * No preexisting CQ entries, publishing, ACK or cache sync before success.
 */
static inline int mt6878_camsv_recipe(struct mt6878_ccd_cq *cq,
	const struct mt6878_camsv_job *job, const struct mtkcam_ipi_config_param *config,
	const struct mt6878_camsv_recipe_resources *resources, unsigned int session,
	unsigned int *descriptor_bytes, unsigned int *values_start)
{
	struct mt6878_camsv_recipe_write writes[MT6878_CAMSV_RECIPE_WRITES];
	const struct mt6878_camsv_dma_layout *layout;
	const struct mt6878_camsv_buffer *buffer;
	unsigned int count = 0, tag, central, dma, shift, format, i, mask;
	unsigned int img = 0, errors = 1, sof = 0, first;
	struct mt6878_camsv_buffer work;
	int ret;

	if (!cq || !cq->buffer || !descriptor_bytes || !values_start)
		return -EINVAL;
	if (cq->first_error)
		return cq->first_error;
	if (cq->head || cq->tail != cq->capacity || cq->finished)
		return -EALREADY;
	ret = mt6878_camsv_recipe_inputs(job, config, resources);
	if (ret)
		return mt6878_cq_fail(cq, ret);
	if (session > 3 || (job->sequence >> 24) != session)
		return mt6878_cq_fail(cq, -ESTALE);
	work.dma = cq->iova;
	work.size = cq->capacity;
	work.mapped = 1;
	if (mt6878_camsv_overlap(&work, &job->raw) ||
	    mt6878_camsv_overlap(&work, &job->pdaf))
		return mt6878_cq_fail(cq, -ERANGE);
	central = resources->central;
	dma = resources->dma;
	mask = (1U << job->raw_tag) | (1U << job->pdaf_tag);
	first = mask & (~mask + 1);
	/* Same ascending tag order as the stock loop; no compressed/UFO branches. */
	for (tag = 0; tag < 8; tag++) {
		if (!(mask & (1U << tag)))
			continue;
		layout = tag == job->raw_tag ? &job->raw_layout : &job->pdaf_layout;
		buffer = tag == job->raw_tag ? &job->raw : &job->pdaf;
		format = layout->format == SV_DMA_FMT_BAYER10_MIPI ? 8 : layout->format;
		shift = tag * 0x40;
		mt6878_camsv_recipe_add(writes, &count, central, 0x548 + shift, layout->width << 16);
		mt6878_camsv_recipe_add(writes, &count, central, 0x54c + shift, layout->height << 16);
		mt6878_camsv_recipe_add(writes, &count, central, 0x554 + shift, format);
		mt6878_camsv_recipe_add(writes, &count, central, 0x55c + shift, 1);
		mt6878_camsv_recipe_add(writes, &count, central, 0x540 + shift, 0x8000);
		mt6878_camsv_recipe_add(writes, &count, dma, 0x210 + shift,
			(layout->bytesperline << 16) | 0x10);
		mt6878_camsv_recipe_add(writes, &count, dma, 0xa10 + shift, 0x10);
		mt6878_camsv_recipe_add(writes, &count, central, 0x554 + shift, format);
		mt6878_camsv_recipe_add(writes, &count, dma, 0x210 + shift,
			(layout->bytesperline << 16) | 0x10);
		mt6878_camsv_recipe_add(writes, &count, dma, 0x200 + shift, (unsigned int)buffer->dma);
		mt6878_camsv_recipe_add(writes, &count, dma, 0x204 + shift, (unsigned int)(buffer->dma >> 32));
		mt6878_camsv_recipe_add(writes, &count, dma, 0x218 + shift, 0);
		mt6878_camsv_recipe_add(writes, &count, dma, 0x21c + shift, 0);
		mt6878_camsv_recipe_add(writes, &count, dma, 0x220 + shift, 0);
		mt6878_camsv_recipe_add(writes, &count, dma, 0x224 + shift, 0);
		mt6878_camsv_recipe_add(writes, &count, central, 0x540 + shift, 0x8080);
		if (tag < 4)
			img |= 1U << tag;
		errors |= 0x700U << (tag * 3);
		sof |= 4U << (tag * 4);
	}
	mt6878_camsv_recipe_add(writes, &count, central, 0x140, 1);
	mt6878_camsv_recipe_add(writes, &count, central, 0x18c, 3);
	mt6878_camsv_recipe_add(writes, &count, central, 0x170, 0x20);
	mt6878_camsv_recipe_add(writes, &count, central, 0x144, 0);
	mt6878_camsv_recipe_add(writes, &count, central, 0x40, mask);
	mt6878_camsv_recipe_add(writes, &count, central, 0x44, img);
	mt6878_camsv_recipe_add(writes, &count, dma, 0xf30, img | (img << 8));
	mt6878_camsv_recipe_add(writes, &count, central, 0x344, 0xf0000);
	mt6878_camsv_recipe_add(writes, &count, central, 0x34c, errors);
	mt6878_camsv_recipe_add(writes, &count, central, 0x35c, sof);
	mt6878_camsv_recipe_add(writes, &count, central, 0x36c, 0x11111111);
	/* Normal hardware_scenario=0, exp_num=0: stock excludes special routing. */
	mt6878_camsv_recipe_add(writes, &count, central, 0x1d4, 0);
	mt6878_camsv_recipe_add(writes, &count, central, 0x1d8, 0);
	mt6878_camsv_recipe_add(writes, &count, central, 0x1b8, mask);
	mt6878_camsv_recipe_add(writes, &count, central, 0x1bc, 0);
	mt6878_camsv_recipe_add(writes, &count, central, 0x1c0, 0);
	mt6878_camsv_recipe_add(writes, &count, central, 0x1c4, 0);
	mt6878_camsv_recipe_add(writes, &count, central, 0x1c8, first);
	mt6878_camsv_recipe_add(writes, &count, central, 0x1cc, first);
	for (tag = 0; tag < 8; tag++)
		mt6878_camsv_recipe_add(writes, &count, central, 0x57c + tag * 0x40, job->sequence);
	if (count != MT6878_CAMSV_RECIPE_WRITES || cq->capacity < count * 16 + 12)
		return mt6878_cq_fail(cq, -ENOSPC);
	/* Validate every target before publishing any descriptor or value. */
	for (i = 0; i < count; i++)
		if (writes[i].address < cq->reg_base ||
		    writes[i].address - cq->reg_base >= cq->reg_size)
			return mt6878_cq_fail(cq, -ERANGE);
	for (i = 0; i < count; i++) {
		ret = mt6878_ccd_cq_values(cq, writes[i].address, &writes[i].value, 1);
		if (ret)
			return ret;
	}
	return mt6878_ccd_cq_finish(cq, descriptor_bytes, values_start);
}

#endif
