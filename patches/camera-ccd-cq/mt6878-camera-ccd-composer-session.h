/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_CCD_COMPOSER_SESSION_H
#define MT6878_CAMERA_CCD_COMPOSER_SESSION_H

#include "mt6878-camera-composer.h"
#include "mt6878-camera-ccd-uapi.h"
#include "mt6878-camera-camsv-recipe.h"

/* Native counterpart of ipi_cam_handler: actual CCD worker envelopes in,
 * actual 75-byte ACKs out, CQ values/descriptors composed here. No callbacks
 * pretending an external service supplied the CQ. Serialized single session,
 * one frame. Mapping acquisition, cache sync and lifetime are owner's duties.
 * CREATE fd numbers MUST be valid in the registered CCD process, not the
 * sender's process; matching libccd 0x39860 calls mmap64 on those exact fds.
 */
struct mt6878_ccd_composer_session {
	unsigned int session, created, configured, frame_started, flushed, closed;
	int first_error;
	struct mtkcam_ipi_session_param mappings;
	unsigned char *work_va, *message_va;
	struct mtkcam_ipi_frame_param *scratch;
	struct mt6878_camsv_recipe_resources resources;
	struct mt6878_camsv_job job;
	struct mtkcam_ipi_config_param config;
};

static inline int mt6878_ccd_va_overlap(const void *a, unsigned int a_size,
	const void *b, unsigned int b_size)
{
	unsigned long x = (unsigned long)a, y = (unsigned long)b;

	return x <= y ? y - x < a_size : x - y < b_size;
}

static inline int mt6878_ccd_composer_prepare(struct mt6878_ccd_composer_session *s,
	unsigned int session, const struct mtkcam_ipi_session_param *mappings,
	unsigned char *work_va, unsigned char *message_va,
	struct mtkcam_ipi_frame_param *scratch,
	const struct mt6878_camsv_recipe_resources *resources,
	const struct mt6878_camsv_job *job)
{
	struct mt6878_camsv_buffer work;
	struct mtkcam_ipi_session_param owned_mappings;
	struct mt6878_camsv_recipe_resources owned_resources;
	struct mt6878_camsv_job owned_job;

	if (!s || session > 3 || !mappings || !work_va || !message_va || !scratch ||
	    !resources || !job || mappings->workbuf.ccd_fd > 0x7fffffff ||
	    mappings->msg_buf.ccd_fd > 0x7fffffff || mappings->msg_buf.iova ||
	    mappings->msg_buf.size < sizeof(*scratch) ||
	    mappings->workbuf.size < MT6878_CAMSV_RECIPE_WRITES * 16 + 12 ||
	    (job->sequence >> 24) != session)
		return -EINVAL;
	work.dma = mappings->workbuf.iova;
	work.size = mappings->workbuf.size;
	work.mapped = 1;
	if (mt6878_camsv_range(&work, work.size) || (work.dma & 15) ||
	    (work.size & 3) || mt6878_camsv_overlap(&work, &job->raw) ||
	    mt6878_camsv_overlap(&work, &job->pdaf))
		return -ERANGE;
	/* Scratch must never erase the incoming frame during canonical validation. */
	if (mt6878_ccd_va_overlap(work_va, work.size, message_va, mappings->msg_buf.size) ||
	    mt6878_ccd_va_overlap(scratch, sizeof(*scratch), work_va, work.size) ||
	    mt6878_ccd_va_overlap(scratch, sizeof(*scratch), message_va, mappings->msg_buf.size) ||
	    mt6878_ccd_va_overlap(s, sizeof(*s), scratch, sizeof(*scratch)) ||
	    mt6878_ccd_va_overlap(s, sizeof(*s), work_va, work.size) ||
	    mt6878_ccd_va_overlap(s, sizeof(*s), message_va, mappings->msg_buf.size))
		return -EINVAL;
	/* Inputs may be snapshots inside s; preserve them before clearing state. */
	owned_mappings = *mappings;
	owned_resources = *resources;
	owned_job = *job;
	memset(s, 0, sizeof(*s));
	s->session = session;
	s->mappings = owned_mappings;
	s->work_va = work_va;
	s->message_va = message_va;
	s->scratch = scratch;
	s->resources = owned_resources;
	s->job = owned_job;
	return 0;
}

static inline void mt6878_ccd_composer_ack(struct ccd_worker_item *reply,
	const struct ccd_worker_item *request, int result)
{
	memset(reply, 0, sizeof(*reply));
	reply->src = request->src;
	reply->id = request->id;
	reply->len = 75;
	memcpy(reply->sbuf, request->sbuf, 5);
	reply->sbuf[5] = CAM_CMD_ACK;
	reply->sbuf[6] = request->sbuf[5];
	mt6878_cq_put32(reply->sbuf + 7, (unsigned int)result);
}

