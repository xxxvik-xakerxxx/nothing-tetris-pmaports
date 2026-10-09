/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <linux/ioctl.h>
#define __packed __attribute__((packed))
#include "mt6878-camera-ccd-composer-session.h"

static const struct mt6878_camsv_recipe_resources resources = {
	0x1a100000, 0x1a110000, 0x1000, 0x1000, 0
}; /* Synthetic source-known aperture, not handset addresses. */

static void setup(struct mt6878_camsv_job *job, struct mtkcam_ipi_config_param *config,
	unsigned int width, unsigned int height, unsigned int stride)
{
	unsigned int i, tag;
	struct mtkcam_ipi_sv_input_param *input;
	const struct mt6878_camsv_dma_layout *layout;

	memset(job, 0, sizeof(*job));
	memset(config, 0, sizeof(*config));
	job->width = width;
	job->height = height;
	job->sequence = 0x03000001;
	job->raw_tag = 0;
	job->pdaf_tag = 1;
	job->group_tags[0] = 3;
	job->raw_layout = (struct mt6878_camsv_dma_layout){
		SV_DMA_FMT_BAYER10_MIPI, width, height, stride, stride * height, 0 };
	job->pdaf_layout = (struct mt6878_camsv_dma_layout){
		SV_DMA_FMT_BAYER8, width, height / 4, width, width * (height / 4), 0 };
	/* These explicit layouts exercise owner contracts, not detected PDAF packing. */
	job->raw = (struct mt6878_camsv_buffer){ 0x100000000ULL, stride * height, 1 };
	job->pdaf = (struct mt6878_camsv_buffer){ 0x200000000ULL, width * (height / 4), 1 };
	for (i = 0; i < 2; i++) {
		tag = i ? job->pdaf_tag : job->raw_tag;
		layout = i ? &job->pdaf_layout : &job->raw_layout;
		input = &config->sv_input[0][tag];
		input->pipe_id = MTKCAM_SUBDEV_CAMSV_START;
		input->tag_id = tag;
		input->tag_order = 3;
		input->is_first_frame = 1;
		input->input.fmt = layout->format;
		input->input.in_crop.s.w = layout->width;
		input->input.in_crop.s.h = layout->height;
	}
}

static void recipe_mode(unsigned int width, unsigned int height, unsigned int stride)
{
	struct mt6878_camsv_job job;
	struct mtkcam_ipi_config_param config;
	struct mt6878_ccd_cq cq;
	unsigned char data[1024], before[1024];
	unsigned int length, tail, i, command, reg, pointer;

	setup(&job, &config, width, height, stride);
	assert(!mt6878_camsv_recipe_inputs(&job, &config, &resources));
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0x300000000ULL,
		resources.central, 0x11000));
	assert(!mt6878_camsv_recipe(&cq, &job, &config, &resources, 3, &length, &tail));
	assert(length == 720 && tail == 788);
	for (i = 0; i < 59; i++) {
		command = mt6878_camera_le32(data + i * 12);
		reg = 0x1a000000 | (command & 0xffff) | ((command >> 27) << 16);
		pointer = mt6878_camera_le32(data + i * 12 + 4);
		assert(pointer >= tail && pointer <= 1020);
		assert(mt6878_camera_le32(data + i * 12 + 8) == 3);
		if (reg == resources.dma + 0x210)
			assert(mt6878_camera_le32(data + pointer) == (stride << 16 | 0x10));
		if (reg == resources.dma + 0x204)
			assert(mt6878_camera_le32(data + pointer) == 1);
		if (reg == resources.dma + 0x244)
			assert(mt6878_camera_le32(data + pointer) == 2);
		if (reg == resources.central + 0x554)
			assert(mt6878_camera_le32(data + pointer) == 8);
		/* No guessed status ACK: enable offsets allowed, status writes forbidden. */
		assert(reg != resources.central + 0x348 && reg != resources.central + 0x350);
	}
	assert(mt6878_camera_le32(data + 708) == MT6878_CQ_END);
	memset(data, 0x55, sizeof(data));
	memcpy(before, data, sizeof(data));
	assert(!mt6878_ccd_cq_init(&cq, data, 952, 0x300000000ULL, resources.central, 0x11000));
	assert(mt6878_camsv_recipe(&cq, &job, &config, &resources, 3, &length, &tail) == -ENOSPC);
	assert(!memcmp(data, before, sizeof(data)));
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0x300000000ULL, resources.central, 0x11000));
	config.sv_input[0][0].is_two_smi_out = 1;
	assert(mt6878_camsv_recipe(&cq, &job, &config, &resources, 3, &length, &tail) == -EOPNOTSUPP);
	assert(!memcmp(data, before, sizeof(data)));
	config.sv_input[0][0].is_two_smi_out = 0;
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0x300000000ULL, resources.central, 0x11000));
	job.raw_layout.pixel_mode_shift = 1;
	assert(mt6878_camsv_recipe(&cq, &job, &config, &resources, 3, &length, &tail) == -EOPNOTSUPP);
	assert(!memcmp(data, before, sizeof(data)));
	job.raw_layout.pixel_mode_shift = 0;
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0x300000000ULL, resources.central, 0x11000));
	job.raw_tag = 4;
	assert(mt6878_camsv_recipe(&cq, &job, &config, &resources, 3, &length, &tail) == -EINVAL);
	assert(!memcmp(data, before, sizeof(data)));
	job.raw_tag = 0;
	job.pdaf_layout.bytesperline--;
	assert(mt6878_camsv_recipe_inputs(&job, &config, &resources) == -ERANGE);
	job.pdaf_layout.bytesperline++;
	job.pdaf.size--;
	assert(mt6878_camsv_recipe_inputs(&job, &config, &resources) == -ERANGE);
}

