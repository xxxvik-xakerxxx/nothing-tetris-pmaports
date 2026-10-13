/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "session.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#ifdef SESSION_CLI_GUARD
int __wrap_ioctl(int fd, unsigned long command, ...)
{
    (void)fd; (void)command;
    _Exit(99);
}
ssize_t __wrap_write(int fd, const void *bytes, size_t count)
{
    (void)fd; (void)bytes; (void)count;
    _Exit(99);
}
#else

static struct gpsdl_v051_session_snapshot actual = {1, 32, 0, 123, 3, 2, {0, 0}};
static uint64_t tick = 10;
static unsigned query_calls, stop_calls, write_calls;
static int query_error, stop_error, write_error, clock_error, fd_changed;
static size_t limit = 12, accepted;
static uint8_t written[12];

int __wrap_clock_gettime(clockid_t id, struct timespec *out)
{
    assert(id == CLOCK_MONOTONIC);
    if (clock_error) { errno = EIO; return -1; }
    out->tv_sec = (time_t)(tick/1000000000u);
    out->tv_nsec = (long)(tick%1000000000u);
    return 0;
}
int __wrap_fcntl(int fd, int command, ...)
{
    assert(fd == 7 && command == F_GETFL);
    return O_RDWR | O_NONBLOCK;
}
int __wrap_fstat(int fd, struct stat *out)
{
    assert(fd == 7);
    memset(out, 0, sizeof(*out));
    out->st_mode = (mode_t)0020000;
    out->st_ino = (ino_t)(fd_changed ? 2u : 1u);
    return 0;
}
int __wrap_lstat(const char *path, struct stat *out)
{
    assert(!strcmp(path, "/dev/gpsdl0"));
    memset(out, 0, sizeof(*out));
    out->st_mode = (mode_t)0020000;
    out->st_ino = 1;
    return 0;
}
int __wrap_ioctl(int fd, unsigned long command, ...)
{
    va_list args;
    assert(fd == 7);
    va_start(args, command);
    if (command == GPSDL_V051_IOC_SESSION_SNAPSHOT) {
        struct gpsdl_v051_session_snapshot *out = va_arg(args, struct gpsdl_v051_session_snapshot *);
        query_calls++;
        va_end(args);
        if (query_error) { errno = query_error; return -1; }
        *out = actual;
        return 0;
    }
    assert(command == 18UL && va_arg(args, unsigned long) == 0UL);
    va_end(args);
    assert(actual.dsp_state == 2 && actual.link_state == 3);
    stop_calls++;
    if (stop_error) { errno = stop_error; return -1; }
    actual.dsp_state = 5; actual.link_state = 9;
    return 0;
}
ssize_t __wrap_write(int fd, const void *bytes, size_t count)
{
    size_t take = count < limit ? count : limit;
    assert(fd == 7 && actual.dsp_state == 3 && actual.link_state == 3);
    write_calls++;
    if (write_error) { errno = write_error; return -1; }
    assert(accepted + take <= sizeof(written));
    memcpy(written + accepted, bytes, take);
    accepted += take;
    return (ssize_t)take;
}
int __wrap_close(int fd)
{
    (void)fd;
    abort(); /* The controller never releases/reset/reopens its borrowed fd. */
}

static struct b41_native_session working(void)
{
    struct b41_native_session owner = {0};
    actual = (struct gpsdl_v051_session_snapshot){1, 32, 0, 123, 3, 2, {0, 0}};
    tick = 10; query_error = 0; stop_error = 0; write_error = 0;
    clock_error = 0; fd_changed = 0; accepted = 0; limit = 12;
    assert(b41_session_attach(&owner, 7, 1000) == 0);
    assert(owner.stage == B41_SESSION_WAIT_WORK);
    assert(b41_session_wait_step(&owner) == 0 && owner.stage == B41_SESSION_WAIT_WORK);
    query_error = EAGAIN;
    assert(b41_session_wait_step(&owner) == 0 && owner.stage == B41_SESSION_WAIT_WORK);
    query_error = 0; actual.dsp_state = 3;
    assert(b41_session_wait_step(&owner) == 0 && owner.stage == B41_SESSION_WORKING);
    return owner;
}

