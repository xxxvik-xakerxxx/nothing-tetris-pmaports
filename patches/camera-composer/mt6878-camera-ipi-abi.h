/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Copyright (c) 2019 MediaTek Inc.
 */

#ifndef __MTK_CAM_IPI_H__
#define __MTK_CAM_IPI_H__

#define MTK_CAM_IPI_VERSION_MAJOR 0
#define MTK_CAM_IPI_VERSION_MINOR 1

#include <linux/types.h>
enum mtkcam_pipe_subdev {
	MTKCAM_SUBDEV_RAW_START = 0,
	MTKCAM_SUBDEV_RAW_0	= MTKCAM_SUBDEV_RAW_START,
	MTKCAM_SUBDEV_RAW_1,
	MTKCAM_SUBDEV_RAW_2,
	MTKCAM_SUBDEV_RAW_END,
	MTKCAM_SUBDEV_CAMSV_START = MTKCAM_SUBDEV_RAW_END,
	MTKCAM_SUBDEV_CAMSV_0 = MTKCAM_SUBDEV_CAMSV_START,
	MTKCAM_SUBDEV_CAMSV_1,
	MTKCAM_SUBDEV_CAMSV_2,
	MTKCAM_SUBDEV_CAMSV_3,
	MTKCAM_SUBDEV_CAMSV_4,
	MTKCAM_SUBDEV_CAMSV_5,
	MTKCAM_SUBDEV_CAMSV_6,
	MTKCAM_SUBDEV_CAMSV_7,
	MTKCAM_SUBDEV_CAMSV_8,
	MTKCAM_SUBDEV_CAMSV_9,
	MTKCAM_SUBDEV_CAMSV_10,
	MTKCAM_SUBDEV_CAMSV_11,
	MTKCAM_SUBDEV_CAMSV_12,
	MTKCAM_SUBDEV_CAMSV_13,
	MTKCAM_SUBDEV_CAMSV_14,
	MTKCAM_SUBDEV_CAMSV_15,
	MTKCAM_SUBDEV_CAMSV_END,
	MTKCAM_SUBDEV_MRAW_START = MTKCAM_SUBDEV_CAMSV_END,
	MTKCAM_SUBDEV_MRAW_0 = MTKCAM_SUBDEV_MRAW_START,
	MTKCAM_SUBDEV_MRAW_1,
	MTKCAM_SUBDEV_MRAW_2,
	MTKCAM_SUBDEV_MRAW_3,
	MTKCAM_SUBDEV_MRAW_END,
	MTKCAM_SUBDEV_MAX = MTKCAM_SUBDEV_MRAW_END,
};
enum mtkcam_ipi_video_id {
	MTKCAM_IPI_RAW_ID_UNKNOWN	= 0,
	MTKCAM_IPI_RAW_RAWI_2,		/* RAWI_R2 */
	MTKCAM_IPI_RAW_RAWI_3,		/* RAWI_R3 */
	MTKCAM_IPI_RAW_RAWI_5,		/* RAWI_R5 */
	MTKCAM_IPI_RAW_IPUI,		/* ADLRD */
	MTKCAM_IPI_RAW_IMGO,		/* IMGO_R1 */
	/* no need pure raw */
	MTKCAM_IPI_RAW_YUVO_1,		/* YUVO_R1 */
	MTKCAM_IPI_RAW_YUVO_2,		/* YUVO_R2 */
	MTKCAM_IPI_RAW_YUVO_3,		/* YUVO_R3 */
	MTKCAM_IPI_RAW_YUVO_4,		/* YUVO_R4 */
	MTKCAM_IPI_RAW_YUVO_5,		/* YUVO_R5 */
	MTKCAM_IPI_RAW_RZH1N2TO_2,	/* RZH1N2TO_R2 */
	MTKCAM_IPI_RAW_DRZS4NO_1,	/* DRZS4NO_R1 */
	MTKCAM_IPI_RAW_DRZS4NO_3,	/* DRZS4NO_R3 */
	MTKCAM_IPI_RAW_RZH1N2TO_3,	/* RZH1N2TO_R3 */
	MTKCAM_IPI_RAW_RZH1N2TO_1,	/* RZH1N2TO_R1 */
	MTKCAM_IPI_RAW_DRZB2NO_1,	/* DRZB2NO_R1 */
	MTKCAM_IPI_RAW_IPUO,		/* IPUO_R1 */
	MTKCAM_IPI_RAW_META_STATS_CFG,	/* All settings */
	MTKCAM_IPI_RAW_META_STATS_0,	/* statistics */

