/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "b41_native_receiver_host.h"
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <string.h>
#include <sys/eventfd.h>
#include <sys/wait.h>
#include <unistd.h>

static _Atomic(struct b41_native_control *) bound;
static int snapshot(const struct b41_library_association *image,
    struct b41_native_stop_snapshot *out);
_Static_assert(sizeof(struct b41_native_thread_record) == 32, "B4.1 thread table stride");

static int control_fail(struct b41_native_control *c, int status)
{
    int expected = 0;
    atomic_compare_exchange_strong(&c->first_error, &expected, status);
    return atomic_load(&c->first_error);
}

int b41_native_control_init(struct b41_native_control *c)
{
    int fd;
    if (!c) return -EINVAL;
    if (c->initialized) return -EALREADY;
    fd = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
    if (fd < 0) return -errno;
    c->fd = fd;
    atomic_init(&c->pending, 0);
    atomic_init(&c->first_error, 0);
    c->initialized = 1;
    return 0;
}

static int32_t native_notify(uint32_t event)
{
    struct b41_native_control *c = atomic_load(&bound);
    unsigned notice;
    uint64_t one = 1;
    int status = 0;
    if (!c) return -ENODEV;
    switch (event) {
    case 0: notice = B41_NATIVE_REPORT; break;
    case 7: notice = B41_NATIVE_PROHIBITED; break;
    case 13: notice = B41_NATIVE_RESTART; break;
    case 3:
        notice = B41_NATIVE_UNSUPPORTED;
        status = control_fail(c, -EOPNOTSUPP);
        break;
    default:
        /* Pinned5de00: all other selectors have genuine no-action targets. */
        return atomic_load(&c->first_error);
    }
    atomic_fetch_or(&c->pending, notice);
    ssize_t written = write(c->fd, &one, sizeof(one));
    if (written < 0) return control_fail(c, -errno);
    if (written != (ssize_t)sizeof(one)) return control_fail(c, -EIO);
    return status ? status : atomic_load(&c->first_error);
}

int b41_native_control_bind(struct b41_native_control *c,
    struct b41_known_callbacks *callbacks)
{
    struct b41_native_control *expected = NULL;
    if (!c || c->initialized != 1 || !callbacks) return -EINVAL;
    if (!atomic_compare_exchange_strong(&bound, &expected, c)) return -EALREADY;
    callbacks->notify = native_notify;
    return 0;
}

int b41_native_control_discard_unbound(struct b41_native_control *c)
{
    int fd;
    if (!c || c->initialized != 1) return -EINVAL;
    if (atomic_load(&bound) == c) return -EBUSY;
    fd = c->fd;
    c->fd = -1;
    c->initialized = 2;
    return close(fd) ? -errno : 0;
}

int b41_native_control_take(struct b41_native_control *c, unsigned *notices)
{
    uint64_t wake;
    ssize_t received;
    if (!c || c->initialized != 1 || !notices) return -EINVAL;
    received = read(c->fd, &wake, sizeof(wake));
    if (received < 0 && errno != EAGAIN) return control_fail(c, -errno);
    if (received >= 0 && received != (ssize_t)sizeof(wake)) return control_fail(c, -EIO);
    /* An event may arrive between read/exchange. Its extra wake is harmless;
     * pending notices are authoritative, the eventfd is only the poll wake. */
    *notices = atomic_exchange(&c->pending, 0);
    return atomic_load(&c->first_error);
}

int b41_native_join_ack(const struct b41_native_stop_snapshot *before,
    const struct b41_native_stop_snapshot *after, unsigned *joined)
{
    unsigned mask = 0;
    if (!before || !after || !joined || !before->base || before->base != after->base ||
        before->base > UINTPTR_MAX - B41_LIBRARY_IMAGE_END)
        return -EINVAL;
    /* Nonzero permits unjoined offload records14/16 at52a190..52a2c0. */
    if (before->offload || after->offload) return -EOPNOTSUPP;
    if (before->threads[0].marker == -1 || before->threads[0].handle == UINT64_MAX)
        return -ENODATA;
    for (unsigned i = 0; i < B41_NATIVE_THREADS; ++i) {
        const struct b41_native_thread_record *a = &before->threads[i], *b = &after->threads[i];
        if (a->marker < -1) return -ESTALE;
        if (a->index != i || b->index != i || a->stop != before->base + 0x529f18u ||
            b->stop != a->stop || a->wake != before->base + 0x529418u ||
            b->wake != a->wake || b->handle != a->handle) return -ESTALE;
        if (a->marker == -1) {
            /* A stale live handle with no admission marker is not proof that
             * an old owner successfully joined it. Never revive such a table. */
            if (a->handle != UINT64_MAX || b->marker != -1) return -ESTALE;
            continue;
        }
        if (a->handle == UINT64_MAX || b->marker != -1) return -EBUSY;
        mask |= 1u << i;
    }
    *joined = mask;
    return 0;
}

