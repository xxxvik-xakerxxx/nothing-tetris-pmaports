/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_agps_receiver.h"
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
#include <stddef.h>
#include <string.h>
#include <sys/eventfd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static int fail(struct b41_agps_receiver *o, int error)
{
    int zero = 0;
    atomic_compare_exchange_strong(&o->first_error, &zero, error);
    return atomic_load(&o->first_error);
}

static int same_fd(const struct b41_agps_receiver *o, unsigned i)
{
    struct stat s;
    if (fstat(o->fd[i], &s)) return -errno;
    const struct stat *saved = &o->identity[i];
    return s.st_dev == saved->st_dev && s.st_ino == saved->st_ino &&
        s.st_mode == saved->st_mode && s.st_rdev == saved->st_rdev ? 0 : -ESTALE;
}

int b41_agps_receiver_open(struct b41_agps_receiver *o, pid_t peer, uid_t uid)
{
    static const char name[] = "mtk_agps2mnl";
    struct sockaddr_un address = {0};
    int status = 0, one = 1;
    _Static_assert(sizeof(address) == 110 && offsetof(struct sockaddr_un, sun_path) == 2,
                   "pinned Linux/Bionic ABI");
    _Static_assert(sizeof(name) + 2 == 15, "abstract name without terminal NUL");
    if (!o || peer <= 0) return -EINVAL;
    if (o->entered) return -EALREADY;
    o->entered = 1;
    for (unsigned i = 0; i < 4; ++i) o->fd[i] = -1;
    atomic_init(&o->stop, 0);
    atomic_init(&o->first_error, 0);
    atomic_init(&o->delivered, 0);
    o->peer_pid = peer; o->peer_uid = uid;
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path + 1, name, sizeof(name) - 1);
    o->fd[0] = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (o->fd[0] < 0) { status = -errno; goto cleanup; }
    if (setsockopt(o->fd[0], SOL_SOCKET, SO_PASSCRED, &one, sizeof(one)) ||
        bind(o->fd[0], (const struct sockaddr *)&address, 15)) {
        status = -errno; goto cleanup;
    }
    for (unsigned i = 1; i < 4; ++i) {
        o->fd[i] = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
        if (o->fd[i] < 0) { status = -errno; goto cleanup; }
    }
    for (unsigned i = 0; i < 4; ++i)
        if (fstat(o->fd[i], &o->identity[i])) { status = -errno; goto cleanup; }
    o->state = B41_AGPS_RX_BOUND;
    return 0;
cleanup:
    for (unsigned i = 0; i < 4; ++i) {
        if (o->fd[i] >= 0) (void)close(o->fd[i]);
        o->fd[i] = -1;
    }
    o->state = B41_AGPS_RX_CLOSED;
    return fail(o, status);
}

static int receive_one(struct b41_agps_receiver *o)
{
    /* Reserve space for unexpected SCM_RIGHTS too: close all received rights,
     * then refuse the message. Linux closes excess rights on MSG_CTRUNC.
     */
    union { struct cmsghdr alignment;
        unsigned char bytes[CMSG_SPACE(sizeof(struct ucred)) + CMSG_SPACE(16 * sizeof(int))];
    } control;
    struct iovec iov = {o->packet, sizeof(o->packet)};
    struct msghdr msg = {0};
    struct ucred peer = {0};
    struct b41_agps_request request;
    unsigned credentials = 0;
    int bad = 0, status = same_fd(o, 0);
    if (status) return status;
    msg.msg_iov = &iov; msg.msg_iovlen = 1;
    msg.msg_control = control.bytes; msg.msg_controllen = sizeof(control.bytes);
    ssize_t n = recvmsg(o->fd[0], &msg, MSG_DONTWAIT | MSG_CMSG_CLOEXEC);
    if (n < 0) return -errno;
    for (struct cmsghdr *c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c)) {
        if (c->cmsg_len < CMSG_LEN(0)) { bad = 1; break; }
        if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS) {
            size_t bytes = c->cmsg_len - CMSG_LEN(0);
            for (size_t i = 0; i < bytes / sizeof(int); ++i) {
                int fd;
                memcpy(&fd, (unsigned char *)CMSG_DATA(c) + i * sizeof(fd), sizeof(fd));
                (void)close(fd);
            }
            bad = 1;
        } else if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_CREDENTIALS &&
                   c->cmsg_len == CMSG_LEN(sizeof(peer))) {
            memcpy(&peer, CMSG_DATA(c), sizeof(peer));
            ++credentials;
        } else bad = 1;
    }
    if (bad || (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) return -EBADMSG;
    if (credentials != 1 || peer.pid != o->peer_pid || peer.uid != o->peer_uid)
        return -EACCES;
    status = b41_agps_receiver_decode(o->packet, (size_t)n, &request);
    if (status) return status;
    if (atomic_load_explicit(&o->stop, memory_order_acquire)) return 0;
    status = b41_agps_native_deliver(&o->image, &request);
    if (!status) atomic_fetch_add(&o->delivered, 1);
    return status;
}