	/*
	 * MTKCAM_IPI_RAW_META_STATS_1 is for AFO only, the buffer can be
	 * dequeued once we got the  dma done.
	 */
	MTKCAM_IPI_RAW_META_STATS_1,

	/* following is for RGBW's w path */
	MTKCAM_IPI_RAW_IMGO_W,		/* IMGO_R1 */
	MTKCAM_IPI_RAW_RAWI_2_W,	/* RAWI_R2 */
	MTKCAM_IPI_RAW_RAWI_3_W,	/* RAWI_R3 */
	MTKCAM_IPI_RAW_RAWI_5_W,	/* RAWI_R5 */

	MTKCAM_IPI_RAW_ID_MAX,

	MTKCAM_IPI_CAMSV_MAIN_OUT = MTKCAM_IPI_RAW_ID_MAX,	/* imgo */

	MTKCAM_IPI_CAMSV_ID_MAX,

	MTKCAM_IPI_MRAW_ID_START = MTKCAM_IPI_CAMSV_ID_MAX,
	MTKCAM_IPI_MRAW_META_STATS_CFG = MTKCAM_IPI_MRAW_ID_START,
	MTKCAM_IPI_MRAW_META_STATS_0,
	MTKCAM_IPI_MRAW_ID_MAX,
};
enum mtkcam_ipi_fmt {
	MTKCAM_IPI_IMG_FMT_UNKNOWN		= -1,
	MTKCAM_IPI_IMG_FMT_BAYER8		= 0,
	MTKCAM_IPI_IMG_FMT_BAYER10		= 1,
	MTKCAM_IPI_IMG_FMT_BAYER12		= 2,
	MTKCAM_IPI_IMG_FMT_BAYER14		= 3,
	MTKCAM_IPI_IMG_FMT_BAYER16		= 4,
	MTKCAM_IPI_IMG_FMT_BAYER10_UNPACKED	= 5,
	MTKCAM_IPI_IMG_FMT_BAYER12_UNPACKED	= 6,
	MTKCAM_IPI_IMG_FMT_BAYER14_UNPACKED	= 7,
	MTKCAM_IPI_IMG_FMT_RGB565		= 8,
	MTKCAM_IPI_IMG_FMT_RGB888		= 9,
	MTKCAM_IPI_IMG_FMT_JPEG			= 10,
	MTKCAM_IPI_IMG_FMT_FG_BAYER8		= 11,
	MTKCAM_IPI_IMG_FMT_FG_BAYER10		= 12,
	MTKCAM_IPI_IMG_FMT_FG_BAYER12		= 13,
	MTKCAM_IPI_IMG_FMT_FG_BAYER14		= 14,
	MTKCAM_IPI_IMG_FMT_YUYV			= 15,
	MTKCAM_IPI_IMG_FMT_YVYU			= 16,
	MTKCAM_IPI_IMG_FMT_UYVY			= 17,
	MTKCAM_IPI_IMG_FMT_VYUY			= 18,
	MTKCAM_IPI_IMG_FMT_YUV_422_2P		= 19,
	MTKCAM_IPI_IMG_FMT_YVU_422_2P		= 20,
	MTKCAM_IPI_IMG_FMT_YUV_422_3P		= 21,
	MTKCAM_IPI_IMG_FMT_YVU_422_3P		= 22,
	MTKCAM_IPI_IMG_FMT_YUV_420_2P		= 23,
	MTKCAM_IPI_IMG_FMT_YVU_420_2P		= 24,
	MTKCAM_IPI_IMG_FMT_YUV_420_3P		= 25,
	MTKCAM_IPI_IMG_FMT_YVU_420_3P		= 26,
	MTKCAM_IPI_IMG_FMT_Y8			= 27,
	MTKCAM_IPI_IMG_FMT_YUYV_Y210		= 28,
	MTKCAM_IPI_IMG_FMT_YVYU_Y210		= 29,
	MTKCAM_IPI_IMG_FMT_UYVY_Y210		= 30,
	MTKCAM_IPI_IMG_FMT_VYUY_Y210		= 31,
	MTKCAM_IPI_IMG_FMT_YUYV_Y210_PACKED	= 32,
	MTKCAM_IPI_IMG_FMT_YVYU_Y210_PACKED	= 33,
	MTKCAM_IPI_IMG_FMT_UYVY_Y210_PACKED	= 34,
	MTKCAM_IPI_IMG_FMT_VYUY_Y210_PACKED	= 35,
	MTKCAM_IPI_IMG_FMT_YUV_P210		= 36,
	MTKCAM_IPI_IMG_FMT_YVU_P210		= 37,
	MTKCAM_IPI_IMG_FMT_YUV_P010		= 38,
	MTKCAM_IPI_IMG_FMT_YVU_P010		= 39,
	MTKCAM_IPI_IMG_FMT_YUV_P210_PACKED	= 40,
	MTKCAM_IPI_IMG_FMT_YVU_P210_PACKED	= 41,
	MTKCAM_IPI_IMG_FMT_YUV_P010_PACKED	= 42,
	MTKCAM_IPI_IMG_FMT_YVU_P010_PACKED	= 43,
	MTKCAM_IPI_IMG_FMT_YUV_P212		= 44,
	MTKCAM_IPI_IMG_FMT_YVU_P212		= 45,
	MTKCAM_IPI_IMG_FMT_YUV_P012		= 46,
	MTKCAM_IPI_IMG_FMT_YVU_P012		= 47,
	MTKCAM_IPI_IMG_FMT_YUV_P212_PACKED	= 48,
	MTKCAM_IPI_IMG_FMT_YVU_P212_PACKED	= 49,
	MTKCAM_IPI_IMG_FMT_YUV_P012_PACKED	= 50,
	MTKCAM_IPI_IMG_FMT_YVU_P012_PACKED	= 51,
	MTKCAM_IPI_IMG_FMT_RGB_8B_3P		= 52,
	MTKCAM_IPI_IMG_FMT_RGB_10B_3P		= 53,
	MTKCAM_IPI_IMG_FMT_RGB_12B_3P		= 54,
	MTKCAM_IPI_IMG_FMT_RGB_14B_3P		= 55,
	MTKCAM_IPI_IMG_FMT_RGB_16B_3P		= 56,
	MTKCAM_IPI_IMG_FMT_RGB_10B_3P_PACKED	= 57,
	MTKCAM_IPI_IMG_FMT_RGB_12B_3P_PACKED	= 58,
	MTKCAM_IPI_IMG_FMT_RGB_14B_3P_PACKED	= 59,
	MTKCAM_IPI_IMG_FMT_RGB_16B_3P_PACKED	= 60,
	MTKCAM_IPI_IMG_FMT_FG_BAYER8_3P		= 61,
	MTKCAM_IPI_IMG_FMT_FG_BAYER10_3P	= 62,
	MTKCAM_IPI_IMG_FMT_FG_BAYER12_3P	= 63,
	MTKCAM_IPI_IMG_FMT_FG_BAYER14_3P	= 64,
	MTKCAM_IPI_IMG_FMT_FG_BAYER16_3P	= 65,
	MTKCAM_IPI_IMG_FMT_FG_BAYER10_3P_PACKED	= 66,
	MTKCAM_IPI_IMG_FMT_FG_BAYER12_3P_PACKED	= 67,
	MTKCAM_IPI_IMG_FMT_FG_BAYER14_3P_PACKED = 68,
	MTKCAM_IPI_IMG_FMT_FG_BAYER16_3P_PACKED = 69,
	MTKCAM_IPI_IMG_FMT_UFBC_NV12		= 70,
	MTKCAM_IPI_IMG_FMT_UFBC_NV21		= 71,
	MTKCAM_IPI_IMG_FMT_UFBC_YUV_P010	= 72,
	MTKCAM_IPI_IMG_FMT_UFBC_YVU_P010	= 73,
	MTKCAM_IPI_IMG_FMT_UFBC_YUV_P012	= 74,
	MTKCAM_IPI_IMG_FMT_UFBC_YVU_P012	= 75,
	MTKCAM_IPI_IMG_FMT_UFBC_BAYER8		= 76,
	MTKCAM_IPI_IMG_FMT_UFBC_BAYER10		= 77,
	MTKCAM_IPI_IMG_FMT_UFBC_BAYER12		= 78,
	MTKCAM_IPI_IMG_FMT_UFBC_BAYER14		= 79,
	MTKCAM_IPI_IMG_FMT_BAYER10_MIPI		= 80,
	MTKCAM_IPI_IMG_FMT_BAYER_8B_4P_BGGR	= 81,
	MTKCAM_IPI_IMG_FMT_BAYER_8B_4P_GBRG	= 82,
	MTKCAM_IPI_IMG_FMT_BAYER_8B_4P_GRBG	= 83,
	MTKCAM_IPI_IMG_FMT_BAYER_8B_4P_RGGB	= 84,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_BGGR	= 85,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_GBRG	= 86,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_GRBG	= 87,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_RGGB	= 88,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_BGGR	= 89,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_GBRG	= 90,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_GRBG	= 91,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_RGGB	= 92,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_BGGR_PACKED	= 93,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_GBRG_PACKED	= 94,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_GRBG_PACKED	= 95,
	MTKCAM_IPI_IMG_FMT_BAYER_10B_4P_RGGB_PACKED	= 96,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_BGGR_PACKED	= 97,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_GBRG_PACKED	= 98,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_GRBG_PACKED	= 99,
	MTKCAM_IPI_IMG_FMT_BAYER_12B_4P_RGGB_PACKED	= 100,
	MTKCAM_IPI_IMG_FMT_BAYER22		= 101,  // re-order?
};