static int valid_time(const struct timespec *t)
{
    return t && t->tv_sec >= 0 && t->tv_nsec >= 0 && t->tv_nsec < 1000000000;
}

static int compare_time(const struct timespec *a, const struct timespec *b)
{
    if (a->tv_sec != b->tv_sec) return a->tv_sec < b->tv_sec ? -1 : 1;
    return a->tv_nsec < b->tv_nsec ? -1 : a->tv_nsec != b->tv_nsec;
}

int b41_native_child_wait(pid_t child, const struct timespec *deadline,
    const struct timespec *cleanup_deadline, int *wait_status)
{
    struct timespec now;
    int escalated = 0, status;
    if (child <= 0 || !wait_status || !valid_time(deadline) ||
        !valid_time(cleanup_deadline) || compare_time(cleanup_deadline, deadline) < 0)
        return -EINVAL;
    for (;;) {
        pid_t result = waitpid(child, &status, WNOHANG);
        if (result == child) {
            *wait_status = status;
            if (escalated) return -ETIMEDOUT;
            return WIFEXITED(status) && !WEXITSTATUS(status) ? 0 : -ECHILD;
        }
        if (result < 0) return -errno;
        if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
        if (compare_time(&now, escalated ? cleanup_deadline : deadline) >= 0) {
            if (escalated) return -EINPROGRESS;
            /* waitpid0 establishes it is our unreaped child; exclusive parent
             * ownership prevents PID reuse between this check and signal. */
            if (kill(child, SIGKILL) && errno != ESRCH) return -errno;
            escalated = 1;
            continue;
        }
        const struct timespec *limit = escalated ? cleanup_deadline : deadline;
        int ms = 25;
        if (limit->tv_sec - now.tv_sec <= 1) {
            long long ns = (long long)(limit->tv_sec - now.tv_sec) * 1000000000 +
                limit->tv_nsec - now.tv_nsec;
            int remaining = (int)((ns + 999999) / 1000000);
            if (remaining < ms) ms = remaining;
        }
        if (poll(NULL, 0, ms) < 0 && errno != EINTR) return -errno;
    }
}

