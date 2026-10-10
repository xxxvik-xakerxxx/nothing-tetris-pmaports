/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAPTURE_EPOCH_H
#define MT6878_CAPTURE_EPOCH_H

#include "mt6878-camera-joint-reset.h"

/* One separately allocated record per frame. Never reuse/zero a record.
 * Native video owns capture/epoch storage and excludes unregister throughout
 * these calls. No queue lock may be held across submit/retirement.
 */
struct mt6878_capture_epoch {
	struct mutex lock;
	struct mt6878_native_capture *capture;
	struct mt6878_camera_joint_reset reset, retirement_reset;
	struct mt6878_camsv_transaction dma_receipt;
	struct mt6878_seninf_route route_receipt;
	struct mt6878_seninf_transaction tsrec_receipt, events_receipt;
	struct mt6878_camsv_job layout;
	struct mtkcam_ipi_config_param config;
	unsigned int cq_bytes, port, pixel_mode;
	u64 timestamp;
	bool entered, retirement_attempted, retired, frame_done, warm, detached;
	int first_error, retirement_error;
};

/* Resource-only allocation: capture must already have a fresh genuine bind.
 * This does not rebind an old capture, remap resources or initialize its mutex.
 */
struct mt6878_capture_epoch *mt6878_capture_epoch_alloc(struct mt6878_native_capture *capture);
int mt6878_capture_epoch_submit(struct mt6878_capture_epoch *epoch,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	const struct mt6878_camsv_job *layout, const struct mtkcam_ipi_config_param *config,
	unsigned int port, unsigned int pixel_mode);
/* Drain task/IRQ, prove DMA OFF, perform source-backed joint reset and PHY
 * off, free CQ and per-frame allocations. Persistent MMIO/IRQ/PM/queue refs
 * stay registered. Failed cleanup retains storage and forbids rearm.
 */
int mt6878_capture_epoch_retire(struct mt6878_capture_epoch *epoch, unsigned long timeout);
/* Fresh frame transaction only after the previous successful receipt. Does
 * not re-probe, reinitialize any published mutex or clear persistent errors.
 */
struct mt6878_capture_epoch *mt6878_capture_epoch_next(struct mt6878_capture_epoch *previous);
int mt6878_capture_epoch_free(struct mt6878_capture_epoch *epoch);

#endif
