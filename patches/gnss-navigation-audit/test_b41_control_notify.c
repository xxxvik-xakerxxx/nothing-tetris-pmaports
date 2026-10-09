/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_control_notify.h"
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static int socket_error, send_error, close_error, short_send;
static unsigned sockets, sends, closes;
int __wrap_socket(int family, int type, int protocol)
{
    ++sockets;
    assert(family == AF_UNIX && protocol == 0);
    assert(type == (SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC));
    if (socket_error) { errno = socket_error; return -1; }
    return 41;
}
ssize_t __wrap_sendto(int fd, const void *data, size_t length, int flags,
                     const struct sockaddr *address, socklen_t address_length)
{
    struct sockaddr_un expected;
    ++sends;
    memset(&expected, 0, sizeof(expected));
    expected.sun_family = AF_UNIX;
    memcpy(expected.sun_path + 1, "mnld_gps_control_socket",
           sizeof("mnld_gps_control_socket") - 1);
    assert(fd == 41 && length == 4);
    assert(memcmp(data, "\3\0\0\0", 4) == 0);
    assert(flags == (MSG_DONTWAIT | MSG_NOSIGNAL));
    assert(address_length == sizeof(expected));
    assert(memcmp(address, &expected, sizeof(expected)) == 0);
    if (send_error) { errno = send_error; return -1; }
    return short_send ? 3 : 4;
}
int __wrap_close(int fd)
{
    ++closes;
    assert(fd == 41);
    if (close_error) { errno = close_error; return -1; }
    return 0;
}
static void reset(void)
{
    socket_error = send_error = close_error = short_send = 0;
    sockets = sends = closes = 0;
}
int main(void)
{
    unsigned policy;
    for (policy = 0; policy < 256; ++policy) {
        reset();
        assert(b41_control_notify(7, (uint8_t)policy) == ((policy & 16) ? 1 : 0));
        assert(sockets == ((policy & 16) ? 0u : 1u));
        assert(sends == sockets && closes == sockets);
    }
    reset();
    assert(b41_control_notify(0, 0) == -ENOTSUP);
    assert(b41_control_notify(3, 0) == -ENOTSUP);
    assert(b41_control_notify(13, 16) == -ENOTSUP);
    assert(sockets == 0);
    socket_error = EMFILE;
    assert(b41_control_notify(7, 0) == -EMFILE && sends == 0 && closes == 0);
    reset(); send_error = EAGAIN; close_error = EINTR;
    assert(b41_control_notify(7, 0) == -EAGAIN && sends == 1 && closes == 1);
    reset(); send_error = EINTR;
    assert(b41_control_notify(7, 0) == -EINTR && sends == 1 && closes == 1);
    reset(); short_send = 1;
    assert(b41_control_notify(7, 0) == -EIO && closes == 1);
    reset(); close_error = EINTR;
    assert(b41_control_notify(7, 0) == -EINTR && closes == 1);
    return 0;
}
