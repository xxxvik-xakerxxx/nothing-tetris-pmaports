// SPDX-License-Identifier: GPL-2.0-only
/* Native caller for the owned bus, not stock libccd registration emulation. */
#include <errno.h>
#include <sys/ioctl.h>
#ifndef __packed
#define __packed __attribute__((packed))
#endif
#include "ccd-worker-owner.h"
#include "mt6878-camera-ccd-composer-session.h"

int mt6878_ccd_worker_receive_once(int fd, struct mt6878_ccd_composer_session *session);

int mt6878_ccd_worker_owner_register(struct mt6878_ccd_worker_owner *owner,
	int fd, unsigned int session)
{
	struct mt6878_ccd_registration registration = {
		.abi = MT6878_CCD_OWNER_ABI,
	};
	int ret;

	if (!owner || fd < 0 || session > 3)
		return -EINVAL;
	if (owner->generation || owner->entered || owner->retired)
		return -EALREADY;
	registration.endpoint_mask = 1U << session;
	/* Caller zero-initializes owner. Failure, including uncertain EFAULT
	 * registration, is terminal: never replay REGISTER on this descriptor.
	 */
	if (owner->first_error)
		return owner->first_error;
	if (ioctl(fd, MT6878_CCD_REGISTER, &registration) < 0) {
		ret = -errno;
		owner->first_error = ret;
		return ret;
	}
	if (!registration.generation) {
		owner->first_error = -EPROTO;
		return owner->first_error;
	}
	owner->fd = fd;
	owner->session = session;
	owner->generation = registration.generation;
	return 0;
}

int mt6878_ccd_worker_owner_step(struct mt6878_ccd_worker_owner *owner,
	struct mt6878_ccd_composer_session *session)
{
	struct mt6878_ccd_worker_retired ticket;
	int ret;

	if (!owner || !session || !owner->generation || owner->fd < 0 ||
	    session->session != owner->session)
		return -EINVAL;
	if (owner->entered || owner->retired)
		return owner->retired ? -ESHUTDOWN : -EBUSY;
	owner->entered = 1;
	/* Check retirement BEFORE dispatch, also after a previous composer error.
	 * Real ioctl is nonblocking; no externally supplied "quiescent" callback.
	 */
	ticket = (struct mt6878_ccd_worker_retired) {
		.generation = owner->generation,
		.src = owner->session + CCD_IPI_ISP_MAIN,
	};
	if (ioctl(owner->fd, MT6878_CCD_RETIRE_QUERY, &ticket) < 0) {
		ret = -errno;
		if (ret != -EAGAIN)
			goto fail;
		if (owner->first_error) {
			ret = owner->first_error;
			goto out;
		}
		/* Protocol DESTROY can finish before control starts retirement. Do not
		 * turn that clean closure into a composer failure on the next step.
		 * Still QUERY on later steps: only the real ticket authorizes ACK.
		 */
		if (session->closed && !session->first_error) {
			ret = -ESHUTDOWN;
			goto out;
		}
		ret = mt6878_ccd_worker_receive_once(owner->fd, session);
		if (session->first_error) {
			/* A syscall-shaped errno can originate in cache END/WRITE, not
			 * READ interruption. Frozen composer records that distinction.
			 */
			owner->composition_failed = 1;
			ret = session->first_error;
			goto fail;
		}
		/* Closure can wake READ mid-step. Return without ACK; next explicit
		 * step queries the actual token, after the call stack/cache sync drains.
		 */
		if (ret == -ETIMEDOUT || ret == -EINTR || ret == -ESHUTDOWN)
			goto out;
		if (ret) {
			/* Frozen worker error cannot distinguish failed cache END from a
			 * parser fault. Do not certify safe mapping release in either case.
			 */
			owner->composition_failed = 1;
			goto fail;
		}
		goto out;
	}
	if (!ticket.token || ticket.generation != owner->generation ||
	    ticket.src != owner->session + CCD_IPI_ISP_MAIN || ticket.reserved) {
		ret = -EPROTO;
		goto fail;
	}
	if (owner->composition_failed || session->first_error) {
		ret = owner->first_error ? owner->first_error :
			(session->first_error ? session->first_error : -EIO);
		goto fail;
	}
	/* All composition and DMA_BUF_SYNC_END calls have returned. Closing is
	 * LOCAL dispatch retirement, not a DESTROY/FLUSH ACK or hardware OFF.
	 * Never unmap here: control must verify kernel retirement before release.
	 */
	session->closed = 1;
	if (ioctl(owner->fd, MT6878_CCD_RETIRE_ACK, &ticket) < 0) {
		ret = -errno;
		goto fail;
	}
	owner->retired = 1;
	ret = 0;
	goto out;
fail:
	if (!owner->first_error)
		owner->first_error = ret;
out:
	owner->entered = 0;
	return ret;
}