static void session_call(void)
{
	struct mt6878_ccd_composer_session session;
	struct mt6878_ccd_composer_session fault;
	struct mt6878_camsv_job job;
	struct mtkcam_ipi_config_param config;
	struct mtkcam_ipi_session_param mappings = { 0 };
	struct ccd_worker_item request = { .src = 4, .id = 4 }, reply;
	struct mtkcam_ipi_img_output outputs[2] = { 0 };
	struct mtkcam_ipi_frame_param *frame = calloc(1, sizeof(*frame));
	struct mtkcam_ipi_frame_param *scratch = calloc(1, sizeof(*scratch));
	union {
		struct mt6878_ccd_composer_session session;
		struct mtkcam_ipi_frame_param frame;
	} *alias = calloc(1, sizeof(*alias));
	unsigned char work[1024], before[1024];
	unsigned int i;
	const struct mt6878_camsv_dma_layout *layout;
	const struct mt6878_camsv_buffer *buffer;

	assert(frame && scratch && alias);
	setup(&job, &config, 4000, 3000, 5000);
	mappings.workbuf.iova = 0x300000000ULL;
	mappings.workbuf.ccd_fd = 10;
	mappings.workbuf.size = sizeof(work);
	mappings.msg_buf.ccd_fd = 11;
	mappings.msg_buf.size = sizeof(*frame);
	assert(mt6878_ccd_composer_prepare(&session, 3, &mappings, work,
		(unsigned char *)frame, frame, &resources, &job) == -EINVAL);
	assert(mt6878_ccd_composer_prepare(&alias->session, 3, &mappings, work,
		(unsigned char *)frame, &alias->frame, &resources, &job) == -EINVAL);
	assert(!mt6878_ccd_composer_prepare(&session, 3, &mappings, work,
		(unsigned char *)frame, scratch, &resources, &job));
	assert(!mt6878_ccd_composer_prepare(&session, 3, &session.mappings, work,
		(unsigned char *)frame, scratch, &session.resources, &session.job));
	assert(session.job.sequence == job.sequence && session.mappings.workbuf.ccd_fd == 10);
	request.sbuf[0] = 3;
	request.sbuf[5] = CAM_CMD_CREATE_SESSION;
	memcpy(request.sbuf + 6, &mappings, sizeof(mappings));
	request.len = 6 + sizeof(mappings);
	assert(mt6878_ccd_composer_dispatch(&session, &request, &request) == -EINVAL);
	assert(!session.created && request.sbuf[5] == CAM_CMD_CREATE_SESSION);
	assert(!mt6878_ccd_composer_dispatch(&session, &request, &reply));
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == -EINVAL);
	request.sbuf[5] = CAM_CMD_CONFIG;
	request.len = 6 + sizeof(config);
	memcpy(request.sbuf + 6, &config, sizeof(config));
	assert(!mt6878_ccd_composer_dispatch(&session, &request, &reply));
	for (i = 0; i < 2; i++) {
		layout = i ? &job.pdaf_layout : &job.raw_layout;
		buffer = i ? &job.pdaf : &job.raw;
		outputs[i].uid.pipe_id = MTKCAM_SUBDEV_CAMSV_START;
		outputs[i].uid.id = MTKCAM_IPI_CAMSV_MAIN_OUT;
		outputs[i].fmt.format = layout->format;
		outputs[i].fmt.s.w = layout->width;
		outputs[i].fmt.s.h = layout->height;
		outputs[i].fmt.stride[0] = layout->bytesperline;
		outputs[i].buf[0][0].iova = buffer->dma;
		outputs[i].buf[0][0].size = buffer->size;
	}
	assert(!mt6878_camera_frame(frame, &job, 0, sizeof(work), sizeof(work), &outputs[0], &outputs[1]));
	request.sbuf[5] = CAM_CMD_FRAME;
	mt6878_cq_put32(request.sbuf + 1, job.sequence);
	mt6878_cq_put32(request.sbuf + 6, 0);
	mt6878_cq_put32(request.sbuf + 10, sizeof(*frame));
	request.len = 14;
	memset(work, 0x55, sizeof(work));
	memcpy(before, work, sizeof(work));
	request.src = 3;
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == -ESTALE);
	assert(!memcmp(work, before, sizeof(work)) && !session.frame_started);
	request.src = 4;
	mt6878_cq_put32(request.sbuf + 1, job.sequence - 1);
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == -ESTALE);
	assert(!memcmp(work, before, sizeof(work)) && !session.frame_started);
	mt6878_cq_put32(request.sbuf + 1, job.sequence);
	/* Corrupt canonical unused payload: reject without touching the CQ. */
	fault = session;
	((unsigned char *)frame)[sizeof(*frame) - 1] = 1;
	assert(mt6878_ccd_composer_dispatch(&fault, &request, &reply) == 1);
	assert(mt6878_camera_le32(reply.sbuf + 7) == (unsigned int)-EOPNOTSUPP);
	assert(!memcmp(work, before, sizeof(work)) && fault.frame_started);
	((unsigned char *)frame)[sizeof(*frame) - 1] = 0;
	/* The failed session preserves its first error, never retries composition. */
	assert(mt6878_ccd_composer_dispatch(&fault, &request, &reply) == 1);
	assert(mt6878_camera_le32(reply.sbuf + 7) == (unsigned int)-EOPNOTSUPP);
	assert(!memcmp(work, before, sizeof(work)));
	fault = session;
	mt6878_cq_put32((unsigned char *)frame, 4);
	assert(mt6878_ccd_composer_dispatch(&fault, &request, &reply) == 1);
	assert(mt6878_camera_le32(reply.sbuf + 7) == (unsigned int)-ERANGE);
	assert(!memcmp(work, before, sizeof(work)));
	mt6878_cq_put32((unsigned char *)frame, 0);
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == 1);
	assert(reply.len == 75 && reply.sbuf[6] == CAM_CMD_FRAME);
	assert(!mt6878_camera_le32(reply.sbuf + 7));
	assert(mt6878_camera_le32(reply.sbuf + 63) == 720);
	memcpy(before, work, sizeof(work));
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == 1);
	assert(mt6878_camera_le32(reply.sbuf + 7) == (unsigned int)-EINVAL);
	assert(!memcmp(work, before, sizeof(work)));
	mt6878_cq_put32(request.sbuf + 1, 0);
	request.sbuf[5] = CAM_CMD_DESTROY_SESSION;
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == -EBUSY);
	request.sbuf[5] = CAM_CMD_FLUSH;
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == 1);
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == -EALREADY);
	request.sbuf[5] = CAM_CMD_DESTROY_SESSION;
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == 1);
	assert(mt6878_ccd_composer_dispatch(&session, &request, &reply) == -ESTALE);
	free(alias);
	free(scratch);
	free(frame);
}

int main(void)
{
	recipe_mode(4000, 3000, 5000);
	recipe_mode(4096, 2304, 5120);
	recipe_mode(4000, 3000, 5120);
	recipe_mode(4096, 2304, 5136);
	session_call();
	puts("CAMSV linear recipe and actual CCD session envelopes PASS");
	return 0;
}
