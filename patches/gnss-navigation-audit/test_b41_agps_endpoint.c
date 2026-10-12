/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "b41_agps_endpoint.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int live, lookup_error, socket_error, connect_error, close_error;
static int recheck_error, changed_inode, changed_mode, type_error, peer_error, wrong_peer, stat_error;
static int fake_fd;
static mode_t mode;
static unsigned lookups, sockets, connects, closes;
static struct sockaddr_un captured;
static socklen_t captured_length;
static const char path[] = "/data/agps_supl/mnl_to_agps";
int __real_socket(int family, int type, int protocol);
int __real_connect(int fd, const struct sockaddr *peer, socklen_t length);
int __real_close(int fd);
int __real_getsockopt(int fd, int level, int option, void *value, socklen_t *length);
int __real_getpeername(int fd, struct sockaddr *peer, socklen_t *length);
int __real_fstat(int fd, struct stat *out);

int __wrap_lstat(const char *name, struct stat *out)
{
    ++lookups;
    assert(!strcmp(name, path));
    if (lookup_error || (lookups == 2 && recheck_error)) {
        errno = lookups == 2 && recheck_error ? recheck_error : lookup_error;
        return -1;
    }
    memset(out, 0, sizeof(*out));
    out->st_mode = lookups == 2 && changed_mode ? S_IFLNK | 0700 : mode;
    out->st_dev = 7;
    out->st_ino = 19 + (lookups == 2 && changed_inode);
    return 0;
}
int __wrap_socket(int family, int type, int protocol)
{
    ++sockets;
    assert(family == AF_UNIX && type == (SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC) && !protocol);
    if (socket_error) { errno = socket_error; return -1; }
    return live ? __real_socket(family, type, protocol) : fake_fd;
}
int __wrap_connect(int fd, const struct sockaddr *peer, socklen_t length)
{
    struct sockaddr_un expected = {.sun_family = AF_UNIX};
    ++connects;
    assert(length <= sizeof(captured));
    memcpy(&captured, peer, sizeof(captured)); captured_length = length;
    if (!lookup_error && S_ISSOCK(mode)) {
        memcpy(expected.sun_path, path, sizeof(path));
        assert(length == 2 + sizeof(path));
    } else {
        memcpy(expected.sun_path + 1, "mtk_mnl2agps", 12);
        assert(length == 15);
    }
    assert(!memcmp(&captured, &expected, sizeof(expected)));
    if (connect_error) { errno = connect_error; return -1; }
    return live ? __real_connect(fd, peer, length) : 0;
}
int __wrap_getsockopt(int fd, int level, int option, void *value, socklen_t *length)
{
    if (live) return __real_getsockopt(fd, level, option, value, length);
    assert(fd == fake_fd && level == SOL_SOCKET && option == SO_TYPE && *length == sizeof(int));
    *(int *)value = type_error ? SOCK_STREAM : SOCK_DGRAM;
    return 0;
}
int __wrap_getpeername(int fd, struct sockaddr *peer, socklen_t *length)
{
    if (live) return __real_getpeername(fd, peer, length);
    assert(fd == fake_fd && *length >= captured_length);
    if (peer_error) { errno = peer_error; return -1; }
    memcpy(peer, &captured, captured_length);
    *length = captured_length + (wrong_peer == 1);
    if (wrong_peer == 2) ((struct sockaddr_un *)peer)->sun_path[1] ^= 1;
    return 0;
}
int __wrap_fstat(int fd, struct stat *out)
{
    if (live) return __real_fstat(fd, out);
    assert(fd == fake_fd);
    if (stat_error) { errno = stat_error; return -1; }
    memset(out, 0, sizeof(*out));
    out->st_mode = S_IFSOCK | 0600; out->st_dev = 9; out->st_ino = 31;
    return 0;
}
int __wrap_close(int fd)
{
    ++closes;
    if (live) return __real_close(fd);
    assert(fd == fake_fd);
    if (close_error) { errno = close_error; return -1; }
    return 0;
}
static struct b41_agps_endpoint *fresh(void)
{
    live = lookup_error = socket_error = connect_error = close_error = 0;
    recheck_error = changed_inode = changed_mode = type_error = peer_error = wrong_peer = stat_error = 0;
    fake_fd = 41;
    mode = S_IFSOCK | 0600;
    lookups = sockets = connects = closes = 0;
    memset(&captured, 0, sizeof(captured)); captured_length = 0;
    struct b41_agps_endpoint *endpoint = calloc(1, sizeof(*endpoint));
    assert(endpoint);
    return endpoint;
}
static void dispose(struct b41_agps_endpoint *endpoint)
{
    assert(endpoint->ipc.fd == -1);
    if (endpoint->ipc.initialized) assert(pthread_mutex_destroy(&endpoint->ipc.lock) == 0);
    free(endpoint);
}
static void failure(struct b41_agps_endpoint *endpoint, int expected,
                    unsigned expected_sockets, unsigned expected_connects, unsigned expected_closes)
{
    assert(b41_agps_endpoint_open(endpoint) == expected);
    assert(endpoint->first_error == expected && endpoint->ipc.state == B41_AGPS_CLOSED);
    assert(sockets == expected_sockets && connects == expected_connects && closes == expected_closes);
    unsigned before = lookups;
    assert(b41_agps_endpoint_open(endpoint) == expected);
    assert(lookups == before && sockets == expected_sockets && connects == expected_connects && closes == expected_closes);
    dispose(endpoint);
}
int main(void)
{
    struct b41_agps_endpoint *endpoint;
    assert(b41_agps_endpoint_open(NULL) == -EINVAL);
    /* Independent exact-address fixtures for all source branch outcomes. */
    for (unsigned branch = 0; branch < 4; ++branch) {
        endpoint = fresh();
        if (branch == 3) fake_fd = 0;
        if (branch == 1) lookup_error = ENOENT;
        if (branch == 2) mode = S_IFDIR | 0700;
        assert(b41_agps_endpoint_open(endpoint) == 0);
        unsigned abstract = branch == 1 || branch == 2;
        assert(endpoint->route == (abstract ? B41_AGPS_ENDPOINT_ABSTRACT : B41_AGPS_ENDPOINT_FILESYSTEM));
        assert(endpoint->ipc.state == B41_AGPS_OWNED && endpoint->ipc.fd == fake_fd);
        assert(lookups == (abstract ? 1u : 2u) && sockets == 1 && connects == 1 && !closes);
        assert(b41_agps_endpoint_open(endpoint) == -EALREADY);
        assert(b41_agps_owner_stop(&endpoint->ipc) == 0 && closes == 1);
        assert(b41_agps_endpoint_open(endpoint) == -EALREADY);
        dispose(endpoint);
    }
    const int lookup_errors[] = {EACCES, EINTR, ELOOP, ENOTDIR, EIO};
    for (unsigned i = 0; i < sizeof(lookup_errors)/sizeof(*lookup_errors); ++i) {
        endpoint = fresh(); lookup_error = lookup_errors[i];
        failure(endpoint, -lookup_error, 0, 0, 0);
    }
    const mode_t bad_modes[] = {S_IFLNK, S_IFREG, S_IFIFO, S_IFCHR, S_IFBLK};
    for (unsigned i = 0; i < sizeof(bad_modes)/sizeof(*bad_modes); ++i) {
        endpoint = fresh(); mode = bad_modes[i];
        failure(endpoint, -EPROTO, 0, 0, 0);
    }
    endpoint = fresh(); socket_error = EMFILE;
    failure(endpoint, -EMFILE, 1, 0, 0);
    const int connect_errors[] = {EAGAIN, EINTR, ECONNREFUSED, ENOENT, EACCES};
    for (unsigned branch = 0; branch < 2; ++branch)
        for (unsigned i = 0; i < sizeof(connect_errors)/sizeof(*connect_errors); ++i) {
            endpoint = fresh(); lookup_error = branch ? ENOENT : 0;
            connect_error = connect_errors[i]; close_error = EINTR;
            failure(endpoint, -connect_error, 1, 1, 1);
        }
    endpoint = fresh(); recheck_error = ENOENT;
    failure(endpoint, -ENOENT, 1, 1, 1);
    endpoint = fresh(); changed_inode = 1;
    failure(endpoint, -ESTALE, 1, 1, 1);
    endpoint = fresh(); changed_mode = 1;
    failure(endpoint, -ESTALE, 1, 1, 1);
    endpoint = fresh(); type_error = 1;
    failure(endpoint, -EPROTO, 1, 1, 1);
    endpoint = fresh(); peer_error = ENOTCONN;
    failure(endpoint, -ENOTCONN, 1, 1, 1);
    for (int variant = 1; variant <= 2; ++variant) {
        endpoint = fresh(); lookup_error = ENOENT; wrong_peer = variant;
        failure(endpoint, -EPROTO, 1, 1, 1);
    }
    endpoint = fresh(); stat_error = EBADF;
    failure(endpoint, -EBADF, 1, 1, 1);

    /* CI-only real Linux address round trip and existing type150/152 sender.
     * This controlled receiver is a transport fixture, NEVER an AGPS service.
     * Refuse bind collision; do not replace an existing listener.
     */
    endpoint = fresh(); live = 1; lookup_error = ENOENT;
    struct sockaddr_un listener = {.sun_family = AF_UNIX};
    memcpy(listener.sun_path + 1, "mtk_mnl2agps", 12);
    int receiver = __real_socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    assert(receiver >= 0);
    assert(bind(receiver, (const struct sockaddr *)&listener, 15) == 0);
    assert(b41_agps_endpoint_open(endpoint) == 0);
    assert(fcntl(endpoint->ipc.fd, F_GETFL) & O_NONBLOCK);
    assert(fcntl(endpoint->ipc.fd, F_GETFD) & FD_CLOEXEC);
    assert(b41_agps_owner_send_data(&endpoint->ipc, "abc", 3) == 0);
    uint8_t packet[64];
    const uint8_t data[] = {1,0,0,0,150,0,0,0,1,4,0,0,0,'a','b','c',0};
    assert(recv(receiver, packet, sizeof(packet), MSG_DONTWAIT) == (ssize_t)sizeof(data));
    assert(!memcmp(packet, data, sizeof(data)));
    assert(b41_agps_owner_send_selector1(&endpoint->ipc) == 0);
    assert(recv(receiver, packet, sizeof(packet), MSG_DONTWAIT) == 8);
    assert(!memcmp(packet, "\1\0\0\0\230\0\0\0", 8));
    int owned = endpoint->ipc.fd;
    assert(b41_agps_owner_stop(&endpoint->ipc) == 0);
    assert(fcntl(owned, F_GETFD) == -1 && errno == EBADF);
    assert(__real_close(receiver) == 0);
    dispose(endpoint);
    /* No listener: actual connect refusal, no fallback or swallowed result. */
    endpoint = fresh(); live = 1; lookup_error = ENOENT;
    failure(endpoint, -ECONNREFUSED, 1, 1, 1);
    return 0;
}
