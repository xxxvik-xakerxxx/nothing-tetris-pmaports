/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "session.h"

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/* Source enum values at exact e96f60dc, independently pinned by static tests. */
enum { LINK_OPENED = 3, LINK_SUSPENDING = 8, LINK_SUSPENDED = 9,
       DSP_ON = 1, DSP_RESET_DONE = 2, DSP_WORKING = 3, DSP_HW_STOP = 5 };
static const uint8_t stop_frame[12] = {
    0xaa, 0xf0, 0x06, 0x00, 0x05, 0xfe, 0x04, 0x00, 0x0d, 0x01, 0xaa, 0x0f
};

static int now_ns(uint64_t *out)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return -errno;
    if (value.tv_sec < 0 || value.tv_nsec < 0 || value.tv_nsec >= 1000000000 ||
        (uint64_t)value.tv_sec > (UINT64_MAX - (uint64_t)value.tv_nsec)/1000000000u)
        return -EOVERFLOW;
    *out = (uint64_t)value.tv_sec*1000000000u + (uint64_t)value.tv_nsec;
    return 0;
}

int b41_session_snapshot(int fd, struct gpsdl_v051_session_snapshot *out)
{
    struct gpsdl_v051_session_snapshot result = {0};
    struct stat actual, node;
    int status;
    if (fd < 0 || !out) return -EINVAL;
    /* Reject an unrelated inherited descriptor before issuing any command. */
    if (fstat(fd, &actual) || lstat("/dev/gpsdl0", &node)) return -errno;
    if (!S_ISCHR(actual.st_mode) || !S_ISCHR(node.st_mode) ||
        actual.st_dev != node.st_dev || actual.st_rdev != node.st_rdev || actual.st_ino != node.st_ino)
        return -ENODEV;
    status = ioctl(fd, (unsigned long)GPSDL_V051_IOC_SESSION_SNAPSHOT, &result);
    if (status < 0) return -errno;
    if (status || result.abi_version != GPSDL_V051_SESSION_ABI ||
        result.size != sizeof(result) || result.link_id > 1 ||
        !result.session_id || result.session_id > 0x7ffffffeu ||
        result.link_state >= 11 || result.dsp_state >= 7 ||
        result.reserved[0] || result.reserved[1]) return -EPROTO;
    *out = result;
    return 0;
}

static int failed(struct b41_native_session *owner, int status)
{
    if (owner->stage != B41_SESSION_FAILED) {
        owner->first_error = status < 0 ? status : -EPROTO;
        owner->stage = B41_SESSION_FAILED;
    }
    return owner->first_error;
}

static int time_check(struct b41_native_session *owner)
{
    uint64_t now;
    int status = now_ns(&now);
    if (status) return failed(owner, status);
    if (now < owner->last_ns) return failed(owner, -ESTALE);
    owner->last_ns = now;
    if (now >= owner->deadline_ns) return failed(owner, -ETIMEDOUT);
    return 0;
}

static int same_fd(struct b41_native_session *owner)
{
    struct stat st;
    int flags = fcntl(owner->fd, F_GETFL);
    if (flags < 0) return failed(owner, -errno);
    if ((flags & O_ACCMODE) != O_RDWR || !(flags & O_NONBLOCK))
        return failed(owner, -EINVAL);
    if (fstat(owner->fd, &st)) return failed(owner, -errno);
    if (!S_ISCHR(st.st_mode) || st.st_dev != owner->device ||
        st.st_rdev != owner->rdevice || st.st_ino != owner->inode)
        return failed(owner, -ESTALE);
    return 0;
}

static int sample(struct b41_native_session *owner)
{
    struct gpsdl_v051_session_snapshot result;
    int status = time_check(owner);
    if (!status) status = same_fd(owner);
    if (status) return status;
    status = b41_session_snapshot(owner->fd, &result);
    if (status && status != -EAGAIN) return failed(owner, status);
    if (time_check(owner)) return owner->first_error;
    if (status) return 1; /* A changing sampled state is pending, not readiness. */
    if (result.link_id != 0 || result.session_id != owner->session_id)
        return failed(owner, -ESTALE);
    owner->latest = result;
    return 0;
}

int b41_session_attach(struct b41_native_session *owner, int fd, uint64_t deadline_ns)
{
    struct b41_native_session result = {0};
    struct stat st;
    int flags, status;
    if (!owner || fd < 0) return -EINVAL;
    if (owner->stage != B41_SESSION_NEW)
        return owner->stage == B41_SESSION_FAILED ? owner->first_error : -EALREADY;
    result.fd = fd;
    result.deadline_ns = deadline_ns;
    status = now_ns(&result.last_ns);
    if (status) return failed(owner, status);
    if (result.last_ns >= deadline_ns) return failed(owner, -ETIMEDOUT);
    flags = fcntl(fd, F_GETFL);
    if (flags < 0) return failed(owner, -errno);
    if ((flags & O_ACCMODE) != O_RDWR || !(flags & O_NONBLOCK)) return failed(owner, -EINVAL);
    if (fstat(fd, &st)) return failed(owner, -errno);
    if (!S_ISCHR(st.st_mode)) return failed(owner, -ENODEV);
    result.device = st.st_dev;
    result.rdevice = st.st_rdev;
    result.inode = st.st_ino;
    status = b41_session_snapshot(fd, &result.latest);
    if (status) return failed(owner, status);
    if (result.latest.link_id != 0 || result.latest.link_state != LINK_OPENED ||
        (result.latest.dsp_state != DSP_ON && result.latest.dsp_state != DSP_RESET_DONE &&
         result.latest.dsp_state != DSP_WORKING)) return failed(owner, -EHOSTDOWN);
    result.session_id = result.latest.session_id;
    result.stage = B41_SESSION_WAIT_WORK;
    if (time_check(&result)) return failed(owner, result.first_error);
    *owner = result;
    return 0;
}