int b41_native_session_execute(const struct b41_library_association *image,
    const struct b41_engine_arguments *arguments, struct b41_native_control *control,
    struct b41_frame_worker *worker, struct b41_native_stop_owner *stop,
    const struct timespec *run_deadline, const struct timespec *worker_deadline,
    struct b41_native_session_result *result)
{
#if !defined(__aarch64__) || !defined(__BIONIC__)
    (void)image; (void)arguments; (void)control; (void)worker; (void)stop;
    (void)run_deadline; (void)worker_deadline; (void)result;
    return -EOPNOTSUPP;
#else
    struct b41_native_stop_snapshot mapping;
    struct timespec now;
    struct pollfd pollset[2];
    int status, reason = 0;
    unsigned notices;
    uint32_t primary;
    if (!arguments || !control || !worker || !stop || !result ||
        !valid_time(run_deadline) || !valid_time(worker_deadline) ||
        compare_time(worker_deadline, run_deadline) < 0) return -EINVAL;
    if (arguments->missing_contracts) return -EOPNOTSUPP;
    if (atomic_load(&bound) != control || control->initialized != 1 ||
        arguments->callbacks.notify != native_notify ||
        worker->state != B41_WORKER_RUNNING || !worker->exposed ||
        !worker->adapter || stop->state != B41_NATIVE_STOP_EMPTY) return -EPERM;
    const struct b41_engine_callback_table *c = &arguments->callbacks;
    if (!c->output || !c->app_output || !c->frame_sleep || !c->frame_network || !c->frame_measurement ||
        !c->agps || !c->passthrough || !c->encode || !c->decode) return -EINVAL;
    for (unsigned i = 0; i < 14; ++i) if (c->optional_null[i]) return -EOPNOTSUPP;
    if (!worker->receiver_count || worker->receiver_count > 2) return -EINVAL;
    if (control->fd < 0 || worker->done_fd < 0) return -EBADF;
    primary = (uint32_t)arguments->second[0x10] | (uint32_t)arguments->second[0x11] << 8 |
        (uint32_t)arguments->second[0x12] << 16 | (uint32_t)arguments->second[0x13] << 24;
    if (worker->receiver[0] < 0 || primary != (uint32_t)worker->receiver[0]) return -ESTALE;
    if (worker->receiver_count == 2) {
        uint32_t secondary = (uint32_t)arguments->second[0x14] |
            (uint32_t)arguments->second[0x15] << 8 | (uint32_t)arguments->second[0x16] << 16 |
            (uint32_t)arguments->second[0x17] << 24;
        if (worker->receiver[1] < 0 || secondary != (uint32_t)worker->receiver[1]) return -ESTALE;
    }
    if (memcmp(arguments->second + 0x1cc, "UseCallback", 11) || arguments->second[0x1d7])
        return -EOPNOTSUPP;
    /* Actual first+68 host/offload policy, not a caller-invented mode flag. */
    for (unsigned i = 0x68; i < 0x6c; ++i)
        if (arguments->first[i]) return -EOPNOTSUPP;
    status = snapshot(image, &mapping);
    if (status) return status;
    if (mapping.offload) return -EOPNOTSUPP;
    for (unsigned i = 0; i < B41_NATIVE_THREADS; ++i)
        if (mapping.threads[i].marker != -1 || mapping.threads[i].handle != UINT64_MAX ||
            mapping.threads[i].index != i || mapping.threads[i].stop != image->base + 0x529f18u ||
            mapping.threads[i].wake != image->base + 0x529418u) return -EALREADY;
    status = b41_host_adapter_error(worker->adapter);
    if (status) return status;
    status = atomic_load(&control->first_error);
    if (status) return status;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
    if (compare_time(&now, run_deadline) >= 0) return -ETIMEDOUT;
    memset(result, 0, sizeof(*result));
    /* ABI52f9d0 / mnld61444 and run52e2bc / mnld63c30..63c40. */
    uint32_t (*registration)(const void *) =
        (uint32_t (*)(const void *))(image->base + 0x52f9d0u);
    uint32_t (*run)(const void *, const void *) =
        (uint32_t (*)(const void *, const void *))(image->base + 0x52e2bcu);
    result->registration_entered = 1;
    if (registration(&arguments->callbacks)) return -EPROTO;
    result->run_entered = 1;
    result->run_status = run(arguments->first, arguments->second);
    /* Partial initialization may have retained threads; do not invoke a
     * guessed partial-stop path. Parent supervises process exit/quarantine. */
    if (result->run_status != 18) return -EPROTO;
    pollset[0] = (struct pollfd){control->fd, POLLIN, 0};
    pollset[1] = (struct pollfd){worker->done_fd, POLLIN, 0};
    for (;;) {
        notices = 0;
        reason = b41_host_adapter_error(worker->adapter);
        if (!reason) reason = atomic_load(&worker->failure);
        if (!reason) reason = b41_native_control_take(control, &notices);
        result->notices |= notices;
        if (reason) break;
        if (notices & B41_NATIVE_PROHIBITED) { reason = -EPERM; break; }
        if (notices & B41_NATIVE_RESTART) { reason = -ECONNRESET; break; }
        if (clock_gettime(CLOCK_MONOTONIC, &now)) { reason = -errno; break; }
        if (compare_time(&now, run_deadline) >= 0) break;
        int ms = 25;
        if (run_deadline->tv_sec - now.tv_sec <= 1) {
            long long ns = (long long)(run_deadline->tv_sec - now.tv_sec) * 1000000000 +
                run_deadline->tv_nsec - now.tv_nsec;
            int remaining = (int)((ns + 999999) / 1000000);
            if (remaining < ms) ms = remaining;
        }
        if (poll(pollset, 2, ms) < 0) { reason = -errno; break; }
        if (pollset[0].revents & (POLLERR | POLLHUP | POLLNVAL)) { reason = -EIO; break; }
        if (pollset[1].revents) {
            reason = atomic_load(&worker->failure);
            if (!reason) reason = -ESHUTDOWN;
            break;
        }
    }
    /* Capture actual live records at STOP admission, not immediately after
     * init returns while a successfully created thread may still be starting. */
    result->native_stop_status = b41_native_stop_capture(stop, image);
    if (!result->native_stop_status)
        result->native_stop_status = b41_native_stop_call(stop, &result->joined_threads);
    /* Keep output service alive during native stop/timer callbacks. Exposed
     * worker always retains resources; propagate its quarantine, not reset. */
    result->worker_stop_status = b41_frame_worker_quiesce(worker, worker_deadline);
    if (reason) return reason;
    if (result->native_stop_status) return result->native_stop_status;
    return result->worker_stop_status;
#endif
}