#define MTK_CAM_MAX_RUNNING_JOBS (3)
#define CAM_MAX_PLANENUM (4)
#define CAM_MAX_SUBSAMPLE (32)

/*
 * struct mtkcam_ipi_point - Point
 *
 * @x: x-coordinate of the point (zero-based).
 * @y: y-coordinate of the point (zero-based).
 */
struct mtkcam_ipi_point {
	__u16 x;
	__u16 y;
} __packed;

/*
 * struct mtkcam_ipi_size - Size
 *
 * @w: width (in pixels).
 * @h: height (in pixels).
 */
struct mtkcam_ipi_size {
	__u16 w;
	__u16 h;
} __packed;

/*
 * struct mtkcam_ipi_buffer
 *	- Shared buffer between cam-device and co-processor.
 *
 * @iova: DMA address for CAM DMA device.
 * @ccd_fd: fd to ccd
 * @scp_addr: SCP  address for external co-processor unit.
 * @size: buffer size.
 */
struct mtkcam_ipi_buffer {
	__u64 iova;
	union {
		__u32 ccd_fd;
		__u32 scp_addr;
	};
	__u32 size;
} __packed;

struct mtkcam_ipi_pix_fmt {
	__u32			format;
	struct mtkcam_ipi_size	s;
	__u16			stride[CAM_MAX_PLANENUM];
} __packed;