int b41_session_wait_step(struct b41_native_session *owner)
{
    int status;
    if (!owner) return -EINVAL;
    if (owner->stage == B41_SESSION_FAILED) return owner->first_error;
    if (owner->stage == B41_SESSION_WORKING) return 0;
    if (owner->stage != B41_SESSION_WAIT_WORK) return -EINVAL;
    status = sample(owner);
    if (status) return status < 0 ? status : 0;
    if (owner->latest.link_state != LINK_OPENED) return failed(owner, -EHOSTDOWN);
    if (owner->latest.dsp_state == DSP_WORKING) owner->stage = B41_SESSION_WORKING;
    else if (owner->latest.dsp_state != DSP_ON && owner->latest.dsp_state != DSP_RESET_DONE)
        return failed(owner, -EHOSTDOWN);
    return 0;
}

int b41_session_stop_begin(struct b41_native_session *owner)
{
    int status;
    if (!owner) return -EINVAL;
    if (owner->stage == B41_SESSION_FAILED) return owner->first_error;
    if (owner->stage != B41_SESSION_WORKING) return -EALREADY;
    status = sample(owner);
    if (status) return status < 0 ? status : -EAGAIN;
    if (owner->latest.link_state != LINK_OPENED || owner->latest.dsp_state != DSP_WORKING)
        return failed(owner, -EHOSTDOWN);
    owner->stop_offset = 0;
    owner->stage = B41_SESSION_STOP_TX;
    return 0;
}

int b41_session_stop_step(struct b41_native_session *owner)
{
    int status;
    if (!owner) return -EINVAL;
    if (owner->stage == B41_SESSION_FAILED) return owner->first_error;
    if (owner->stage == B41_SESSION_STOPPED) return 0;
    if (owner->stage != B41_SESSION_STOP_TX && owner->stage != B41_SESSION_WAIT_RESET &&
        owner->stage != B41_SESSION_WAIT_HWSTOP) return -EINVAL;
    status = sample(owner);
    if (status) return status < 0 ? status : 0;
    if (owner->stage == B41_SESSION_STOP_TX) {
        ssize_t count;
        int write_error = 0;
        size_t remaining;
        if (owner->latest.link_state != LINK_OPENED || owner->latest.dsp_state != DSP_WORKING)
            return failed(owner, -EHOSTDOWN);
        if (owner->stop_offset >= sizeof(stop_frame)) return failed(owner, -EPROTO);
        remaining = sizeof(stop_frame) - owner->stop_offset;
        count = write(owner->fd, stop_frame + owner->stop_offset, remaining);
        if (count < 0) write_error = -errno;
        if (write_error && write_error != -EAGAIN) return failed(owner, write_error);
        if (time_check(owner)) return owner->first_error;
        if (write_error) return 0;
        if (!count || (size_t)count > remaining) return failed(owner, -EIO);
        owner->stop_offset += (size_t)count;
        if (owner->stop_offset == sizeof(stop_frame)) owner->stage = B41_SESSION_WAIT_RESET;
    } else if (owner->stage == B41_SESSION_WAIT_RESET) {
        int ioctl_error;
        if (owner->latest.link_state != LINK_OPENED) return failed(owner, -EHOSTDOWN);
        if (owner->latest.dsp_state == DSP_WORKING) return 0;
        if (owner->latest.dsp_state != DSP_RESET_DONE) return failed(owner, -EHOSTDOWN);
        /* This is the existing normal deep-stop route, never assert ioctl12.
         * Do not issue it from WORK, where stock may warn/reject the sequence.
         */
        owner->stage = B41_SESSION_WAIT_HWSTOP;
        status = ioctl(owner->fd, 18UL, 0UL);
        ioctl_error = status < 0 ? -errno : status ? -EPROTO : 0;
        if (ioctl_error) return failed(owner, ioctl_error);
        return time_check(owner);
    } else {
        if (owner->latest.link_state == LINK_SUSPENDED && owner->latest.dsp_state == DSP_HW_STOP)
            owner->stage = B41_SESSION_STOPPED;
        else if ((owner->latest.link_state != LINK_SUSPENDING && owner->latest.link_state != LINK_SUSPENDED) ||
                 (owner->latest.dsp_state != DSP_RESET_DONE && owner->latest.dsp_state != DSP_HW_STOP))
            return failed(owner, -EHOSTDOWN);
    }
    return 0;
}
