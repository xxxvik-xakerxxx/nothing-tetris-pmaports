/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_CCD_SESSION_H
#define MT6878_CAMERA_CCD_SESSION_H

#include "mt6878-camera-composer.h"

/* A local one-shot state machine, NOT an added vendor wire epoch. Rebinding
 * or reinitializing this state cannot distinguish old replies on the same
 * endpoint. Allocate a new owner only after the bus drains/destroys that
 * endpoint and the capture owner proves DMA quiescence.
 */
struct mt6878_camera_ccd_session {
	unsigned int session, pending, closed, command, cookie;
	unsigned int frame_started, flush_started, flushed, destroy_started, destroyed;
	int result;
	unsigned char reply[75];
};

static inline int mt6878_camera_ccd_begin(struct mt6878_camera_ccd_session *s,
	unsigned int command, unsigned int cookie)
{
	if (!s || s->session > 3)
		return -EINVAL;
	if (s->closed)
		return -ENOTCONN;
	if (s->pending)
		return -EBUSY;
	if (command == CAM_CMD_FRAME) {
		if (!mt6878_camera_cookie_valid(s->session, cookie))
			return -EINVAL;
		if (s->frame_started || s->flush_started)
			return -EALREADY;
		s->frame_started = 1;
	} else if (command == CAM_CMD_FLUSH) {
		if (cookie || s->flush_started)
			return -EALREADY;
		s->flush_started = 1;
	} else if (command == CAM_CMD_DESTROY_SESSION) {
		if (cookie || !s->flushed || s->destroy_started)
			return -EINVAL;
		s->destroy_started = 1;
	} else {
		return -EOPNOTSUPP;
	}
	s->command = command;
	s->cookie = cookie;
	s->result = 0;
	s->pending = 1;
	return 0;
}

/* Must run under the same receive lock as begin/finish. Positive return
 * means a matching successful reply, zero is never a synthetic ready event.
 */
static inline int mt6878_camera_ccd_receive(struct mt6878_camera_ccd_session *s,
	const void *message, unsigned int length)
{
	const unsigned char *p = message;
	int ret;

	if (!s)
		return -EINVAL;
	if (!message) {
		s->closed = 1;
		s->result = -ENOTCONN;
		s->pending = 0;
		return -ENOTCONN;
	}
	if (s->closed)
		return -ENOTCONN;
	if (!s->pending)
		return -ESTALE;
	/* A truncated foreign reply must not cancel this frame. If its cookie
	 * cannot be read, drop it without waking the waiter; its bounded timeout
	 * remains the only evidence of failure for the outstanding command.
	 */
	if (length < 5)
		return -EMSGSIZE;
	if (p[0] != s->session || mt6878_camera_le32(p + 1) != s->cookie)
		return -ESTALE;
	ret = mt6878_camera_reply_header(message, length, s->session, s->cookie, s->command);
	if (ret == -ESTALE)
		return ret; /* No state change, no completion wake. */
	if (length >= sizeof(s->reply))
		memcpy(s->reply, message, sizeof(s->reply));
	s->pending = 0;
	s->result = ret;
	if (!ret && s->command == CAM_CMD_FLUSH)
		s->flushed = 1;
	if (!ret && s->command == CAM_CMD_DESTROY_SESSION) {
		s->destroyed = 1;
		s->closed = 1;
	}
	return ret ? ret : 1;
}

static inline int mt6878_camera_ccd_finish(struct mt6878_camera_ccd_session *s,
	int send_or_wait_error)
{
	/* Even a failed/timeout command is consumed permanently. Do not retry a
	 * FLUSH with cookie=0: the ABI has no nonce to reject its previous ACK.
	 */
	if (send_or_wait_error)
		s->result = send_or_wait_error;
	s->pending = 0;
	return s->result;
}

#endif
