// SPDX-License-Identifier: GPL-2.0-only
#include <linux/jiffies.h>
#include <linux/kernel.h>
#include <linux/build_bug.h>
#include <linux/ioctl.h>
#include "mt6878-camera-ccd-owner.h"
#include "mt6878-camera-capture-owner.h"
#include "mt6878-camera-ccd-uapi.h"

static_assert(sizeof(struct mtkcam_ipi_event) <= BUF_MAX_SIZE);
static_assert(sizeof(struct ccd_worker_item) == 1036);

void mt6878_camera_ccd_init(struct mt6878_camera_ccd_owner *owner, unsigned int session)
{
	memset(owner, 0, sizeof(*owner));
	mutex_init(&owner->lock);
	spin_lock_init(&owner->reply_lock);
	init_completion(&owner->completion);
	owner->session = session;
	owner->gate.session = session;
	if (session > CCD_IPI_MRAW_CMD - CCD_IPI_ISP_MAIN)
		owner->first_error = -EINVAL;
}

int mt6878_camera_ccd_bind(struct mt6878_camera_ccd_owner *owner,
	struct rpmsg_endpoint *endpoint)
{
	char name[RPMSG_NAME_SIZE];
	unsigned long flags;
	int ret = 0;

	if (!owner || !endpoint || !endpoint->rpdev)
		return -EINVAL;
	snprintf(name, sizeof(name), "mtk-camsys%u", owner->session);
	if (endpoint->cb != mt6878_camera_ccd_rx || endpoint->priv != owner ||
	    endpoint->addr != owner->session + CCD_IPI_ISP_MAIN ||
	    strncmp(endpoint->rpdev->id.name, name, sizeof(name)))
		return -EINVAL;
	mutex_lock(&owner->lock);
	spin_lock_irqsave(&owner->reply_lock, flags);
	if (owner->client || owner->created || owner->gate.closed || owner->first_error)
		ret = owner->first_error ? owner->first_error : -EALREADY;
	else {
		owner->client = endpoint->rpdev;
		owner->endpoint = endpoint;
	}
	spin_unlock_irqrestore(&owner->reply_lock, flags);
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_camera_ccd_rx(struct rpmsg_device *rpdev, void *data, int length,
	void *priv, u32 src)
{
	struct mt6878_camera_ccd_owner *owner = priv;
	unsigned long flags;
	unsigned int was_pending;
	int ret;

	if (!owner)
		return -EINVAL;
	spin_lock_irqsave(&owner->reply_lock, flags);
	/* A cookie is not endpoint identity. Pinned worker_write uses src, while
	 * master_destroy uses NULL/0/src=-1. Reject foreign endpoint callbacks.
	 */
	if (!owner->client || rpdev != owner->client ||
	    (!data && length != 0) ||
	    (data ? src != owner->session + CCD_IPI_ISP_MAIN : src != (u32)-1)) {
		spin_unlock_irqrestore(&owner->reply_lock, flags);
		return -ESTALE;
	}
	was_pending = owner->gate.pending;
	ret = mt6878_camera_ccd_receive(&owner->gate, data, length < 0 ? 0 : length);
	if (was_pending && !owner->gate.pending)
		complete(&owner->completion);
	spin_unlock_irqrestore(&owner->reply_lock, flags);
	return ret == 1 ? 0 : ret;
}

static int ccd_send(struct mt6878_camera_ccd_owner *owner, struct mtkcam_ipi_event *event)
{
	unsigned long flags;
	unsigned int closed;

	spin_lock_irqsave(&owner->reply_lock, flags);
	closed = owner->gate.closed;
	spin_unlock_irqrestore(&owner->reply_lock, flags);
	if (closed || !owner->endpoint || !owner->client)
		return -ENOTCONN;
	event->cookie.session_id = owner->session;
	/* Pinned CCD trysend enqueues via ccd_send(..., wait=0). Never retry. */
	return rpmsg_trysend(owner->endpoint, event, sizeof(*event));
}

static int ccd_error(struct mt6878_camera_ccd_owner *owner, int error)
{
	if (error && !owner->first_error)
		owner->first_error = error;
	return error;
}

int mt6878_camera_ccd_create(struct mt6878_camera_ccd_owner *owner,
	const struct mtkcam_ipi_session_param *params)
{
	struct mtkcam_ipi_event event = { 0 };
	int ret;

	if (!owner || !params || !params->workbuf.size ||
	    params->msg_buf.size < sizeof(struct mtkcam_ipi_frame_param) ||
	    params->workbuf.ccd_fd > 0x7fffffff || params->msg_buf.ccd_fd > 0x7fffffff)
		return -EINVAL;
	mutex_lock(&owner->lock);
	ret = owner->first_error;
	if (!ret && (owner->created || owner->frame_sent))
		ret = -EALREADY;
	if (!ret) {
		event.cmd_id = CAM_CMD_CREATE_SESSION;
		event.session_data = *params;
		event.session_data.msg_buf.iova = 0; /* Exact pinned create-session ABI. */
		ret = ccd_send(owner, &event);
		if (!ret) {
			owner->created = 1; /* Queued, NOT firmware/service readiness. */
			owner->msg_size = params->msg_buf.size;
			owner->cq_size = params->workbuf.size;
		}
	}
	ccd_error(owner, ret);
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_camera_ccd_config(struct mt6878_camera_ccd_owner *owner,
	const struct mtkcam_ipi_config_param *config)
{
	struct mtkcam_ipi_event event = { 0 };
	int ret;

	if (!owner || !config)
		return -EINVAL;
	mutex_lock(&owner->lock);
	ret = owner->first_error;
	if (!ret && (!owner->created || owner->configured))
		ret = -EINVAL;
	if (!ret) {
		event.cmd_id = CAM_CMD_CONFIG;
		event.config_data = *config; /* Exact caller-proven sensor/receiver config. */
		ret = ccd_send(owner, &event);
		if (!ret)
			owner->configured = 1; /* Ordered enqueue, not a fabricated ACK. */
	}
	ccd_error(owner, ret);
	mutex_unlock(&owner->lock);
	return ret;
}

/* Called under owner->lock. Only rx callback takes reply_lock. */
static int ccd_exchange(struct mt6878_camera_ccd_owner *owner,
	struct mtkcam_ipi_event *event, unsigned int timeout_ms)
{
	unsigned long flags;
	int ret;

	if (!timeout_ms || timeout_ms > 5000)
		return -EINVAL;
	reinit_completion(&owner->completion);
	spin_lock_irqsave(&owner->reply_lock, flags);
	ret = mt6878_camera_ccd_begin(&owner->gate, event->cmd_id, event->cookie.frame_no);
	spin_unlock_irqrestore(&owner->reply_lock, flags);
	if (ret)
		return ret;
	ret = ccd_send(owner, event);
	if (!ret && !wait_for_completion_timeout(&owner->completion,
		msecs_to_jiffies(timeout_ms)))
		ret = -ETIMEDOUT;
	spin_lock_irqsave(&owner->reply_lock, flags);
	ret = mt6878_camera_ccd_finish(&owner->gate, ret);
	spin_unlock_irqrestore(&owner->reply_lock, flags);
	return ret;
}

int mt6878_camera_ccd_frame(struct mt6878_camera_ccd_owner *owner,
	unsigned int cookie, unsigned int offset, unsigned int size,
	unsigned int timeout_ms, unsigned char reply[75])
{
	struct mtkcam_ipi_event event = { 0 };
	int ret;

	if (!owner || !reply || !mt6878_camera_cookie_valid(owner->session, cookie))
		return -EINVAL;
	mutex_lock(&owner->lock);
	ret = owner->first_error;
	if (!ret && (!owner->configured || owner->frame_sent ||
	    size < sizeof(struct mtkcam_ipi_frame_param) ||
	    offset > owner->msg_size || size > owner->msg_size - offset))
		ret = -EINVAL;
	if (!ret) {
		event.cmd_id = CAM_CMD_FRAME;
		event.cookie.frame_no = cookie; /* Caller uses exact to_fh_cookie encoding. */
		event.frame_data.cur_msgbuf_offset = offset;
		event.frame_data.cur_msgbuf_size = size;
		owner->frame_sent = 1; /* One bounded capture per session, no CQ reuse. */
		ret = ccd_exchange(owner, &event, timeout_ms);
		if (!ret)
			memcpy(reply, owner->gate.reply, sizeof(owner->gate.reply));
	}
	ccd_error(owner, ret);
	mutex_unlock(&owner->lock);
	return ret;
}

int mt6878_camera_ccd_capture(struct mt6878_camera_ccd_owner *owner,
	struct mt6878_camera_capture_owner *capture, unsigned int msg_offset,
	unsigned int msg_size, unsigned int timeout_ms,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf)
{
	unsigned char reply[75];
	int ret;

	if (!owner || !capture || !raw || !pdaf ||
	    capture->reply.session != owner->session ||
	    capture->job.sequence != capture->reply.cookie ||
	    capture->workbuf.size != owner->cq_size)
		return -EINVAL;
	/* The actual full frame is already in the exported message DMA-BUF;
	 * caller holds its mapping and has completed CPU/device synchronization.
	 * Transport ACK never substitutes for the capture backend's CQ verifier.
	 */
	ret = mt6878_camera_ccd_frame(owner, capture->reply.cookie, msg_offset,
		msg_size, timeout_ms, reply);
	if (!ret)
		ret = mt6878_camera_capture_ack(capture, reply, sizeof(reply), raw, pdaf);
	if (ret && !capture->reply.first_error)
		capture->reply.first_error = ret;
	return ret;
}

int mt6878_camera_ccd_drain(struct mt6878_camera_ccd_owner *owner,
	unsigned int timeout_ms)
{
	struct mtkcam_ipi_event event = { 0 };
	int ret = 0;

	if (!owner)
		return -EINVAL;
	mutex_lock(&owner->lock);
	if (owner->created) {
		event.cmd_id = CAM_CMD_FLUSH;
		ret = ccd_exchange(owner, &event, timeout_ms);
		if (!ret) {
			event.cmd_id = CAM_CMD_DESTROY_SESSION;
			ret = ccd_exchange(owner, &event, timeout_ms);
		}
		if (!ret) {
			owner->created = 0;
			owner->configured = 0;
		}
	}
	ccd_error(owner, ret);
	ret = owner->first_error; /* Cleanup cannot hide the original failure. */
	mutex_unlock(&owner->lock);
	return ret;
}
