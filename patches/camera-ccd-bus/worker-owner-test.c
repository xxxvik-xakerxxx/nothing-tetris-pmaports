// SPDX-License-Identifier: GPL-2.0-only
/* Native CI fault fixture; no device, real ioctl or vendor code execution. */
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <sys/ioctl.h>
static int fake_ioctl(int fd, unsigned long command, ...);
#define ioctl fake_ioctl
#include "ccd-worker-owner.c"
#undef ioctl

static int registration_errno, query_errno, ack_errno, receive_result, receive_session_error;
static unsigned int registrations, receives, acknowledgments;
static unsigned long long token = 43;

static int fake_ioctl(int fd, unsigned long command, ...)
{
	va_list ap;
	void *argument;
	int error = 0;

	assert(fd == 9);
	va_start(ap, command);
	argument = va_arg(ap, void *);
	va_end(ap);
	if (command == MT6878_CCD_REGISTER) {
		struct mt6878_ccd_registration *registration = argument;

		registrations++;
		assert(registration->abi == 1 && registration->endpoint_mask == 1);
		registration->generation = 29;
		error = registration_errno;
	} else if (command == MT6878_CCD_RETIRE_QUERY) {
		struct mt6878_ccd_worker_retired *ticket = argument;

		assert(ticket->generation == 29 && ticket->src == 1);
		ticket->token = token;
		error = query_errno;
	} else if (command == MT6878_CCD_RETIRE_ACK) {
		struct mt6878_ccd_worker_retired *ticket = argument;

		assert(ticket->generation == 29 && ticket->token == 43);
		acknowledgments++;
		error = ack_errno;
	} else {
		assert(0);
	}
	errno = error;
	return error ? -1 : 0;
}

int mt6878_ccd_worker_receive_once(int fd, struct mt6878_ccd_composer_session *session)
{
	assert(fd == 9);
	if (session->closed)
		return -ENOTCONN;
	receives++;
	if (receive_session_error)
		session->first_error = receive_session_error;
	return receive_result;
}

int main(void)
{
	struct mt6878_ccd_worker_owner owner = { 0 }, failed = { 0 }, sync_failed = { 0 };
	struct mt6878_ccd_composer_session session = { 0 };
	struct mt6878_ccd_worker_owner destroyed = { 0 }, closed_failed = { 0 };
	struct mt6878_ccd_composer_session closed_session = { .closed = 1 };
	unsigned int previous_receives, previous_acknowledgments;

	registration_errno = EFAULT;
	assert(mt6878_ccd_worker_owner_register(&failed, 9, 0) == -EFAULT);
	assert(mt6878_ccd_worker_owner_register(&failed, 9, 0) == -EFAULT);
	assert(registrations == 1); /* Uncertain registration must not replay. */
	registration_errno = 0;
	assert(mt6878_ccd_worker_owner_register(&owner, 9, 0) == 0);
	assert(mt6878_ccd_worker_owner_register(&owner, 9, 0) == -EALREADY);
	query_errno = EAGAIN;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == 0);
	assert(receives == 1 && acknowledgments == 0);
	receive_result = -ETIMEDOUT;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -ETIMEDOUT);
	assert(!owner.first_error && !session.closed);
	receive_result = -ESHUTDOWN;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -ESHUTDOWN);
	assert(acknowledgments == 0); /* READ closure alone is not retirement proof. */
	receive_result = -EIO;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -EIO);
	assert(owner.first_error == -EIO);
	owner.entered = 1;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -EBUSY);
	owner.entered = 0;
	query_errno = 0;
	token = 0;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -EPROTO);
	assert(owner.first_error == -EIO && !session.closed && acknowledgments == 0);
	token = 43;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -EIO);
	assert(!owner.retired && acknowledgments == 0); /* Failed END cannot certify drain. */
	/* Separate clean-composition fixture for transient kernel ACK rejection. */
	owner.composition_failed = 0;
	owner.first_error = 0;
	ack_errno = EBUSY;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -EBUSY);
	assert(session.closed && !owner.retired && owner.first_error == -EBUSY);
	ack_errno = 0;
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == 0);
	assert(owner.retired && owner.first_error == -EBUSY);
	assert(mt6878_ccd_worker_owner_step(&owner, &session) == -ESHUTDOWN);
	/* Same errno as READ interruption, but frozen composer recorded failed END. */
	session.closed = 0;
	session.first_error = 0;
	assert(mt6878_ccd_worker_owner_register(&sync_failed, 9, 0) == 0);
	query_errno = EAGAIN;
	receive_result = -EINTR;
	receive_session_error = -EINTR;
	assert(mt6878_ccd_worker_owner_step(&sync_failed, &session) == -EINTR);
	assert(sync_failed.composition_failed && sync_failed.first_error == -EINTR);
	query_errno = 0;
	assert(mt6878_ccd_worker_owner_step(&sync_failed, &session) == -EINTR);
	assert(!sync_failed.retired && !session.closed);
	/* Successful protocol DESTROY precedes the control thread's retire_begin.
	 * The next step must not READ or poison an otherwise clean composer.
	 */
	assert(!mt6878_ccd_worker_owner_register(&destroyed, 9, 0));
	query_errno = EAGAIN;
	previous_receives = receives;
	previous_acknowledgments = acknowledgments;
	assert(mt6878_ccd_worker_owner_step(&destroyed, &closed_session) == -ESHUTDOWN);
	assert(receives == previous_receives && acknowledgments == previous_acknowledgments);
	assert(!destroyed.first_error && !destroyed.composition_failed && !destroyed.retired);
	assert(!destroyed.entered && closed_session.closed);
	query_errno = 0;
	assert(!mt6878_ccd_worker_owner_step(&destroyed, &closed_session));
	assert(destroyed.retired && acknowledgments == previous_acknowledgments + 1);
	assert(receives == previous_receives);
	/* Closure must not hide a recorded composition/cache failure. */
	assert(!mt6878_ccd_worker_owner_register(&closed_failed, 9, 0));
	closed_session.first_error = -EINTR;
	query_errno = EAGAIN;
	assert(mt6878_ccd_worker_owner_step(&closed_failed, &closed_session) == -EINTR);
	assert(closed_failed.composition_failed && closed_failed.first_error == -EINTR);
	query_errno = 0;
	assert(mt6878_ccd_worker_owner_step(&closed_failed, &closed_session) == -EINTR);
	assert(!closed_failed.retired && acknowledgments == previous_acknowledgments + 1);
	return 0;
}