struct mtkcam_ipi_crop {
	struct mtkcam_ipi_point p;
	struct mtkcam_ipi_size s;
} __packed;

struct mtkcam_ipi_uid {
	__u8 pipe_id;
	__u8 id;
} __packed;

struct mtkcam_ipi_img_input {
	struct mtkcam_ipi_uid		uid;
	struct mtkcam_ipi_pix_fmt	fmt;
	struct mtkcam_ipi_buffer	buf[CAM_MAX_PLANENUM];
} __packed;

struct mtkcam_ipi_img_output {
	struct mtkcam_ipi_uid		uid;
	struct mtkcam_ipi_pix_fmt	fmt;
	struct mtkcam_ipi_buffer	buf[CAM_MAX_SUBSAMPLE][CAM_MAX_PLANENUM];
	struct mtkcam_ipi_crop		crop;
} __packed;

struct mtkcam_ipi_meta_input {
	struct mtkcam_ipi_uid		uid;
	struct mtkcam_ipi_buffer	buf;
} __packed;

struct mtkcam_ipi_meta_output {
	struct mtkcam_ipi_uid		uid;
	struct mtkcam_ipi_buffer	buf;
} __packed;

struct mtkcam_ipi_input_param {
	__u32	fmt;
	__u8	raw_pixel_id;
	__u8	data_pattern;
	__u8	pixel_mode;
	__u8	pixel_mode_before_raw;
	__u8	subsample;
	/* u8 continuous; */ /* always 1 */
	/* u16 tg_fps; */ /* not used yet */
	struct mtkcam_ipi_crop in_crop;
} __packed;