int main(void)
{
    static const uint8_t expected[12] = {0xaa, 0xf0, 6, 0, 5, 0xfe, 4, 0, 0x0d, 1, 0xaa, 0x0f};
    struct b41_native_session owner = working();
    unsigned previous_writes = write_calls, previous_stops = stop_calls, previous_queries;
    assert(write_calls == 0 && stop_calls == 0); /* attach/wait are read-only. */
    assert(b41_session_stop_begin(&owner) == 0);
    assert(b41_session_stop_begin(&owner) == -EALREADY);
    write_error = EAGAIN;
    assert(b41_session_stop_step(&owner) == 0 && owner.stop_offset == 0);
    write_error = 0; limit = 5;
    assert(b41_session_stop_step(&owner) == 0 && owner.stop_offset == 5);
    assert(b41_session_stop_step(&owner) == 0 && owner.stop_offset == 10);
    assert(b41_session_stop_step(&owner) == 0 && owner.stage == B41_SESSION_WAIT_RESET);
    assert(accepted == 12 && !memcmp(expected, written, 12));
    assert(b41_session_stop_step(&owner) == 0 && stop_calls == previous_stops);
    actual.dsp_state = 2;
    assert(b41_session_stop_step(&owner) == 0 && stop_calls == previous_stops + 1);
    assert(b41_session_stop_step(&owner) == 0 && owner.stage == B41_SESSION_STOPPED);
    previous_queries = query_calls;
    assert(b41_session_stop_step(&owner) == 0 && query_calls == previous_queries);
    assert(write_calls == previous_writes + 4);

    owner = working(); actual.session_id++;
    assert(b41_session_stop_begin(&owner) == -ESTALE);
    previous_queries = query_calls;
    assert(b41_session_wait_step(&owner) == -ESTALE && query_calls == previous_queries);
    owner = working(); fd_changed = 1;
    assert(b41_session_stop_begin(&owner) == -ESTALE);
    owner = working(); tick = 1000;
    assert(b41_session_stop_begin(&owner) == -ETIMEDOUT);
    owner = working(); tick = 9;
    assert(b41_session_stop_begin(&owner) == -ESTALE);
    owner = working(); query_error = EFAULT;
    assert(b41_session_stop_begin(&owner) == -EFAULT); /* No fallback on r188. */
    owner = working(); actual.abi_version++;
    assert(b41_session_stop_begin(&owner) == -EPROTO);
    owner = working(); actual.link_id = 1;
    assert(b41_session_stop_begin(&owner) == -ESTALE);
    owner = working(); clock_error = 1;
    previous_queries = query_calls;
    assert(b41_session_stop_begin(&owner) == -EIO && query_calls == previous_queries);
    assert(b41_session_stop_begin(&owner) == -EIO && query_calls == previous_queries);
    owner = working(); actual.size = 28;
    assert(b41_session_stop_begin(&owner) == -EPROTO);
    owner = working(); actual.reserved[1] = 1;
    assert(b41_session_stop_begin(&owner) == -EPROTO);
    owner = working();
    {
        struct gpsdl_v051_session_snapshot out, before;
        memset(&out, 0xa5, sizeof(out));
        before = out;
        query_error = EFAULT;
        assert(b41_session_snapshot(7, &out) == -EFAULT);
        assert(!memcmp(&out, &before, sizeof(out)));
    }
    owner = working(); assert(b41_session_stop_begin(&owner) == 0);
    limit = 0;
    assert(b41_session_stop_step(&owner) == -EIO);
    owner = working(); assert(b41_session_stop_begin(&owner) == 0);
    write_error = EINTR;
    assert(b41_session_stop_step(&owner) == -EINTR);
    previous_writes = write_calls;
    assert(b41_session_stop_step(&owner) == -EINTR && write_calls == previous_writes);
    owner = working(); assert(b41_session_stop_begin(&owner) == 0);
    assert(b41_session_stop_step(&owner) == 0);
    actual.dsp_state = 2; stop_error = EBUSY;
    assert(b41_session_stop_step(&owner) == -EBUSY);
    previous_stops = stop_calls;
    assert(b41_session_stop_step(&owner) == -EBUSY && stop_calls == previous_stops);
    owner = working(); assert(b41_session_stop_begin(&owner) == 0);
    assert(b41_session_stop_step(&owner) == 0);
    actual.dsp_state = 2;
    assert(b41_session_stop_step(&owner) == 0);
    actual.dsp_state = 3;
    assert(b41_session_stop_step(&owner) == -EHOSTDOWN); /* ioctl success is not STOP proof. */
    return 0;
}
#endif