static inline int mt6878_ccd_composer_frame(struct mt6878_ccd_composer_session *s,
	const struct ccd_worker_item *request, struct ccd_worker_item *reply)
{
	struct mtkcam_ipi_img_output output[2] = { 0 };
	const struct mt6878_camsv_dma_layout *layout;
	const struct mt6878_camsv_buffer *buffer;
	const unsigned char *frame;
	struct mt6878_ccd_cq cq;
	unsigned int offset, size, work_offset, work_size, length, tail, i;
	int ret;

	if (!s->configured || s->frame_started || request->len < 14)
		return -EINVAL;
	if (mt6878_camera_le32(request->sbuf + 1) != s->job.sequence)
		return -ESTALE;
	s->frame_started = 1; /* Consume before validation: failed FRAME never retries. */
	offset = mt6878_camera_le32(request->sbuf + 6);
	size = mt6878_camera_le32(request->sbuf + 10);
	if (size != sizeof(*s->scratch) || offset > s->mappings.msg_buf.size ||
	    size > s->mappings.msg_buf.size - offset)
		return -ERANGE;
	frame = s->message_va + offset;
	work_offset = mt6878_camera_le32(frame);
	work_size = mt6878_camera_le32(frame + 4);
	if (!work_size || (work_offset & 15) || (work_size & 3) ||
	    work_offset > s->mappings.workbuf.size ||
	    work_size > s->mappings.workbuf.size - work_offset)
		return -ERANGE;
	/* Match the entire incoming frame to the canonical frozen 0118 builder,
	 * including zero RAW/MRAW/unused tags/planes/subsamples. No ignored payload.
	 */
	for (i = 0; i < 2; i++) {
		layout = i ? &s->job.pdaf_layout : &s->job.raw_layout;
		buffer = i ? &s->job.pdaf : &s->job.raw;
		output[i].uid.pipe_id = s->job.sv_id + MTKCAM_SUBDEV_CAMSV_START;
		output[i].uid.id = MTKCAM_IPI_CAMSV_MAIN_OUT;
		output[i].fmt.format = layout->format;
		output[i].fmt.s.w = layout->width;
		output[i].fmt.s.h = layout->height;
		output[i].fmt.stride[0] = layout->bytesperline;
		output[i].buf[0][0].iova = buffer->dma;
		output[i].buf[0][0].size = buffer->size;
	}
	ret = mt6878_camera_frame(s->scratch, &s->job, work_offset, work_size,
		s->mappings.workbuf.size, &output[0], &output[1]);
	if (ret)
		return ret;
	if (memcmp(frame, s->scratch, sizeof(*s->scratch)))
		return -EOPNOTSUPP;
	ret = mt6878_ccd_cq_init(&cq, s->work_va + work_offset, work_size,
		s->mappings.workbuf.iova + work_offset, s->resources.central, 0x11000);
	if (ret)
		return ret;
	ret = mt6878_camsv_recipe(&cq, &s->job, &s->config, &s->resources,
		s->session, &length, &tail);
	if (ret)
		return ret;
	/* Actual camsv[0] ACK slot. Full value tail remains owned and mapped.
	 * Caller must synchronize the full CQ work slice before WORKER_WRITE ACK.
	 */
	mt6878_cq_put32(reply->sbuf + 59, work_offset);
	mt6878_cq_put32(reply->sbuf + 63, length);
	return 0;
}

/* Return 1 only for a real ACK to send; 0 for ordered CREATE/CONFIG (stock
 * sends no ACK), negative for rejected/foreign envelopes. FLUSH acknowledges
 * synchronous composition drain, NOT CAMSV DMA stop or buffer unmapping.
 */
static inline int mt6878_ccd_composer_dispatch(struct mt6878_ccd_composer_session *s,
	const struct ccd_worker_item *request, struct ccd_worker_item *reply)
{
	struct mtkcam_ipi_session_param mappings;
	unsigned int command;
	int ret;

	if (!s || !request || !reply || request->len < 6 || request->len > BUF_MAX_SIZE)
		return -EMSGSIZE;
	if (mt6878_ccd_va_overlap(request, sizeof(*request), reply, sizeof(*reply)) ||
	    mt6878_ccd_va_overlap(s, sizeof(*s), request, sizeof(*request)) ||
	    mt6878_ccd_va_overlap(s, sizeof(*s), reply, sizeof(*reply)))
		return -EINVAL;
	if (s->closed || request->src != s->session + CCD_IPI_ISP_MAIN ||
	    request->id != request->src || request->sbuf[0] != s->session)
		return -ESTALE;
	command = request->sbuf[5];
	memset(reply, 0, sizeof(*reply));
	if (command == CAM_CMD_CREATE_SESSION) {
		if (request->len < 6 + sizeof(mappings) || s->created)
			return -EINVAL;
		memcpy(&mappings, request->sbuf + 6, sizeof(mappings));
		if (memcmp(&mappings, &s->mappings, sizeof(mappings)))
			return -ESTALE;
		s->created = 1;
		return 0;
	}
	if (command == CAM_CMD_CONFIG) {
		if (s->first_error)
			return s->first_error;
		if (!s->created || s->configured || s->flushed ||
		    request->len < 6 + sizeof(s->config))
			return -EINVAL;
		memcpy(&s->config, request->sbuf + 6, sizeof(s->config));
		ret = mt6878_camsv_recipe_inputs(&s->job, &s->config, &s->resources);
		if (ret) {
			if (!s->first_error)
				s->first_error = ret;
			return ret;
		}
		s->configured = 1;
		return 0;
	}
	if (command != CAM_CMD_FRAME && command != CAM_CMD_FLUSH &&
	    command != CAM_CMD_DESTROY_SESSION)
		return -EOPNOTSUPP;
	if (!s->created)
		return -ENOTCONN;
	if (command != CAM_CMD_FRAME && mt6878_camera_le32(request->sbuf + 1))
		return -ESTALE;
	mt6878_ccd_composer_ack(reply, request, 0);
	if (command == CAM_CMD_FLUSH) {
		if (s->flushed)
			return -EALREADY;
		s->flushed = 1;
		return 1;
	}
	if (command == CAM_CMD_DESTROY_SESSION) {
		if (!s->flushed)
			return -EBUSY;
		s->closed = 1;
		return 1;
	}
	if (s->flushed)
		return -ESHUTDOWN;
	ret = s->first_error ? s->first_error : mt6878_ccd_composer_frame(s, request, reply);
	if (ret == -ESTALE)
		return ret;
	if (ret) {
		if (!s->first_error)
			s->first_error = ret;
		mt6878_ccd_composer_ack(reply, request, s->first_error);
	}
	return 1;
}

#endif
