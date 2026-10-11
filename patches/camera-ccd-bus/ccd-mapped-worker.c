// SPDX-License-Identifier: GPL-2.0-only
/* Process-local mmap ownership for the existing native CCD composer. */
#include <errno.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include "ccd-mapped-worker.h"

static void cleanup_error(struct mt6878_ccd_mapped_worker *owner, int ret)
{
	if (!owner->cleanup_error)
		owner->cleanup_error = ret;
}

int mt6878_ccd_mapped_worker_release(struct mt6878_ccd_mapped_worker *owner)
{
	int ret = 0, fd;

	if (!owner)
		return -EINVAL;
	if (owner->worker.entered || owner->worker.composition_failed || owner->session.first_error ||
	    ((owner->worker.generation || owner->worker.first_error) && !owner->worker.retired))
		return -EBUSY;
	owner->session.closed = 1; /* Local CPU dispatch only, never hardware OFF. */
	if (owner->message_mapped) {
		if (munmap(owner->message_va, owner->message_size) < 0) {
			ret = -errno;
			cleanup_error(owner, ret);
		} else {
			owner->message_va = NULL;
			owner->message_mapped = 0;
			owner->session.message_va = NULL;
		}
	}
	if (owner->work_mapped) {
		if (munmap(owner->work_va, owner->work_size) < 0) {
			if (!ret)
				ret = -errno;
			cleanup_error(owner, -errno);
		} else {
			owner->work_va = NULL;
			owner->work_mapped = 0;
			owner->session.work_va = NULL;
		}
	}
	/* Retain failed munmap state and fds for explicit cleanup, not a silent retry. */
	if (ret)
		return ret;
	free(owner->scratch);
	owner->scratch = NULL;
	owner->session.scratch = NULL;
	owner->prepared = 0;
	if (owner->owns_fds) {
		owner->owns_fds = 0;
		fd = owner->message_fd;
		owner->message_fd = -1;
		if (close(fd) < 0) {
			ret = -errno;
			cleanup_error(owner, ret);
		}
		fd = owner->work_fd;
		owner->work_fd = -1;
		if (close(fd) < 0) {
			if (!ret)
				ret = -errno;
			cleanup_error(owner, -errno);
		}
		/* Linux releases an fd even on close EINTR: never retry its number. */
	}
	return ret;
}

int mt6878_ccd_mapped_worker_prepare(struct mt6878_ccd_mapped_worker *owner,
	unsigned int session, const struct mtkcam_ipi_session_param *mappings,
	const struct mt6878_camsv_recipe_resources *resources,
	const struct mt6878_camsv_job *job)
{
	struct mtkcam_ipi_session_param snapshot;
	struct stat work, message;
	void *va;
	int ret, unwind;

	if (!owner || !mappings || !resources || !job || session > 3 ||
	    mappings->workbuf.ccd_fd > 0x7fffffff || mappings->msg_buf.ccd_fd > 0x7fffffff ||
	    mappings->workbuf.ccd_fd == mappings->msg_buf.ccd_fd ||
	    !mappings->workbuf.size || mappings->msg_buf.size < sizeof(*owner->scratch))
		return -EINVAL;
	if (owner->prepared || owner->owns_fds || owner->work_mapped || owner->message_mapped ||
	    owner->worker.generation || owner->worker.first_error || owner->worker.entered ||
	    owner->worker.retired)
		return -EBUSY;
	if (owner->first_error)
		return owner->first_error;
	snapshot = *mappings; /* Preserve metadata before taking ownership of fds. */
	if (fstat((int)snapshot.workbuf.ccd_fd, &work) < 0 ||
	    fstat((int)snapshot.msg_buf.ccd_fd, &message) < 0)
		return -errno;
	if (work.st_size < 0 || message.st_size < 0 ||
	    (unsigned long long)work.st_size < snapshot.workbuf.size ||
	    (unsigned long long)message.st_size < snapshot.msg_buf.size ||
	    (work.st_dev == message.st_dev && work.st_ino == message.st_ino))
		return -ERANGE;
	owner->work_fd = (int)snapshot.workbuf.ccd_fd;
	owner->message_fd = (int)snapshot.msg_buf.ccd_fd;
	owner->work_size = snapshot.workbuf.size;
	owner->message_size = snapshot.msg_buf.size;
	owner->owns_fds = 1;
	va = mmap(NULL, owner->work_size, PROT_READ | PROT_WRITE, MAP_SHARED, owner->work_fd, 0);
	if (va == MAP_FAILED) {
		ret = -errno;
		goto fail;
	}
	owner->work_va = va;
	owner->work_mapped = 1;
	va = mmap(NULL, owner->message_size, PROT_READ, MAP_SHARED, owner->message_fd, 0);
	if (va == MAP_FAILED) {
		ret = -errno;
		goto fail;
	}
	owner->message_va = va;
	owner->message_mapped = 1;
	/* calloc provides actual alignment for the unpacked ABI frame, not a cast
	 * from a packed/alignment-one scratch array. No frame copy is introduced.
	 */
	owner->scratch = calloc(1, sizeof(*owner->scratch));
	if (!owner->scratch) {
		ret = -ENOMEM;
		goto fail;
	}
	ret = mt6878_ccd_composer_prepare(&owner->session, session, &snapshot,
		owner->work_va, owner->message_va, owner->scratch, resources, job);
	if (ret)
		goto fail;
	owner->prepared = 1;
	return 0;
fail:
	owner->first_error = ret;
	unwind = mt6878_ccd_mapped_worker_release(owner);
	if (unwind)
		cleanup_error(owner, unwind);
	return ret;
}