struct mtkcam_ipi_sv_input_param {
	__u32	pipe_id;
	__u8	tag_id;
	__u8	tag_order;
	__u8	is_first_frame;
	__u8	is_two_smi_out;
	__u8	is_last_order_meta_off;
	struct mtkcam_ipi_input_param input;
} __packed;

struct mtkcam_ipi_mraw_input_param {
	__u32	pipe_id;
	struct mtkcam_ipi_input_param input;
} __packed;

struct mtkcam_ipi_img_ufo_param {
	__u32 ufd_bitstream_ofst_addr[2]; /* 2 for max 3-raw of twin driver */
	__u32 ufd_bs_au_start[2];
	__u32 ufd_au2_size[2];
	__u32 ufd_bond_mode[2]; /* bond means boundary, 2 for max 3-raw of twin driver */
} __packed;

struct mtkcam_ipi_img_ufdo_params {
	/* NOTE: "imgo_w" param is not required
	   until supporting twin mode in RGBW */
	struct mtkcam_ipi_img_ufo_param imgo;
	/* struct mtkcam_ipi_img_ufo_param imgo2; */
	struct mtkcam_ipi_img_ufo_param yuvo1;
	struct mtkcam_ipi_img_ufo_param yuvo3;
} __packed;

struct mtkcam_ipi_img_ufdi_params {
	struct mtkcam_ipi_img_ufo_param rawi2;
	struct mtkcam_ipi_img_ufo_param rawi3;
	/* struct mtkcam_ipi_img_ufo_param rawi4; */
	struct mtkcam_ipi_img_ufo_param rawi5;
} __packed;

enum dc_path_type {
	DC_DRAM,
	DC_SLB_EMI,
	DC_SLB_DEDICATED_PORT,
};

struct mtkcam_ipi_dcif_ring_param {
	__u8	ring_mode_en;
	__u64	ring_start_offset;
	__u8	dc_path_type;
} __packed;

struct mtkcam_ipi_raw_frame_param {
	__u8	imgo_path_sel; /* mtkcam_ipi_raw_path_control */
	__u32	hardware_scenario;
	__u32	bin_flag;
	__u8    exposure_num;
	__u8    previous_exposure_num;

