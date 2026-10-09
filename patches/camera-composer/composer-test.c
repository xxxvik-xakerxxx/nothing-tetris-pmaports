/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stddef.h>
#include <stdlib.h>
#include <linux/ioctl.h>
#define __packed __attribute__((packed))
#include "mt6878-camera-composer.h"
#include "mt6878-camera-ccd-uapi.h"

_Static_assert(sizeof(struct mtkcam_ipi_frame_param) == 92291, "complete frame ABI");
_Static_assert(offsetof(struct mtkcam_ipi_frame_param, camsv_param) == 25005, "CAMSV ABI offset");
_Static_assert(sizeof(struct mtkcam_ipi_camsv_frame_param) == 2083, "CAMSV slot ABI");
_Static_assert(offsetof(struct mtkcam_ipi_event, ack_data) == 6, "ACK offset");
_Static_assert(sizeof(struct mtkcam_ipi_ack_info) == 69, "ACK size");
_Static_assert(sizeof(struct ccd_worker_item) == 1036, "CCD worker envelope");
_Static_assert(offsetof(struct ccd_worker_item, len) == 1032, "CCD worker length offset");
_Static_assert(sizeof(struct ccd_master_listen_item) == 40, "CCD master envelope");
_Static_assert(sizeof(struct mtkcam_ipi_event) <= BUF_MAX_SIZE, "CCD send bound");

static void put32(unsigned char *p, unsigned int v)
{
	p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}

static void ack_test(void)
{
	unsigned char storage[76] = { 0 }, *p = storage + 1; /* Unaligned message. */
	struct mt6878_camera_reply state = { .session = 2, .cookie = 77 };
	struct mt6878_camsv_buffer work = { .dma = 4096, .size = 4096, .mapped = 1 };
	struct mt6878_camsv_buffer cq = { 0 };
	unsigned int i;

	p[0] = 2; put32(p + 1, 77); p[5] = CAM_CMD_ACK; p[6] = CAM_CMD_FRAME;
	assert(!mt6878_camera_reply_header(p, 75, 2, 77, CAM_CMD_FRAME));
	assert(mt6878_camera_reply_header(p, 75, 2, 77, CAM_CMD_FLUSH) == -ESTALE);
	assert(mt6878_camera_reply_header(NULL, 0, 2, 77, CAM_CMD_FRAME) == -ENOTCONN);
	p[6] = CAM_CMD_CONFIG;
	assert(mt6878_camera_reply_header(p, 75, 2, 77, CAM_CMD_FRAME) == -ESTALE);
	p[6] = CAM_CMD_FRAME;
	put32(p + 59, 128); put32(p + 63, 256);
	assert(!mt6878_camera_ack(&state, p, 75, &work, &cq));
	assert(cq.dma == 4224 && cq.size == 256 && cq.mapped == 1);
	assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -EALREADY);
	state.accepted = 0; p[0] = 3;
	assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -ESTALE);
	assert(!state.first_error); p[0] = 2;
	for (i = 0; i < 75; i++) {
		state.first_error = 0;
		assert(mt6878_camera_reply_header(p, i, 2, 77, CAM_CMD_FRAME) == -EMSGSIZE);
		assert(mt6878_camera_ack(&state, p, i, &work, &cq) == -EMSGSIZE);
	}
	state.first_error = 0; put32(p + 63, 0);
	assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -ERANGE);
	put32(p + 63, 256);
	assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -ERANGE);
	state.first_error = 0; put32(p + 59, 0xffffffffU);
	assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -ERANGE);
	state.first_error = 0; put32(p + 59, 128); put32(p + 7, (unsigned int)-EIO);
	assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -EIO);
	put32(p + 7, 0);
	for (i = 0; i < 8; i++) {
		if (i == 6) continue;
		state.first_error = 0; put32(p + 11 + i * 8, 1);
		assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -EOPNOTSUPP);
		put32(p + 11 + i * 8, 0);
	}
	state.first_error = 0; work.dma = (1ULL << 34) - 4095;
	assert(mt6878_camera_ack(&state, p, 75, &work, &cq) == -ERANGE);
}

