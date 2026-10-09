/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_CAPTURE_OWNER_H
#define MT6878_CAMERA_CAPTURE_OWNER_H

#include "mt6878-camera-composer.h"
#include "mt6878-camsv-vb2.h"

struct mt6878_camera_done_snapshot {
	u32 outer_sequence, inner_sequence, status;
	u64 timestamp_ns;
};

struct mt6878_camera_capture_owner {
	struct mt6878_camera_reply reply;
	struct mt6878_camsv_job job;
	struct mt6878_camsv_buffer workbuf;
	struct mt6878_camsv_vb2_pair *pair;
	const struct mt6878_camsv_backend *backend;
	struct mt6878_camsv_resources *resources;
	struct device *allocator;
	/* Prove powered exclusive banks, live registered IRQ ownership and
	 * the vendor status-read acknowledgment protocol before any read.
	 * Must be atomic in hard IRQ; no placeholder success implementation.
	 */
	int (*verify_irq_read)(struct mt6878_camera_capture_owner *owner);
};

/* Queue mutex / threaded IRQ serialization is supplied by the capture owner.
 * No probe, request_irq, clocks, firmware loading or production registration.
 */
int mt6878_camera_capture_ack(struct mt6878_camera_capture_owner *owner,
	const void *message, unsigned int length,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf);
int mt6878_camera_done_snapshot(struct mt6878_camera_capture_owner *owner,
	struct mt6878_camera_done_snapshot *snapshot);
int mt6878_camera_done_dispatch(struct mt6878_camera_capture_owner *owner,
	const struct mt6878_camera_done_snapshot *snapshot);

#endif
