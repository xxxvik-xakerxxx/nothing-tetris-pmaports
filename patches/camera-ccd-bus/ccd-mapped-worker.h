/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CCD_MAPPED_WORKER_H
#define MT6878_CCD_MAPPED_WORKER_H

#ifndef __packed
#define __packed __attribute__((packed))
#endif
#include "ccd-worker-owner.h"
#include "mt6878-camera-ccd-composer-session.h"

struct mt6878_ccd_mapped_worker {
	struct mt6878_ccd_worker_owner worker;
	struct mt6878_ccd_composer_session session;
	struct mtkcam_ipi_frame_param *scratch;
	unsigned char *work_va, *message_va;
	unsigned int work_size, message_size, prepared, owns_fds, work_mapped, message_mapped;
	int work_fd, message_fd, first_error, cleanup_error;
};

/* Zero-initialized, one-job owner. Inputs MUST come from the kernel pipeline's
 * validated DMA-BUF exports, actual job and resource snapshot. fstat checks
 * length/aliasing, not DMA-BUF type or IOVA provenance. Never supply a guessed
 * address or regular file as a capture buffer. No VA is accessed here: frozen
 * worker's real DMA_BUF_SYNC brackets own all subsequent composition access.
 * Message is mapped read-only; work is read/write. No duplicate frame/recipe
 * implementation or stock libccd dependency is introduced.
 * Successful input validation transfers both fd numbers, unchanged, to this
 * owner. No concurrent close/dup2/fd transfer/prepare/step/release is allowed.
 */
int mt6878_ccd_mapped_worker_prepare(struct mt6878_ccd_mapped_worker *owner,
	unsigned int session, const struct mtkcam_ipi_session_param *mappings,
	const struct mt6878_camsv_recipe_resources *resources,
	const struct mt6878_camsv_job *job);

/* Register/step using the existing APIs and embedded worker/session directly:
 * mt6878_ccd_worker_owner_register(&owner->worker, ccd_fd, session);
 * mt6878_ccd_worker_owner_step(&owner->worker, &owner->session);
 * CCD fd is borrowed, buffer fds are owned. Registration uncertainty or any
 * composition/cache error retains mappings. Release is CPU-only; real worker
 * retirement must precede it once registered. Kernel DMA stop is separate.
 */
int mt6878_ccd_mapped_worker_release(struct mt6878_ccd_mapped_worker *owner);

#endif