static void mode_test(unsigned int width, unsigned int height, unsigned int stride)
{
	/* Exercise explicit alternative PDAF output layouts, NOT a claim that the
	 * firmware chooses either. DT30 does not choose the memory format.
	 */
	struct mt6878_camsv_dma_layout layouts[2] = {
		{ MTKCAM_IPI_IMG_FMT_BAYER10, width, height, stride, stride * height, 4 },
		{ MTKCAM_IPI_IMG_FMT_BAYER8, width, height / 4, width, width * (height / 4), 4 }
	};
	struct mt6878_camsv_job job = { .sv_id = 1, .raw_tag = 1, .pdaf_tag = 2 };
	struct mtkcam_ipi_img_output outputs[2] = { 0 };
	struct mtkcam_ipi_frame_param *frame = malloc(sizeof(*frame));
	unsigned int i;

	assert(frame);
	job.width = width;
	job.height = height;
	job.raw_layout = layouts[0];
	job.pdaf_layout = layouts[1];
	job.raw = (struct mt6878_camsv_buffer){ 0x100000, layouts[0].sizeimage, 1 };
	job.pdaf = (struct mt6878_camsv_buffer){ 0x2000000, layouts[1].sizeimage, 1 };
	for (i = 0; i < 2; i++) {
		assert(!mt6878_camsv_layout_validate(&layouts[i], layouts[i].sizeimage));
		assert(mt6878_camsv_layout_validate(&layouts[i], layouts[i].sizeimage - 1));
		outputs[i].uid.pipe_id = 1 + MTKCAM_SUBDEV_CAMSV_START;
		outputs[i].uid.id = MTKCAM_IPI_CAMSV_MAIN_OUT;
		outputs[i].fmt.format = layouts[i].format;
		outputs[i].fmt.s.w = width;
		outputs[i].fmt.s.h = layouts[i].height;
		outputs[i].fmt.stride[0] = layouts[i].bytesperline;
		outputs[i].buf[0][0].iova = i ? job.pdaf.dma : job.raw.dma;
		outputs[i].buf[0][0].size = layouts[i].sizeimage;
	}
	assert(!mt6878_camera_frame(frame, &job, 128, 1024, 4096, &outputs[0], &outputs[1]));
	assert(frame->camsv_param[0][1].pipe_id == 4);
	assert(frame->camsv_param[0][2].camsv_img_outputs[0].buf[0][0].size == layouts[1].sizeimage);
	assert(frame->camsv_param[1][1].pipe_id == 0);
	outputs[1].buf[0][1].size = 1;
	assert(mt6878_camera_frame(frame, &job, 128, 1024, 4096, &outputs[0], &outputs[1]) == -EOPNOTSUPP);
	outputs[1].buf[0][1].size = 0;
	layouts[0].bytesperline--;
	assert(mt6878_camsv_layout_validate(&layouts[0], job.raw.size) == -ERANGE);
	layouts[0].bytesperline++;
	layouts[1].format = MTKCAM_IPI_IMG_FMT_BAYER10;
	assert(mt6878_camsv_layout_validate(&layouts[1], job.pdaf.size) == -ERANGE);
	layouts[1].bytesperline = stride;
	layouts[1].sizeimage = stride * (height / 4);
	assert(!mt6878_camsv_layout_validate(&layouts[1], layouts[1].sizeimage));
	layouts[1].sizeimage--;
	assert(mt6878_camsv_layout_validate(&layouts[1], job.pdaf.size) == -ERANGE);
	layouts[1].sizeimage++;
	layouts[1].format = MTKCAM_IPI_IMG_FMT_BAYER10_UNPACKED;
	assert(mt6878_camsv_layout_validate(&layouts[1], 0xffffffffU) == -EOPNOTSUPP);
	free(frame);
}

int main(void)
{
	assert(mt6878_camera_cookie_valid(2, (2U << 24) | 77));
	assert(!mt6878_camera_cookie_valid(2, (1U << 24) | 77));
	assert(!mt6878_camera_cookie_valid(4, 4U << 24));
	ack_test();
	mode_test(4000, 3000, 5024);
	mode_test(4096, 2304, 5120);
	return 0;
}
