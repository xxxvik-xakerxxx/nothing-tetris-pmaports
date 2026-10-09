/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_CCD_OWNER_H
#define MT6878_CAMERA_CCD_OWNER_H

#include <linux/completion.h>
#include <linux/mutex.h>
#include <linux/rpmsg.h>
#include <linux/spinlock.h>
#include "mt6878-camera-composer.h"
#include "mt6878-camera-ccd-session.h"

/* No registration. The capture/CCD bus owner supplies a real endpoint created
 * with mt6878_camera_ccd_rx as callback and this object as priv. Initialize
 * first, bind endpoint second; drain callback lifetime before freeing owner.
 */
struct mt6878_camera_ccd_owner {
	struct mutex lock;
	spinlock_t reply_lock;
	struct completion completion;
	struct rpmsg_endpoint *endpoint;
	struct rpmsg_device *client;
	unsigned int session, created, configured, frame_sent;
	unsigned int msg_size, cq_size;
	int first_error;
	struct mt6878_camera_ccd_session gate;
};

void mt6878_camera_ccd_init(struct mt6878_camera_ccd_owner *owner, unsigned int session);
/* One binding only. Bus owner must serialize endpoint lifetime against send,
 * drain callbacks before owner destruction, and never recycle this owner.
 */
int mt6878_camera_ccd_bind(struct mt6878_camera_ccd_owner *owner,
	struct rpmsg_endpoint *endpoint);
int mt6878_camera_ccd_rx(struct rpmsg_device *rpdev, void *data, int length,
	void *priv, u32 src);
/* params carry real exported DMA-BUF handles valid for the matching CCD
 * consumer. Never cast a kernel pointer or invent an fd. Caller owns mappings,
 * transport endpoint lifetime and cache synchronization throughout the session.
 */
int mt6878_camera_ccd_create(struct mt6878_camera_ccd_owner *owner,
	const struct mtkcam_ipi_session_param *params);
int mt6878_camera_ccd_config(struct mt6878_camera_ccd_owner *owner,
	const struct mtkcam_ipi_config_param *config);
int mt6878_camera_ccd_frame(struct mt6878_camera_ccd_owner *owner,
	unsigned int cookie, unsigned int offset, unsigned int size,
	unsigned int timeout_ms, unsigned char reply[75]);
struct mt6878_camera_capture_owner;
struct vb2_v4l2_buffer;
int mt6878_camera_ccd_capture(struct mt6878_camera_ccd_owner *owner,
	struct mt6878_camera_capture_owner *capture, unsigned int msg_offset,
	unsigned int msg_size, unsigned int timeout_ms,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf);
/* Drain is legal after a failed frame. It does not release buffers or prove
 * hardware quiescence. Any flush/destroy error keeps endpoint/mappings pinned.
 */
int mt6878_camera_ccd_drain(struct mt6878_camera_ccd_owner *owner,
	unsigned int timeout_ms);

#endif