static void *run(void *context)
{
    struct b41_agps_receiver *o = context;
    struct pollfd fds[2] = {{o->fd[3], POLLIN, 0}, {o->fd[1], POLLIN, 0}};
    int done = o->fd[2];
    int active = 0;
    uint64_t one = 1;
    while (!atomic_load_explicit(&o->stop, memory_order_acquire)) {
        int ready = poll(fds, 2, -1);
        if (ready < 0) { if (errno == EINTR) continue; fail(o, -errno); break; }
        if ((fds[0].revents | fds[1].revents) & (POLLERR | POLLHUP | POLLNVAL)) {
            fail(o, -EIO); break;
        }
        if (fds[1].revents & POLLIN) break;
        if (fds[0].revents & POLLIN) {
            if (!active) {
                uint64_t activation;
                ssize_t n = read(fds[0].fd, &activation, sizeof(activation));
                if (n != (ssize_t)sizeof(activation) || activation != 1) { fail(o, -EIO); break; }
                active = 1;
                fds[0].fd = o->fd[0];
                continue;
            }
            int status = receive_one(o);
            if (status && status != -EAGAIN) { fail(o, status); break; }
        }
    }
    /* Last owner and native image access precedes completion publication. */
    ssize_t n = write(done, &one, sizeof(one));
    if (n != (ssize_t)sizeof(one)) fail(o, n < 0 ? -errno : -EIO);
    return NULL;
}

int b41_agps_receiver_prepare(struct b41_agps_receiver *o,
    const void *elf, size_t size, const struct b41_library_view *view)
{
    pthread_attr_t attr;
    pthread_t thread;
    struct b41_library_association image;
    int status;
    if (!o || !o->entered || o->state != B41_AGPS_RX_BOUND) return -EINVAL;
    status = atomic_load(&o->first_error);
    if (status) return status;
    status = b41_agps_native_associate(elf, size, view, &image);
    if (status) return fail(o, status);
    for (unsigned i = 0; i < 4; ++i) {
        status = same_fd(o, i);
        if (status) return fail(o, status);
    }
    o->image = image;
    status = pthread_attr_init(&attr);
    if (status) return fail(o, -status);
    status = pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    if (!status) status = pthread_create(&thread, &attr, run, o);
    (void)pthread_attr_destroy(&attr);
    if (status) return fail(o, -status);
    o->state = B41_AGPS_RX_PREPARED;
    return 1;
}

int b41_agps_receiver_activate(struct b41_agps_receiver *o)
{
    uint64_t one = 1;
    int status;
    if (!o || o->state != B41_AGPS_RX_PREPARED) return -EINVAL;
    status = atomic_load(&o->first_error);
    if (!status) status = b41_agps_native_admit(&o->image);
    if (!status) status = same_fd(o, 3);
    if (status) return fail(o, status);
    ssize_t n = write(o->fd[3], &one, sizeof(one));
    if (n != (ssize_t)sizeof(one)) return fail(o, n < 0 ? -errno : -EIO);
    o->state = B41_AGPS_RX_RUNNING;
    return 0;
}

int b41_agps_receiver_start(struct b41_agps_receiver *o,
    const void *elf, size_t size, const struct b41_library_view *view)
{
    int status = b41_agps_receiver_prepare(o, elf, size, view);
    return status < 0 ? status : b41_agps_receiver_activate(o);
}

static int remaining(const struct timespec *deadline)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
    if (deadline->tv_sec < now.tv_sec ||
        (deadline->tv_sec == now.tv_sec && deadline->tv_nsec <= now.tv_nsec)) return 0;
    if (deadline->tv_sec - now.tv_sec >= INT_MAX / 1000) return -ERANGE;
    long long ns = (long long)(deadline->tv_sec - now.tv_sec) * 1000000000 +
        deadline->tv_nsec - now.tv_nsec;
    return (int)((ns + 999999) / 1000000);
}

int b41_agps_receiver_quiesce(struct b41_agps_receiver *o, const struct timespec *deadline)
{
    uint64_t one = 1;
    int status = 0;
    if (!o || !deadline || deadline->tv_sec < 0 || deadline->tv_nsec < 0 ||
        deadline->tv_nsec >= 1000000000) return -EINVAL;
    if (o->state == B41_AGPS_RX_QUARANTINED) return -EBUSY;
    if (o->state != B41_AGPS_RX_RUNNING && o->state != B41_AGPS_RX_PREPARED) return -EINVAL;
    atomic_store_explicit(&o->stop, 1, memory_order_release);
    status = same_fd(o, 1);
    if (!status && write(o->fd[1], &one, sizeof(one)) < 0 && errno != EAGAIN)
        status = -errno;
    if (!status) status = same_fd(o, 2);
    struct pollfd done = {o->fd[2], POLLIN, 0};
    while (!status) {
        int ms = remaining(deadline);
        if (ms < 0) { status = ms; break; }
        int ready = poll(&done, 1, ms);
        if (ready < 0) { if (errno == EINTR) continue; status = -errno; break; }
        if (ready && (done.revents & (POLLERR | POLLHUP | POLLNVAL))) { status = -EIO; break; }
        if (ready && (done.revents & POLLIN)) {
            o->state = B41_AGPS_RX_QUIESCED;
            return atomic_load(&o->first_error);
        }
        if (!ready) { status = -ETIMEDOUT; break; }
        status = -EIO;
    }
    o->state = B41_AGPS_RX_QUARANTINED;
    return fail(o, status);
}

int b41_agps_receiver_close(struct b41_agps_receiver *o)
{
    int status;
    if (!o || !o->entered) return -EINVAL;
    if (o->state != B41_AGPS_RX_BOUND && o->state != B41_AGPS_RX_QUIESCED)
        return -EPERM;
    for (unsigned i = 0; i < 4; ++i) {
        status = same_fd(o, i);
        if (status) {
            o->state = B41_AGPS_RX_QUARANTINED;
            return fail(o, status);
        }
    }
    for (unsigned i = 0; i < 4; ++i) {
        int error = close(o->fd[i]) ? -errno : 0;
        o->fd[i] = -1;
        if (error) fail(o, error);
    }
    o->state = B41_AGPS_RX_CLOSED;
    return atomic_load(&o->first_error);
}
