/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_frame_worker.h"
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <sys/eventfd.h>
#include <unistd.h>

static void fail(struct b41_frame_worker *w, int error)
{
    int zero = 0;
    atomic_compare_exchange_strong(&w->failure, &zero, error);
}
static void *run(void *context)
{
    struct b41_frame_worker *w = context;
    struct pollfd wake = {w->wake_fd, POLLIN, 0};
    struct b41_host_event event;
    int done = w->done_fd;
    uint64_t value;
    while (!atomic_load_explicit(&w->stop_requested, memory_order_acquire)) {
        int status = b41_host_adapter_error(w->adapter);
        if (status) { fail(w, status); break; }
        status = b41_host_adapter_take(w->adapter, &event);
        if (!status) {
            /* Only proven frame-request events; other output has a different
             * owner and is rejected, never silently consumed as a successful TX.
             */
            status = b41_agps_owner_send_event(w->ipc, &event);
            if (status) { fail(w, status); break; }
            continue;
        }
        if (status != -EAGAIN && status != -EBUSY) { fail(w, status); break; }
        /* Frozen callback queue has no wake hook. This25ms idle drain policy
         * is new host scheduling, not an OEM delay or hardware retry.
         */
        int ready = poll(&wake, 1, 25);
        if (ready < 0 && errno != EINTR) { fail(w, -errno); break; }
        if (ready > 0) {
            if (wake.revents & (POLLERR | POLLHUP | POLLNVAL)) { fail(w, -EIO); break; }
            if (read(wake.fd, &value, sizeof(value)) < 0 && errno != EAGAIN && errno != EINTR) {
                fail(w, -errno); break;
            }
        }
    }
    /* Last access to owner occurs BEFORE publication. Detached thread does
     * not touch w/adapter/ipc after this syscall, including during its epilogue.
     * A failed publication is caught by controller's deadline/quarantine.
     */
    value = 1;
    (void)write(done, &value, sizeof(value));
    return NULL;
}
int b41_frame_worker_start(struct b41_frame_worker *w,
    struct b41_host_adapter *adapter, struct b41_agps_owner *ipc,
    int *fds, unsigned count)
{
    struct stat identity[2];
    pthread_attr_t attr;
    pthread_t thread;
    int status, wake, done;
    if (!w || !adapter || !ipc || !ipc->initialized || count > 2 || (count && !fds))
        return -EINVAL;
    if (w->state != B41_WORKER_FRESH) return -EALREADY;
    if (ipc->state != B41_AGPS_OWNED) return -ENODATA;
    for (unsigned i = 0; i < count; ++i) {
        if (fds[i] < 0 || fds[i] == ipc->fd || (i && fds[0] == fds[1])) return -EINVAL;
        if (fstat(fds[i], &identity[i])) return -errno;
    }
    wake = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
    if (wake < 0) return -errno;
    done = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
    if (done < 0) { status = -errno; (void)close(wake); return status; }
    status = pthread_attr_init(&attr);
    if (status) { (void)close(wake); (void)close(done); return -status; }
    status = pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    w->adapter = adapter; w->ipc = ipc; w->wake_fd = wake; w->done_fd = done;
    w->exposed = 0; w->receiver_count = count;
    atomic_init(&w->stop_requested, 0); atomic_init(&w->failure, 0);
    for (unsigned i = 0; i < count; ++i) { w->receiver[i] = fds[i]; w->identity[i] = identity[i]; }
    if (!status) status = pthread_create(&thread, &attr, run, w);
    (void)pthread_attr_destroy(&attr);
    if (status) { (void)close(wake); (void)close(done); return -status; }
    for (unsigned i = 0; i < count; ++i) fds[i] = -1;
    w->state = B41_WORKER_RUNNING;
    return 0;
}
int b41_frame_worker_expose(struct b41_frame_worker *w)
{
    if (!w || w->state != B41_WORKER_RUNNING) return -EINVAL;
    w->exposed = 1;
    return 0;
}
static int remaining(const struct timespec *deadline)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
    if (deadline->tv_sec < now.tv_sec ||
        (deadline->tv_sec == now.tv_sec && deadline->tv_nsec <= now.tv_nsec)) return 0;
    if (deadline->tv_sec - now.tv_sec >= INT_MAX / 1000) return -ERANGE;
    long long ns = (long long)(deadline->tv_sec - now.tv_sec) * 1000000000 + deadline->tv_nsec - now.tv_nsec;
    return (int)((ns + 999999) / 1000000);
}
int b41_frame_worker_quiesce(struct b41_frame_worker *w, const struct timespec *deadline)
{
    struct pollfd done;
    uint64_t one = 1;
    int status = 0;
    if (!w || !deadline || deadline->tv_sec < 0 || deadline->tv_nsec < 0 || deadline->tv_nsec >= 1000000000)
        return -EINVAL;
    if (w->state == B41_WORKER_QUARANTINED) {
        status = atomic_load(&w->failure);
        return status ? status : -EBUSY;
    }
    if (w->state != B41_WORKER_RUNNING) return -EALREADY;
    atomic_store_explicit(&w->stop_requested, 1, memory_order_release);
    if (write(w->wake_fd, &one, sizeof(one)) < 0 && errno != EAGAIN) status = -errno;
    done = (struct pollfd){w->done_fd, POLLIN, 0};
    while (!status) {
        int ms = remaining(deadline);
        if (ms < 0) { status = ms; break; }
        int ready = poll(&done, 1, ms);
        if (ready < 0) { if (errno == EINTR) continue; status = -errno; break; }
        if (ready && (done.revents & (POLLERR | POLLHUP | POLLNVAL))) { status = -EIO; break; }
        if (ready && (done.revents & POLLIN)) break;
        if (ready) { status = -EIO; break; }
        if (!remaining(deadline)) { status = -ETIMEDOUT; break; }
    }
    int worker_error = atomic_load(&w->failure);
    if (worker_error) status = worker_error;
    if (status || w->exposed) {
        if (status) fail(w, status);
        w->state = B41_WORKER_QUARANTINED;
        return status ? status : -EBUSY;
    }
    w->state = B41_WORKER_QUIESCED;
    return 0;
}
int b41_frame_worker_release_unused(struct b41_frame_worker *w)
{
    int status = 0;
    if (!w || w->state != B41_WORKER_QUIESCED || w->exposed) return -EPERM;
    /* Validate ALL retained fd identities before any close; never close a
     * replaced fd. Exclusive ownership is a precondition (no external close).
     */
    for (unsigned i = 0; i < w->receiver_count; ++i) {
        struct stat current;
        if (fstat(w->receiver[i], &current)) { status = -errno; break; }
        if (current.st_dev != w->identity[i].st_dev || current.st_ino != w->identity[i].st_ino ||
            current.st_mode != w->identity[i].st_mode || current.st_rdev != w->identity[i].st_rdev) {
            status = -ESTALE; break;
        }
    }
    if (status) { fail(w, status); w->state = B41_WORKER_QUARANTINED; return status; }
    for (unsigned i = 0; i < w->receiver_count; ++i) {
        if (close(w->receiver[i]) && !status) status = -errno;
        w->receiver[i] = -1; /* Never retry close(EINTR). */
        if (status) break;
    }
    if (status) { fail(w, status); w->state = B41_WORKER_QUARANTINED; return status; }
    int ipc_error = b41_agps_owner_stop(w->ipc);
    if (!status) status = ipc_error;
    if (status) { fail(w, status); w->state = B41_WORKER_QUARANTINED; return status; }
    if (close(w->wake_fd)) status = -errno;
    w->wake_fd = -1;
    if (status) { fail(w, status); w->state = B41_WORKER_QUARANTINED; return status; }
    if (close(w->done_fd)) status = -errno;
    w->done_fd = -1;
    w->state = status ? B41_WORKER_QUARANTINED : B41_WORKER_RELEASED;
    if (status) fail(w, status);
    return status;
}
