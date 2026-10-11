// SPDX-License-Identifier: GPL-2.0-only
/* CI native mapping/dispatch integration. Real memfd/mmap, synthetic DMA sync
 * and CCD syscalls. No camera hardware, actual exporter or vendor ELF executed.
 */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/dma-buf.h>
#include <unistd.h>
#define main frozen_recipe_test_main
#include "../camera-ccd-cq/recipe-test.c"
#undef main
#include "ccd-mapped-worker.h"

static unsigned int mmap_calls, mmap_fail, unmap_fail, sync_calls, retire_query;
static unsigned int reads, writes, retire_acks;
static struct ccd_worker_item incoming, outgoing;

static void *test_mmap(void *addr, size_t size, int prot, int flags, int fd, off_t offset)
{
	if (++mmap_calls == mmap_fail) {
		errno = ENOMEM;
		return MAP_FAILED;
	}
	return mmap(addr, size, prot, flags, fd, offset);
}

static int test_munmap(void *addr, size_t size)
{
	if (unmap_fail) {
		unmap_fail = 0;
		errno = EIO;
		return -1;
	}
	return munmap(addr, size);
}

static int test_ioctl(int fd, unsigned long command, ...)
{
	va_list ap;
	void *arg;

	va_start(ap, command);
	arg = va_arg(ap, void *);
	va_end(ap);
	if (command == DMA_BUF_IOCTL_SYNC) {
		assert(fcntl(fd, F_GETFD) >= 0);
		sync_calls++;
	} else if (command == IOCTL_CCD_WORKER_READ) {
		reads++;
		*(struct ccd_worker_item *)arg = incoming;
	} else if (command == IOCTL_CCD_WORKER_WRITE) {
		writes++;
		outgoing = *(struct ccd_worker_item *)arg;
	} else if (command == MT6878_CCD_REGISTER) {
		((struct mt6878_ccd_registration *)arg)->generation = 71;
	} else if (command == MT6878_CCD_RETIRE_QUERY) {
		if (!retire_query) {
			errno = EAGAIN;
			return -1;
		}
		((struct mt6878_ccd_worker_retired *)arg)->token = 93;
	} else {
		assert(command == MT6878_CCD_RETIRE_ACK);
		assert(((struct mt6878_ccd_worker_retired *)arg)->token == 93);
		retire_acks++;
	}
	return 0;
}

#define mmap test_mmap
#define munmap test_munmap
#include "ccd-mapped-worker.c"
#undef mmap
#undef munmap
#define ioctl test_ioctl
#include "ccd-worker-owner.c"
#include "../camera-ccd-cq/mt6878-camera-ccd-worker.c"
#undef ioctl

static void buffers(struct mtkcam_ipi_session_param *mappings)
{
	int work = memfd_create("ccd-fixture-work", MFD_CLOEXEC);
	int message = memfd_create("ccd-fixture-message", MFD_CLOEXEC);

	assert(work >= 0 && message >= 0);
	assert(!ftruncate(work, 1024));
	assert(!ftruncate(message, sizeof(struct mtkcam_ipi_frame_param)));
	memset(mappings, 0, sizeof(*mappings));
	mappings->workbuf.ccd_fd = (unsigned int)work;
	mappings->msg_buf.ccd_fd = (unsigned int)message;
	mappings->workbuf.size = 1024;
	mappings->msg_buf.size = sizeof(struct mtkcam_ipi_frame_param);
	mappings->workbuf.iova = 0x300000000ULL; /* Existing recipe's synthetic fixture only. */
	mmap_calls = mmap_fail = unmap_fail = sync_calls = retire_query = 0;
	reads = writes = retire_acks = 0;
}

static void mapping_faults(struct mt6878_camsv_job *job)
{
	struct mt6878_ccd_mapped_worker owner = { 0 };
	struct mtkcam_ipi_session_param mappings;
	int work, message, alias;

	buffers(&mappings);
	work = mappings.workbuf.ccd_fd;
	message = mappings.msg_buf.ccd_fd;
	assert(!ftruncate(work, sizeof(struct mtkcam_ipi_frame_param)));
	alias = dup(work);
	assert(alias >= 0);
	mappings.msg_buf.ccd_fd = (unsigned int)alias;
	assert(mt6878_ccd_mapped_worker_prepare(&owner, 3, &mappings, &resources, job) == -ERANGE);
	assert(!owner.owns_fds && !mmap_calls);
	assert(!close(alias));
	mappings.msg_buf.ccd_fd = (unsigned int)message;
	mmap_fail = 2;
	assert(mt6878_ccd_mapped_worker_prepare(&owner, 3, &mappings, &resources, job) == -ENOMEM);
	assert(owner.first_error == -ENOMEM && !owner.owns_fds && !owner.work_mapped);
	assert(fcntl(work, F_GETFD) == -1 && errno == EBADF);
	assert(fcntl(message, F_GETFD) == -1 && errno == EBADF);

	memset(&owner, 0, sizeof(owner));
	buffers(&mappings);
	assert(!mt6878_ccd_mapped_worker_prepare(&owner, 3, &mappings, &resources, job));
	unmap_fail = 1;
	assert(mt6878_ccd_mapped_worker_release(&owner) == -EIO);
	assert(owner.cleanup_error == -EIO && owner.owns_fds && owner.message_mapped);
	assert(!owner.work_mapped);
	/* Explicit second cleanup after injected syscall failure, not production retry. */
	assert(!mt6878_ccd_mapped_worker_release(&owner));
	assert(owner.cleanup_error == -EIO && !owner.owns_fds);
}

