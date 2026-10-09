/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_COMPOSER_H
#define MT6878_CAMERA_COMPOSER_H

#ifdef __KERNEL__
#include <linux/string.h>
#else
#include <string.h>
#endif
#include "mt6878-camera-ipi-abi.h"
#include "mt6878-camsv-capture.h"

/* The camera CCD composer, not sensor SCP, must own this workbuf mapping.
 * One outstanding frame per state; reset only after transport drain and DMA
 * quiescence. Serialized by the capture owner. No firmware-ready surrogate.
 */
struct mt6878_camera_reply {
	unsigned int session, cookie, accepted;
	int first_error;
};

/* Pinned mtk_cam-job.h: [31:24] context, [23:0] frame sequence. */
static inline int mt6878_camera_cookie_valid(unsigned int session, unsigned int cookie)
{
	return session <= 3 && (cookie >> 24) == session;
}

static inline unsigned int mt6878_camera_le32(const unsigned char *p)
{
	return p[0] | ((unsigned int)p[1] << 8) |
		((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}

static inline int mt6878_camera_reply_header(const void *message, unsigned int length,
	unsigned int session, unsigned int cookie, unsigned int command)
{
	const unsigned char *p = message;
	int ret;

	if (!message)
		return -ENOTCONN;
	if (length < 75)
		return -EMSGSIZE;
	if (p[0] != session || mt6878_camera_le32(p + 1) != cookie)
		return -ESTALE;
	if (p[5] != CAM_CMD_ACK)
		return -EPROTO;
	/* CREATE/CONFIG ACKs may be delayed: never poison a later FRAME. */
	if (p[6] != command)
		return -ESTALE;
	ret = (int)mt6878_camera_le32(p + 7);
	return ret > 0 ? -EPROTO : ret;
}

/* Exact packed ACK prefix: cookie(5), command(1), ACK(69). No unaligned
 * struct dereferences, and no interpretation of the larger union tail.
 * camsv[0] is the logical composer slot even when physical CAMSV is SV1.
 */
static inline int mt6878_camera_ack(struct mt6878_camera_reply *state,
	const void *message, unsigned int length,
	const struct mt6878_camsv_buffer *workbuf,
	struct mt6878_camsv_buffer *cq)
{
	const unsigned char *p = message;
	unsigned int offset, size, i;
	int ret;

	if (!state || !message || !workbuf || !cq)
		return -EINVAL;
	if (state->first_error)
		return state->first_error;
	if (state->accepted)
		return -EALREADY;
	if (length < 75 || state->session > 255) {
		ret = -EMSGSIZE;
		goto fail;
	}
	if (p[0] != state->session || mt6878_camera_le32(p + 1) != state->cookie) {
		/* A foreign/stale reply must not poison the current frame. */
		return -ESTALE;
	}
	if (p[5] != CAM_CMD_ACK || p[6] != CAM_CMD_FRAME) {
		ret = -EPROTO;
		goto fail;
	}
	ret = (int)mt6878_camera_le32(p + 7);
	if (ret) {
		if (ret > 0)
			ret = -EPROTO;
		goto fail;
	}
	/* Reject RAW, MRAW and a second CAMSV result: this owner has one engine. */
	for (i = 0; i < 8; i++) {
		if (i == 6)
			continue;
		if (mt6878_camera_le32(p + 11 + i * 8) ||
		    mt6878_camera_le32(p + 15 + i * 8)) {
			ret = -EOPNOTSUPP;
			goto fail;
		}
	}
	offset = mt6878_camera_le32(p + 59);
	size = mt6878_camera_le32(p + 63);
	if (mt6878_camsv_range(workbuf, workbuf->size) || !size ||
	    size > 0xffff || offset > workbuf->size ||
	    size > workbuf->size - offset) {
		ret = -ERANGE;
		goto fail;
	}
	cq->dma = workbuf->dma + offset;
	cq->size = size;
	cq->mapped = 1;
	state->accepted = 1;
	return 0;
fail:
	state->first_error = ret;
	return ret;
}

/* Copy an already source-validated pair of output descriptions into the
 * actual full frame ABI. Format/stride/PDAF packing are the composer's
 * validated contract, not guessed here. fd fields remain the caller's CCD
 * handles; those handles require a real exporter/CCD transport owner.
 * Caller allocates the large frame outside the kernel stack.
 */
static inline int mt6878_camera_frame(struct mtkcam_ipi_frame_param *frame,
	const struct mt6878_camsv_job *job, unsigned int work_offset,
	unsigned int work_size, unsigned int shared_size,
	const struct mtkcam_ipi_img_output *raw,
	const struct mtkcam_ipi_img_output *pdaf)
{
	const struct mtkcam_ipi_img_output *outputs[2] = { raw, pdaf };
	const struct mt6878_camsv_dma_layout *layouts[2];
	const struct mt6878_camsv_buffer *buffers[2];
	unsigned int tags[2], i, s, plane, pipe;

	if (!frame || !job || !raw || !pdaf || job->sv_id > 1 ||
	    job->raw_tag > 7 || job->pdaf_tag > 7 || job->raw_tag == job->pdaf_tag ||
	    !work_size || work_offset > shared_size || work_size > shared_size - work_offset)
		return -EINVAL;
	layouts[0] = &job->raw_layout;
	layouts[1] = &job->pdaf_layout;
	if (!((job->width == 4000 && job->height == 3000) ||
	      (job->width == 4096 && job->height == 2304)) ||
	    layouts[0]->width != job->width || layouts[0]->height != job->height ||
	    (layouts[0]->format != MTKCAM_IPI_IMG_FMT_BAYER10 &&
	     layouts[0]->format != MTKCAM_IPI_IMG_FMT_BAYER10_MIPI))
		return -EOPNOTSUPP;
	buffers[0] = &job->raw;
	buffers[1] = &job->pdaf;
	tags[0] = job->raw_tag;
	tags[1] = job->pdaf_tag;
	pipe = job->sv_id + MTKCAM_SUBDEV_CAMSV_START;
	for (i = 0; i < 2; i++) {
		const struct mtkcam_ipi_img_output *out = outputs[i];

		if (mt6878_camsv_layout_validate(layouts[i], buffers[i]->size) ||
		    out->fmt.format != layouts[i]->format ||
		    out->fmt.s.w != layouts[i]->width || out->fmt.s.h != layouts[i]->height ||
		    out->fmt.stride[0] != layouts[i]->bytesperline ||
		    out->uid.pipe_id != pipe || out->uid.id != MTKCAM_IPI_CAMSV_MAIN_OUT ||
		    out->buf[0][0].iova != buffers[i]->dma ||
		    out->buf[0][0].size != buffers[i]->size ||
		    mt6878_camsv_range(buffers[i], buffers[i]->size) ||
		    !out->fmt.s.w || !out->fmt.s.h || !out->fmt.stride[0])
			return -EINVAL;
		for (plane = 1; plane < CAM_MAX_PLANENUM; plane++)
			if (out->fmt.stride[plane])
				return -EOPNOTSUPP;
		for (s = 0; s < CAM_MAX_SUBSAMPLE; s++)
			for (plane = 0; plane < CAM_MAX_PLANENUM; plane++) {
				struct mtkcam_ipi_buffer zero = { 0 };

				if ((s || plane) &&
				    memcmp(&out->buf[s][plane], &zero, sizeof(zero)))
					return -EOPNOTSUPP;
			}
	}
	/* Inputs must not alias frame: memset would destroy them. */
	if ((unsigned long)raw < (unsigned long)frame + sizeof(*frame) &&
	    (unsigned long)frame < (unsigned long)raw + sizeof(*raw))
		return -EINVAL;
	if ((unsigned long)pdaf < (unsigned long)frame + sizeof(*frame) &&
	    (unsigned long)frame < (unsigned long)pdaf + sizeof(*pdaf))
		return -EINVAL;
	memset(frame, 0, sizeof(*frame));
	frame->cur_workbuf_offset = work_offset;
	frame->cur_workbuf_size = work_size;
	for (i = 0; i < 2; i++) {
		struct mtkcam_ipi_camsv_frame_param *sv = &frame->camsv_param[0][tags[i]];

		sv->pipe_id = pipe;
		sv->tag_id = tags[i];
		sv->hardware_scenario = 0;
		memcpy(&sv->camsv_img_outputs[0], outputs[i], sizeof(*raw));
	}
	return 0;
}

#endif
