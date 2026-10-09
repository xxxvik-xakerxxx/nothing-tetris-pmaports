// SPDX-License-Identifier: GPL-2.0-only
/* Compile-only native CCD caller. Not installed or started by this candidate. */
#include <sys/ioctl.h>
#include <linux/dma-buf.h>
#include <errno.h>
#ifndef __packed
#define __packed __attribute__((packed))
#endif
#include "mt6878-camera-ccd-composer-session.h"

int mt6878_ccd_worker_compose_reply(int ccd_fd,
	struct mt6878_ccd_composer_session *session,
	const struct ccd_worker_item *request);

static int ccd_sync(unsigned int fd, unsigned long long flags)
{
	struct dma_buf_sync sync = { .flags = flags };

	if (ioctl((int)fd, DMA_BUF_IOCTL_SYNC, &sync) < 0)
		return -errno;
	return 0;
}

/* One real receive/compose/reply step for an already registered CCD endpoint.
 * No fake ready return when the pinned READ returns zero without an envelope.
 * Pinned READ can swallow an interrupted wait into that zero/empty result.
 * Session, mappings and fd are borrowed until this call has actually returned;
 * no concurrent dispatch, close, reset or unmap is permitted by this interface.
 * This is deliberately not used as a boot service or run in local tests.
 */
int mt6878_ccd_worker_receive_once(int ccd_fd,
	struct mt6878_ccd_composer_session *session)
{
	struct ccd_worker_item request = { 0 };

	if (ccd_fd < 0 || !session || session->closed)
		return -ENOTCONN;
	request.src = session->session + CCD_IPI_ISP_MAIN;
	request.id = request.src;
	if (ioctl(ccd_fd, IOCTL_CCD_WORKER_READ, &request) < 0)
		return -errno;
	if (!request.len)
		return -ENOMSG;
	return mt6878_ccd_worker_compose_reply(ccd_fd, session, &request);
}

/* Caller receives request via actual IOCTL_CCD_WORKER_READ. Its pinned kernel
 * implementation can block indefinitely: receive must live in an owned,
 * interruptible worker, not a bounded control path or the camera IRQ thread.
 * No retries. ioctl WRITE uses the same 1036-byte envelope as matching libccd.
 * WRITE success means ioctl acceptance, not ACK delivery or hardware completion:
 * pinned ccd_worker_write is void and may drop a missing/destroyed endpoint.
 * Sync requires real dma-buf exporters. ENOTTY is a hard ownership failure,
 * never treated as permission to publish an unsynchronized CQ.
 */
int mt6878_ccd_worker_compose_reply(int ccd_fd,
	struct mt6878_ccd_composer_session *session,
	const struct ccd_worker_item *request)
{
	struct ccd_worker_item reply;
	int ret, cleanup, message_sync = 0, work_sync = 0;

	if (ccd_fd < 0 || !session || !request || request->len < 6 ||
	    request->len > BUF_MAX_SIZE || session->closed ||
	    request->src != session->session + CCD_IPI_ISP_MAIN ||
	    request->id != request->src || request->sbuf[0] != session->session)
		return -EINVAL;
	if (request->sbuf[5] == CAM_CMD_FRAME) {
		if (session->first_error)
			return session->first_error;
		if (mt6878_camera_le32(request->sbuf + 1) != session->job.sequence ||
		    session->frame_started || session->flushed || !session->configured)
			return -ESTALE;
		ret = ccd_sync(session->mappings.msg_buf.ccd_fd,
			DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ);
		if (ret)
			goto fail;
		message_sync = 1;
		ret = ccd_sync(session->mappings.workbuf.ccd_fd,
			DMA_BUF_SYNC_START | DMA_BUF_SYNC_RW);
		if (ret)
			goto fail;
		work_sync = 1;
	}
	ret = mt6878_ccd_composer_dispatch(session, request, &reply);
fail:
	if (work_sync) {
		cleanup = ccd_sync(session->mappings.workbuf.ccd_fd,
			DMA_BUF_SYNC_END | DMA_BUF_SYNC_RW);
		if (cleanup && ret >= 0)
			ret = cleanup;
	}
	if (message_sync) {
		cleanup = ccd_sync(session->mappings.msg_buf.ccd_fd,
			DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ);
		if (cleanup && ret >= 0)
			ret = cleanup;
	}
	if (ret < 0) {
		if (ret != -ESTALE && !session->first_error)
			session->first_error = ret;
		return ret == -ESTALE ? ret : session->first_error;
	}
	if (ret == 1 && ioctl(ccd_fd, IOCTL_CCD_WORKER_WRITE, &reply) < 0) {
		ret = -errno;
		if (!session->first_error)
			session->first_error = ret;
		return session->first_error;
	}
	return 0;
}
