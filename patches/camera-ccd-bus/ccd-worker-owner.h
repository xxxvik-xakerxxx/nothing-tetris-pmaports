/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CCD_WORKER_OWNER_H
#define MT6878_CCD_WORKER_OWNER_H

#include "mt6878-ccd-retire-uapi.h"
struct mt6878_ccd_composer_session;

/* Single registered worker thread, same mm/files as pipeline control thread.
 * Borrowed fd/session/mappings stay alive through registration and retirement.
 * No concurrent step, close, unmap or thread transfer is permitted.
 */
struct mt6878_ccd_worker_owner {
	int fd, first_error;
	unsigned int session, entered, retired, composition_failed;
	unsigned long long generation;
};

int mt6878_ccd_worker_owner_register(struct mt6878_ccd_worker_owner *owner,
	int fd, unsigned int session);
/* One receive/compose/reply or retirement step; no retry loop. After protocol
 * DESTROY, ESHUTDOWN with retired==0 is local closure only: control must begin
 * retirement and schedule another step to query/ACK its ticket before release.
 */
int mt6878_ccd_worker_owner_step(struct mt6878_ccd_worker_owner *owner,
	struct mt6878_ccd_composer_session *session);

#endif