int main(void)
{
	struct mt6878_ccd_mapped_worker owner = { 0 };
	struct mt6878_camsv_job job;
	struct mtkcam_ipi_config_param config;
	struct mtkcam_ipi_session_param mappings;
	struct mtkcam_ipi_img_output outputs[2] = { 0 };
	struct mtkcam_ipi_frame_param *frame = calloc(1, sizeof(*frame));
	const struct mt6878_camsv_dma_layout *layout;
	const struct mt6878_camsv_buffer *buffer;
	unsigned int i;

	assert(frame);
	setup(&job, &config, 4000, 3000, 5000); /* Reuse frozen, proven fixture construction. */
	mapping_faults(&job);
	buffers(&mappings);
	assert(!mt6878_ccd_mapped_worker_prepare(&owner, 3, &mappings, &resources, &job));
	assert(owner.session.mappings.workbuf.ccd_fd == mappings.workbuf.ccd_fd);
	assert(!mt6878_ccd_worker_owner_register(&owner.worker, 99, 3));
	assert(mt6878_ccd_mapped_worker_release(&owner) == -EBUSY);
	incoming.src = incoming.id = 4;
	incoming.sbuf[0] = 3;
	incoming.sbuf[5] = CAM_CMD_CREATE_SESSION;
	incoming.len = 6 + sizeof(mappings);
	memcpy(incoming.sbuf + 6, &mappings, sizeof(mappings));
	assert(!mt6878_ccd_worker_owner_step(&owner.worker, &owner.session));
	incoming.sbuf[5] = CAM_CMD_CONFIG;
	incoming.len = 6 + sizeof(config);
	memcpy(incoming.sbuf + 6, &config, sizeof(config));
	assert(!mt6878_ccd_worker_owner_step(&owner.worker, &owner.session));
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
	assert(!mt6878_camera_frame(frame, &job, 0, 1024, 1024,
		&outputs[0], &outputs[1]));
	/* Producer publishes backing bytes; worker's message mapping stays read-only. */
	assert(pwrite(owner.message_fd, frame, sizeof(*frame), 0) == (ssize_t)sizeof(*frame));
	free(frame);
	incoming.sbuf[5] = CAM_CMD_FRAME;
	incoming.len = 14;
	mt6878_cq_put32(incoming.sbuf + 1, job.sequence);
	mt6878_cq_put32(incoming.sbuf + 6, 0);
	mt6878_cq_put32(incoming.sbuf + 10, sizeof(struct mtkcam_ipi_frame_param));
	assert(!mt6878_ccd_worker_owner_step(&owner.worker, &owner.session));
	assert(sync_calls == 4 && outgoing.len == 75);
	assert(!mt6878_camera_le32(outgoing.sbuf + 7));
	assert(mt6878_camera_le32(outgoing.sbuf + 63) == 720);
	assert(mt6878_camera_le32(owner.work_va + 708) == MT6878_CQ_END);
	/* Exercise actual frozen FLUSH/DESTROY dispatch, not an injected closed bit. */
	mt6878_cq_put32(incoming.sbuf + 1, 0);
	incoming.len = 6;
	incoming.sbuf[5] = CAM_CMD_FLUSH;
	assert(!mt6878_ccd_worker_owner_step(&owner.worker, &owner.session));
	assert(owner.session.flushed && !owner.session.closed);
	assert(outgoing.sbuf[6] == CAM_CMD_FLUSH);
	incoming.sbuf[5] = CAM_CMD_DESTROY_SESSION;
	assert(!mt6878_ccd_worker_owner_step(&owner.worker, &owner.session));
	assert(owner.session.closed && outgoing.sbuf[6] == CAM_CMD_DESTROY_SESSION);
	assert(reads == 5 && writes == 3 && !retire_acks && sync_calls == 4);
	assert(mt6878_ccd_worker_owner_step(&owner.worker, &owner.session) == -ESHUTDOWN);
	assert(reads == 5 && writes == 3 && !retire_acks && sync_calls == 4);
	assert(!owner.worker.first_error && !owner.worker.composition_failed);
	assert(owner.owns_fds && owner.work_mapped && owner.message_mapped);
	assert(mt6878_ccd_mapped_worker_release(&owner) == -EBUSY);
	retire_query = 1;
	assert(!mt6878_ccd_worker_owner_step(&owner.worker, &owner.session));
	assert(owner.worker.retired && owner.session.closed);
	assert(retire_acks == 1 && reads == 5 && writes == 3);
	assert(!mt6878_ccd_mapped_worker_release(&owner));
	assert(!owner.owns_fds && !owner.scratch && !owner.work_mapped && !owner.message_mapped);
	puts("PASS: native mmap -> existing CCD composer/CQ -> retirement integration (synthetic transport)");
	return 0;
}