	/* blahblah */
} __packed;

struct mtkcam_ipi_adl_frame_param {
	__u8 vpu_i_point;
	__u8 vpu_o_point;
	__u8 sysram_en;
	__u32 block_y_size;
	__u64 slb_addr;
	__u32 slb_size;
} __packed;

/* TODO: support CAMSV */
struct cam_camsv_params {
	/* sth here */
} __packed;

#define MRAW_MAX_IMAGE_OUTPUT (3)
#define CAMSV_MAX_IMAGE_OUTPUT (1)

struct mtkcam_ipi_camsv_frame_param {
	__u32	pipe_id;
	__u8	tag_id;
	__u32	hardware_scenario; /* TODO: remove it */

	struct mtkcam_ipi_img_output camsv_img_outputs[CAMSV_MAX_IMAGE_OUTPUT];
} __packed;

struct mtkcam_ipi_mraw_frame_param {
	__u32 pipe_id;

	struct mtkcam_ipi_meta_input mraw_meta_inputs;
	struct mtkcam_ipi_img_output mraw_img_outputs[MRAW_MAX_IMAGE_OUTPUT];
} __packed;

struct mtkcam_ipi_session_cookie {
	__u8 session_id;
	__u32 frame_no;
} __packed;

struct mtkcam_ipi_session_param {
	struct mtkcam_ipi_buffer workbuf; /* TODO: rename cqbuf? */
	struct mtkcam_ipi_buffer msg_buf;
} __packed;

struct mtkcam_ipi_hw_mapping {
	__u8 pipe_id; /* ref. to mtkcam_pipe_subdev */
	__u16 dev_mask; /* ref. to mtkcam_pipe_dev */
} __packed;

struct mtkcam_ipi_bw_info {
	/* TBD */
	/* TODO: define ports in defs.h */
	__u32 xsize;
	__u32 ysize;
} __packed;

struct mtkcam_ipi_timeshared_msg {
	__u8	session_id;
	__u32	cur_msgbuf_offset;
	__u32	cur_msgbuf_size;
} __packed;

/*  Control flags of CAM_CMD_CONFIG */
#define MTK_CAM_IPI_CONFIG_TYPE_INIT			0x0001
#define MTK_CAM_IPI_CONFIG_TYPE_INPUT_CHANGE		0x0002
#define MTK_CAM_IPI_CONFIG_TYPE_EXEC_TWICE		0x0004
#define MTK_CAM_IPI_CONFIG_TYPE_SMVR_PREVIEW		0x0008
#define MTK_CAM_IPI_CONFIG_TYPE_REINIT		0x00010


/* TODO: update number */
#define CAM_MAX_INPUT_PAD           (3)
#define CAM_MAX_W_PATH_INPUT_SIZE   (2)
#define CAM_MAX_IMAGE_INPUT  (CAM_MAX_INPUT_PAD + CAM_MAX_W_PATH_INPUT_SIZE)
#define CAM_MAX_OUTPUT_PAD          (15)
#define CAM_MAX_W_PATH_OUT_SIZE     (1)
#define CAM_MAX_IMAGE_OUTPUT (CAM_MAX_OUTPUT_PAD + CAM_MAX_W_PATH_OUT_SIZE)
#define CAM_MAX_META_OUTPUT	 (4)
#define CAM_MAX_PIPE_USED	 (4)
#define MRAW_MAX_PIPE_USED   (4)
#define CAMSV_MAX_PIPE_USED  (2)
#define CAMSV_MAX_TAGS       (8)

