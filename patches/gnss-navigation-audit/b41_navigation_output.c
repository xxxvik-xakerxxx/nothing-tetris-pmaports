/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "b41_navigation_output.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
static _Atomic(struct b41_navigation_output *) bound_output;
static int identity_matches(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
        a->st_rdev == b->st_rdev && a->st_mode == b->st_mode;
}
int b41_navigation_output_take(struct b41_navigation_output *o, int *app, int *raw)
{
    if (!o || !app || !raw || app == raw || *app < 0 || *raw < 0 || *app == *raw)
        return -EINVAL;
    if (o->state != B41_NAV_OUTPUT_EMPTY || atomic_load(&bound_output) == o) return -EALREADY;
    struct stat identity[2]; int fd[2] = {*app, *raw}, pty[2] = {-1, -1};
    for (unsigned i = 0; i < 2; ++i) {
        if (fstat(fd[i], &identity[i])) return -errno;
        if (S_ISCHR(identity[i].st_mode)) {
            unsigned number;
            if (ioctl(fd[i], TIOCGPTN, &number)) return -ENOTSUP;
            if (number > INT_MAX) return -ERANGE;
            pty[i] = (int)number;
        } else if (!S_ISFIFO(identity[i].st_mode)) return -ENOTSUP;
        int flags = fcntl(fd[i], F_GETFL);
        if (flags < 0) return -errno;
        if ((flags & O_ACCMODE) == O_RDONLY || !(flags & O_NONBLOCK)) return -EACCES;
    }
    if (identity_matches(&identity[0], &identity[1]) && pty[0] == pty[1]) return -EINVAL;
    for (unsigned i = 0; i < 2; ++i) {
        o->fd[i] = fd[i]; o->pty[i] = pty[i]; o->identity[i] = identity[i]; o->delivered[i] = 0;
    }
    o->first_error = 0; o->state = B41_NAV_OUTPUT_OWNED;
    *app = *raw = -1;
    return 0;
}
int b41_navigation_output_bind(struct b41_navigation_output *o)
{
    if (!o || o->state != B41_NAV_OUTPUT_OWNED) return -EINVAL;
    struct b41_navigation_output *expected = NULL;
    if (!atomic_compare_exchange_strong(&bound_output, &expected, o)) return -EALREADY;
    return 0;
}
static int fail(struct b41_navigation_output *o, int error)
{
    if (!o->first_error) o->first_error = error;
    o->state = B41_NAV_OUTPUT_FAILED;
    return o->first_error;
}
/* Per-worker SIGPIPE containment, not process-wide SIG_IGN which would change
 * opaque engine behavior. Consume only a new EPIPE-generated pending signal;
 * preexisting SIGPIPE and the original thread mask remain untouched.
 */
static ssize_t write_stream(int fd, const void *bytes, size_t length, int *error)
{
    sigset_t set, old, pending;
    sigemptyset(&set); sigaddset(&set, SIGPIPE);
    int e = pthread_sigmask(SIG_BLOCK, &set, &old);
    if (e) { *error = -e; return -1; }
    if (sigpending(&pending)) {
        *error = -errno;
        e = pthread_sigmask(SIG_SETMASK, &old, NULL);
        if (e && !*error) *error = -e;
        return -1;
    }
    int existed = sigismember(&pending, SIGPIPE);
    ssize_t n = write(fd, bytes, length);
    *error = n < 0 ? -errno : n != (ssize_t)length ? -EIO : 0;
    if (*error == -EPIPE && !existed) {
        const struct timespec zero = {0, 0};
        int result = sigtimedwait(&set, NULL, &zero);
        /* If interrupted during drain, retain the blocked mask on the failed
         * private worker until exit; never restore into a pending fatal signal.
         * Preserve EPIPE, not the downstream drain error. No signal retry loop.
         */
        if (result < 0 && errno != EAGAIN) return n;
    }
    e = pthread_sigmask(SIG_SETMASK, &old, NULL);
    if (e && !*error) *error = -e;
    return n;
}
int b41_navigation_dispatch_event(struct b41_agps_owner *agps, const struct b41_host_event *event)
{
    if (!event || !event->length || event->length > B41_HOST_OUTPUT_MAX) return -EMSGSIZE;
    switch (event->kind) {
    case B41_HOST_FRAME_SLEEP: case B41_HOST_FRAME_NETWORK: case B41_HOST_FRAME_MEASUREMENT:
        return b41_agps_owner_send_event(agps, event);
    case B41_HOST_APP_OUTPUT: case B41_HOST_OUTPUT:
        break;
    default:
        return -EOPNOTSUPP;
    }
    struct b41_navigation_output *o = atomic_load(&bound_output);
    if (!o) return -EOPNOTSUPP;
    if (o->first_error) return o->first_error;
    if (o->state != B41_NAV_OUTPUT_OWNED) return fail(o, -EPERM);
    unsigned slot = event->kind == B41_HOST_APP_OUTPUT ? 0 : 1;
    struct stat current;
    if (fstat(o->fd[slot], &current)) return fail(o, -errno);
    if (!identity_matches(&current, &o->identity[slot])) return fail(o, -ESTALE);
    if (o->pty[slot] >= 0) {
        unsigned number;
        if (ioctl(o->fd[slot], TIOCGPTN, &number)) return fail(o, -errno);
        if (number != (unsigned)o->pty[slot]) return fail(o, -ESTALE);
    }
    int flags = fcntl(o->fd[slot], F_GETFL);
    if (flags < 0) return fail(o, -errno);
    if (!(flags & O_NONBLOCK) || (flags & O_ACCMODE) == O_RDONLY) return fail(o, -EACCES);
    int error;
    ssize_t written = write_stream(o->fd[slot], event->bytes, event->length, &error);
    if (written > 0) o->delivered[slot] += (uint64_t)written;
    /* No retry or replay after partial delivery/backpressure; preserve causal
     * failure and retain both sinks until process exit. Worker stops normally.
     */
    return error ? fail(o, error) : 0;
}
