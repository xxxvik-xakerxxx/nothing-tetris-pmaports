/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "download_linux.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static void erase(void *storage, size_t size)
{
    volatile uint8_t *bytes = storage;

    while (size-- != 0)
        *bytes++ = 0;
}

static int monotonic(uint64_t *now)
{
    struct timespec time;

    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0)
        return -errno;
    if (time.tv_sec < 0 || time.tv_nsec < 0 || time.tv_nsec >= 1000000000L ||
        (uint64_t)time.tv_sec > (UINT64_MAX - (uint64_t)time.tv_nsec) / 1000000000u)
        return -EOVERFLOW;
    *now = (uint64_t)time.tv_sec * 1000000000u + (uint64_t)time.tv_nsec;
    return 0;
}

static int descriptor(int fd)
{
    struct stat st;
    int flags = fcntl(fd, F_GETFL);

    if (flags < 0)
        return -errno;
    if ((flags & O_ACCMODE) != O_RDWR || (flags & O_NONBLOCK) == 0)
        return -EINVAL;
    if (fstat(fd, &st) != 0)
        return -errno;
    if (!S_ISCHR(st.st_mode))
        return -ENODEV;
    /* Identity/exclusive lifetime belongs to the real gps0 opener, not a
     * guessed minor number or fstat-based permission certificate here.
     */
    return 0;
}

int b41_download_linux_begin(struct b41_download *owner,
                             const struct b41_bootstrap_session *session,
                             uint64_t deadline_ns)
{
    struct b41_bootstrap_route route;
    struct b41_mvcd_bootstrap_fields fields;
    struct b41_bootstrap_boot_info info;
    struct b41_bootstrap_query query;
    uint64_t now;
    int status;

    if (owner == NULL || session == NULL)
        return -EINVAL;
    if (owner->stage != B41_DOWNLOAD_NEW)
        return owner->stage == B41_DOWNLOAD_FAILED ? owner->first_error : -EALREADY;
    status = b41_bootstrap_route_select(&session->selectors, &route);
    if (status == 0)
        status = b41_mvcd_bootstrap_fields_build(session->fields, &fields);
    erase(&fields, sizeof(fields));
    if (status == 0)
        status = descriptor(session->gps0_fd);
    if (status == 0)
        status = monotonic(&now);
    if (status != 0)
        return b41_download_abort(owner, status);
    if (now >= deadline_ns)
        return b41_download_abort(owner, -ETIMEDOUT);
    memset(&info, 0, sizeof(info));
    status = ioctl(session->gps0_fd, (unsigned long)route.metadata_ioctl, &info);
    if (status < 0)
        status = -errno;
    if (status != 0) {
        erase(&info, sizeof(info));
        return b41_download_abort(owner, status);
    }
    memset(&query, 0, sizeof(query));
    query.session = session;
    query.gps0_fd = session->gps0_fd;
    query.selectors = session->selectors;
    query.command = route.metadata_ioctl;
    query.info = &info;
    query.bytes_returned = sizeof(info); /* Pinned ioctl success copies this full ABI. */
    status = monotonic(&now);
    if (status == 0)
        status = b41_download_begin(owner, session, &query, now, deadline_ns);
    erase(&info, sizeof(info));
    erase(&query, sizeof(query));
    return status == 0 ? 0 : b41_download_abort(owner, status);
}

int b41_download_linux_step(struct b41_download *owner)
{
    struct b41_download_action action;
    uint8_t received[2048]; /* Actual gps0 DMA entries cannot be read by header size. */
    uint64_t now;
    ssize_t count;
    int result;
    int status = monotonic(&now);

    if (status != 0)
        return b41_download_abort(owner, status);
    status = b41_download_next(owner, now, &action);
    if (status != 0 || action.kind == B41_DOWNLOAD_DONE)
        return status;
    status = descriptor(action.gps0_fd);
    if (status != 0)
        return b41_download_abort(owner, status);
    switch (action.kind) {
    case B41_DOWNLOAD_WRITE:
        count = write(action.gps0_fd, action.bytes, action.size);
        result = count < 0 ? -errno : count > INT_MAX ? -EOVERFLOW : (int)count;
        if (result < 0 && result != -EAGAIN)
            return b41_download_abort(owner, result);
        if (result == 0)
            return b41_download_abort(owner, -EIO);
        status = monotonic(&now);
        return status == 0 ? b41_download_written(owner, now, result) : b41_download_abort(owner, status);
    case B41_DOWNLOAD_SUBMIT_FRAGMENT:
        result = ioctl(action.gps0_fd, (unsigned long)action.command, (unsigned long)action.argument);
        if (result < 0)
            result = -errno;
        if (result != 0)
            return b41_download_abort(owner, result);
        status = monotonic(&now);
        return status == 0 ? b41_download_submitted(owner, now, result) : b41_download_abort(owner, status);
    case B41_DOWNLOAD_READ:
        count = read(action.gps0_fd, received, sizeof(received));
        result = count < 0 ? -errno : 0;
        if (count == 0 || (result < 0 && result != -EAGAIN)) {
            erase(received, sizeof(received));
            return b41_download_abort(owner, count == 0 ? -EPIPE : result);
        }
        status = monotonic(&now);
        if (status == 0 && count > 0)
            status = b41_download_received(owner, now, received, (size_t)count);
        else if (status == 0 && result == -EAGAIN)
            status = b41_download_next(owner, now, &action);
        else if (status == 0)
            status = b41_download_abort(owner, count == 0 ? -EPIPE : result);
        erase(received, sizeof(received));
        return status == 0 ? 0 : b41_download_abort(owner, status);
    default:
        return b41_download_abort(owner, -EPROTO);
    }
}