struct mtkcam_ipi_config_param {
	__u8 flags;
	struct mtkcam_ipi_input_param	input;
	struct mtkcam_ipi_sv_input_param sv_input[CAMSV_MAX_PIPE_USED][CAMSV_MAX_TAGS];
	struct mtkcam_ipi_mraw_input_param mraw_input[MRAW_MAX_PIPE_USED];
	__u8 n_maps; /* maximum # of subdevs per stream */
	struct mtkcam_ipi_hw_mapping maps[6];
	__u8	sw_feature;
	__u32	exp_order : 4;
	__u32	frame_order : 4;
	__u32	vsync_order : 4;
	struct mtkcam_ipi_buffer w_cac_table; /* for rgbw's empty cac table */
} __packed;

struct mtkcam_ipi_frame_param {
	__u32 cur_workbuf_offset;
	__u32 cur_workbuf_size;

	struct mtkcam_ipi_dcif_ring_param dcif_param;
	struct mtkcam_ipi_raw_frame_param raw_param;
	struct mtkcam_ipi_mraw_frame_param mraw_param[MRAW_MAX_PIPE_USED];
	struct mtkcam_ipi_camsv_frame_param camsv_param[CAMSV_MAX_PIPE_USED][CAMSV_MAX_TAGS];
	struct mtkcam_ipi_adl_frame_param adl_param;

	struct mtkcam_ipi_timeshared_msg	timeshared_param;

	struct mtkcam_ipi_img_input img_ins[CAM_MAX_IMAGE_INPUT];
	struct mtkcam_ipi_img_output img_outs[CAM_MAX_IMAGE_OUTPUT];
	struct mtkcam_ipi_meta_output meta_outputs[CAM_MAX_META_OUTPUT];
	struct mtkcam_ipi_meta_input meta_inputs[CAM_MAX_PIPE_USED];
	/* for UFD meta info transfer from buffer header to parameters */
	struct mtkcam_ipi_img_ufdo_params img_ufdo_params;
	struct mtkcam_ipi_img_ufdi_params img_ufdi_params;

	/* following will be modified */
	//struct mtkcam_ipi_bw_info	bw_infos[10*3]; //ports * num_raw
} __packed;

struct mtkcam_ipi_frame_info {
	__u32	cur_msgbuf_offset;
	__u32	cur_msgbuf_size;
} __packed;

struct mtkcam_ipi_cq_desc_entry {
	__u32 offset;
	__u32 size;
} __packed;

struct mtkcam_ipi_frame_ack_result {
	struct mtkcam_ipi_cq_desc_entry		main;
	struct mtkcam_ipi_cq_desc_entry		sub;
	struct mtkcam_ipi_cq_desc_entry		mraw[MRAW_MAX_PIPE_USED];
	struct mtkcam_ipi_cq_desc_entry		camsv[CAMSV_MAX_PIPE_USED];
} __packed;

struct mtkcam_ipi_ack_info {
	__u8 ack_cmd_id;
	__s32 ret;
	struct mtkcam_ipi_frame_ack_result frame_result;
} __packed;

/*
 * The IPI command enumeration.
 */
enum mtkcam_ipi_cmds {
	/* request for a new streaming: mtkcam_ipi_session_param */
	CAM_CMD_CREATE_SESSION,

	/* config the stream: mtkcam_ipi_config_param */
	CAM_CMD_CONFIG,

	/* per-frame: mtkcam_ipi_frame_param */
	CAM_CMD_FRAME,

	/* release certain streaming: mtkcam_ipi_session_param */
	CAM_CMD_DESTROY_SESSION,

	/* ack: mtkcam_ipi_ack_info */
	CAM_CMD_ACK,

	/* flush: to ensure previous cmds are done */
	CAM_CMD_FLUSH,

	CAM_CMD_RESERVED,
};

struct mtkcam_ipi_event  {
	struct mtkcam_ipi_session_cookie cookie;
	__u8 cmd_id;
	union {
		struct mtkcam_ipi_session_param	session_data;
		struct mtkcam_ipi_config_param	config_data;
		struct mtkcam_ipi_frame_info	frame_data;
		struct mtkcam_ipi_ack_info	ack_data;
	};
} __packed;

#endif /* __MTK_CAM_IPI_H__ */