static int snapshot(const struct b41_library_association *image,
    struct b41_native_stop_snapshot *out)
{
    uintptr_t flag;
    struct b41_native_stop_snapshot result;
    if (!image || !out || !image->base || image->extent != B41_LIBRARY_IMAGE_END ||
        image->base > UINTPTR_MAX - image->extent) return -EINVAL;
    memcpy(&flag, (const void *)(image->base + 0x6e6d00u), sizeof(flag));
    if (flag != image->base + 0x6fa3d8u) return -ESTALE;
    result.base = image->base;
    memcpy(&result.offload, (const void *)flag, sizeof(result.offload));
    memcpy(result.threads, (const void *)(image->base + 0x6edef0u), sizeof(result.threads));
    *out = result;
    return 0;
}

int b41_native_stop_capture(struct b41_native_stop_owner *owner,
    const struct b41_library_association *image)
{
    struct b41_native_stop_snapshot current;
    int status;
    if (!owner) return -EINVAL;
    if (owner->state != B41_NATIVE_STOP_EMPTY) return -EALREADY;
    status = snapshot(image, &current);
    if (status) return status;
    if (current.offload) return -EOPNOTSUPP;
    if (current.threads[0].marker == -1 || current.threads[0].handle == UINT64_MAX)
        return -ENODATA;
    for (unsigned i = 0; i < B41_NATIVE_THREADS; ++i) {
        const struct b41_native_thread_record *r = &current.threads[i];
        if (r->marker < -1) return -ESTALE;
        if (r->index != i || r->stop != current.base + 0x529f18u ||
            r->wake != current.base + 0x529418u) return -ESTALE;
        if ((r->marker == -1) != (r->handle == UINT64_MAX)) return -ESTALE;
    }
    owner->before = current;
    owner->image = *image;
    owner->controller = pthread_self();
    owner->first_error = 0;
    owner->state = B41_NATIVE_STOP_CAPTURED;
    return 0;
}

int b41_native_stop_call(struct b41_native_stop_owner *owner, unsigned *joined)
{
#if !defined(__aarch64__) || !defined(__BIONIC__)
    (void)owner;
    (void)joined;
    return -EOPNOTSUPP;
#else
    struct b41_native_stop_snapshot after;
    int status;
    if (!owner || !joined) return -EINVAL;
    if (owner->state != B41_NATIVE_STOP_CAPTURED) return -EALREADY;
    if (!pthread_equal(owner->controller, pthread_self())) return -EPERM;
    owner->state = B41_NATIVE_STOP_ENTERED;
    /* AArch64 no-argument export52e2c0. Its residual w0 is not a join result.
     * Process watchdog, not cancellation of this thread, bounds supervisor wait. */
    void (*native_stop)(void) = (void (*)(void))(owner->image.base + 0x52e2c0u);
    native_stop();
    status = snapshot(&owner->image, &after);
    if (!status) status = b41_native_join_ack(&owner->before, &after, joined);
    owner->first_error = status;
    owner->state = status ? B41_NATIVE_STOP_QUARANTINED : B41_NATIVE_STOP_ACKED;
    return status;
#endif
}
