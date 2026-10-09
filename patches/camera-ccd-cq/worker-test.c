/* SPDX-License-Identifier: GPL-2.0-only */
/* CI-only ioctl fault injection. No device, mapping or native vendor code. */
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <linux/dma-buf.h>
#include <errno.h>
#define __packed __attribute__((packed))
#include "mt6878-camera-ccd-composer-session.h"

static unsigned int calls, fail_at, empty_read;
static int injected_error;
static unsigned long seen[8];
static unsigned long long flags_seen[8];
static int fd_seen[8];
static struct ccd_worker_item sent;

static int fake_ioctl(int fd, unsigned long command, ...)
{
	va_list ap;
	void *argument;
	unsigned int index = calls++;

	assert(index < 8);
	va_start(ap, command);
	argument = va_arg(ap, void *);
	va_end(ap);
	seen[index] = command;
	fd_seen[index] = fd;
	if (command == DMA_BUF_IOCTL_SYNC)
		flags_seen[index] = ((struct dma_buf_sync *)argument)->flags;
	if (calls == fail_at) {
		errno = injected_error;
		return -1;
	}
	if (command == IOCTL_CCD_WORKER_WRITE)
		sent = *(struct ccd_worker_item *)argument;
	else if (command == IOCTL_CCD_WORKER_READ)
		assert(empty_read); /* The zeroed envelope is intentionally untouched. */
	else
		assert(command == DMA_BUF_IOCTL_SYNC);
	return 0;
}

#define ioctl fake_ioctl
#include "mt6878-camera-ccd-worker.c"
#undef ioctl

static void reset(struct mt6878_ccd_composer_session *session,
	struct ccd_worker_item *request, unsigned int failure, int error)
{
	memset(session, 0, sizeof(*session));
	memset(request, 0, sizeof(*request));
	memset(&sent, 0, sizeof(sent));
	memset(seen, 0, sizeof(seen));
	calls = 0;
	fail_at = failure;
	injected_error = error;
	empty_read = 0;
	session->session = 3;
	session->created = 1;
	session->configured = 1;
	session->job.sequence = 0x03000001;
	session->mappings.msg_buf.ccd_fd = 11;
	session->mappings.workbuf.ccd_fd = 10;
	request->src = 4;
	request->id = 4;
	request->len = 14;
	request->sbuf[0] = 3;
	request->sbuf[5] = CAM_CMD_FRAME;
	mt6878_cq_put32(request->sbuf + 1, session->job.sequence);
	/* Invalid full-frame size, rejected before accessing any frame mapping. */
	mt6878_cq_put32(request->sbuf + 10, 1);
}

int main(void)
{
	struct mt6878_ccd_composer_session session;
	struct ccd_worker_item request;

	reset(&session, &request, 0, 0);
	assert(!mt6878_ccd_worker_compose_reply(20, &session, &request));
	assert(calls == 5 && seen[4] == IOCTL_CCD_WORKER_WRITE);
	assert(fd_seen[0] == 11 && fd_seen[1] == 10 && fd_seen[4] == 20);
	assert(flags_seen[0] == (DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ));
	assert(flags_seen[1] == (DMA_BUF_SYNC_START | DMA_BUF_SYNC_RW));
	assert(flags_seen[2] == (DMA_BUF_SYNC_END | DMA_BUF_SYNC_RW));
	assert(flags_seen[3] == (DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ));
	assert(sent.len == 75 && sent.sbuf[6] == CAM_CMD_FRAME);
	assert(mt6878_camera_le32(sent.sbuf + 7) == (unsigned int)-ERANGE);
	assert(!mt6878_camera_le32(sent.sbuf + 63));
	/* Both sync START failures are fatal; unwind only successful STARTs. */
	reset(&session, &request, 1, ENOTTY);
	assert(mt6878_ccd_worker_compose_reply(20, &session, &request) == -ENOTTY);
	assert(calls == 1 && !sent.len && !session.frame_started);
	reset(&session, &request, 2, EIO);
	assert(mt6878_ccd_worker_compose_reply(20, &session, &request) == -EIO);
	assert(calls == 3 && !sent.len && !session.frame_started);
	assert(fd_seen[2] == 11 && flags_seen[2] == (DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ));
	/* Failed END never publishes even an error ACK; retain composition failure. */
	reset(&session, &request, 3, EIO);
	assert(mt6878_ccd_worker_compose_reply(20, &session, &request) == -ERANGE);
	assert(calls == 4 && !sent.len && session.frame_started);
	reset(&session, &request, 4, EIO);
	assert(mt6878_ccd_worker_compose_reply(20, &session, &request) == -ERANGE);
	assert(calls == 4 && !sent.len);
	/* Failed publication does not replace the earlier composition failure. */
	reset(&session, &request, 5, EPIPE);
	assert(mt6878_ccd_worker_compose_reply(20, &session, &request) == -ERANGE);
	assert(calls == 5 && !sent.len);
	/* Stale cookie and a latched failure do not enter cache access again. */
	assert(mt6878_ccd_worker_compose_reply(20, &session, &request) == -ERANGE);
	assert(calls == 5);
	reset(&session, &request, 0, 0);
	mt6878_cq_put32(request.sbuf + 1, session.job.sequence - 1);
	assert(mt6878_ccd_worker_compose_reply(20, &session, &request) == -ESTALE);
	assert(!calls && !session.frame_started);
	reset(&session, &request, 0, 0);
	empty_read = 1;
	assert(mt6878_ccd_worker_receive_once(20, &session) == -ENOMSG);
	assert(calls == 1 && seen[0] == IOCTL_CCD_WORKER_READ);
	reset(&session, &request, 1, EINTR);
	assert(mt6878_ccd_worker_receive_once(20, &session) == -EINTR);
	assert(calls == 1); /* Never retry an interrupted receive. */
	puts("CCD caller cache/ACK/receive fault fixtures PASS");
	return 0;
}
