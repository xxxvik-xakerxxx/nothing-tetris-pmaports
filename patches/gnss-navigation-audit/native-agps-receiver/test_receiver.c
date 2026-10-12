/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_agps_receiver.h"
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

/* CI transport fixture only. Never substitute these symbols in production. */
static int delivery_fd, block_fd = -1, delivery_error, association_error, admission_error;
struct receipt { unsigned type, parameter, length; unsigned char bytes[256]; };
int __wrap_b41_agps_native_associate(const void *elf, size_t size,
    const struct b41_library_view *view, struct b41_library_association *out)
{
    assert(!elf && !size && !view);
    if (association_error) return association_error;
    *out = (struct b41_library_association){.base = 0x1000, .extent = B41_LIBRARY_IMAGE_END};
    return 0;
}
int __wrap_b41_agps_native_admit(const struct b41_library_association *image)
{
    assert(image->base == 0x1000);
    return admission_error;
}
int __real_b41_agps_native_deliver(const struct b41_library_association *,
                                 const struct b41_agps_request *);
int __wrap_b41_agps_native_deliver(const struct b41_library_association *image,
                                 const struct b41_agps_request *request)
{
    struct receipt r = {request->type, request->parameter, request->length, {0}};
    assert(image->base == 0x1000 && request->length <= sizeof(r.bytes));
    memcpy(r.bytes, request->payload, request->length);
    assert(write(delivery_fd, &r, sizeof(r)) == (ssize_t)sizeof(r));
    if (block_fd >= 0) {
        char c;
        assert(read(block_fd, &c, 1) == 1);
    }
    return delivery_error;
}
static void word(unsigned char *p, unsigned value)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (unsigned char)(value >> (i * 8));
}
static size_t packet(unsigned char *p, unsigned type, const void *payload, size_t length)
{
    word(p, 1); word(p + 4, type);
    size_t prefix = type == 250 ? 13 : 12;
    if (type == 250) p[8] = 1;
    word(p + prefix - 4, (unsigned)length);
    memcpy(p + prefix, payload, length);
    return prefix + length;
}
static struct timespec deadline(long milliseconds)
{
    struct timespec t;
    assert(!clock_gettime(CLOCK_MONOTONIC, &t));
    t.tv_sec += milliseconds / 1000;
    t.tv_nsec += milliseconds % 1000 * 1000000;
    if (t.tv_nsec >= 1000000000) { ++t.tv_sec; t.tv_nsec -= 1000000000; }
    return t;
}
static void ready(int fd)
{
    struct pollfd p = {fd, POLLIN, 0};
    assert(poll(&p, 1, 2000) == 1 && p.revents == POLLIN);
}
static int sender(void)
{
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    assert(fd >= 0);
    return fd;
}
static struct sockaddr_un address(void)
{
    struct sockaddr_un a = {0}; a.sun_family = AF_UNIX;
    memcpy(a.sun_path + 1, "mtk_agps2mnl", 12);
    return a;
}
static void send_packet(int fd, const void *p, size_t n)
{
    struct sockaddr_un a = address();
    assert(sendto(fd, p, n, MSG_NOSIGNAL, (const struct sockaddr *)&a, 15) == (ssize_t)n);
}
static unsigned fd_count(void)
{
    unsigned n = 0;
    DIR *d = opendir("/proc/self/fd"); assert(d);
    while (readdir(d)) ++n;
    assert(!closedir(d));
    return n;
}
static struct b41_agps_receiver owner;
static int receipts[2];
static void start(pid_t pid)
{
    assert(!pipe2(receipts, O_CLOEXEC)); delivery_fd = receipts[1];
    assert(!b41_agps_receiver_open(&owner, pid, getuid()));
    assert(!b41_agps_receiver_start(&owner, NULL, 0, NULL));
}
static void stop(int expected)
{
    struct timespec t = deadline(2000);
    assert(b41_agps_receiver_close(&owner) == -EPERM);
    assert(b41_agps_receiver_quiesce(&owner, &t) == expected);
    assert(owner.state == B41_AGPS_RX_QUIESCED);
    assert(b41_agps_receiver_close(&owner) == expected);
    assert(owner.state == B41_AGPS_RX_CLOSED);
    assert(b41_agps_receiver_close(&owner) == -EPERM);
    assert(b41_agps_receiver_open(&owner, getpid(), getuid()) == -EALREADY);
}
static void decode(void)
{
    static unsigned char p[B41_AGPS_RX_MAX + 1];
    struct b41_agps_request r, before = {99, 88, 77, p};
    for (unsigned type = 0; type < 400; ++type) {
        size_t n = packet(p, type, "X", 2);
        memcpy(&r, &before, sizeof(r));
        int status = b41_agps_receiver_decode(p, n, &r);
        int supported = type == 250 || (type >= 256 && type <= 262) || type == 264;
        assert(status == (supported ? 0 : -EOPNOTSUPP));
        if (!supported) assert(!memcmp(&r, &before, sizeof(r)));
        else {
            assert(r.parameter == (type == 250 ? 35 : type == 264 ? 118 : type - 256 + 62));
            assert(r.length == 2 && !memcmp(r.payload, "X", 2));
            for (size_t cut = 0; cut < n; ++cut) {
                memcpy(&r, &before, sizeof(r));
                assert(b41_agps_receiver_decode(p, cut, &r) < 0);
                assert(!memcmp(&r, &before, sizeof(r)));
            }
            memcpy(&r, &before, sizeof(r));
            p[n] = 0;
            assert(b41_agps_receiver_decode(p, n + 1, &r) == -EBADMSG);
        }
    }
    size_t n = packet(p, 250, "", 1);
    assert(!b41_agps_receiver_decode(p, n, &r) && r.length == 1);
    p[8] = 0;
    assert(b41_agps_receiver_decode(p, 9, &r) == -ENODATA);
    assert(b41_agps_receiver_decode(p, n, &r) == -EBADMSG);
    p[8] = 2;
    assert(b41_agps_receiver_decode(p, n, &r) == -EBADMSG);
    memset(p + 13, 'x', 257); p[13 + 255] = 0;
    word(p, 1); word(p + 4, 250); p[8] = 1; word(p + 9, 256);
    assert(!b41_agps_receiver_decode(p, 269, &r));
    word(p + 9, 257); p[13 + 255] = 'x'; p[13 + 256] = 0;
    assert(b41_agps_receiver_decode(p, 270, &r) == -EMSGSIZE);
    word(p + 9, 3); p[13] = 'x'; p[14] = 0; p[15] = 0;
    assert(b41_agps_receiver_decode(p, 16, &r) == -EBADMSG);
    for (unsigned type = 256; type <= 264; ++type) {
        if (type == 263) continue;
        word(p, 1); word(p + 4, type);
        unsigned limit = type == 262 ? 8192 : B41_AGPS_RX_MAX - 12;
        memset(p + 12, 0xff, limit); word(p + 8, limit);
        assert(!b41_agps_receiver_decode(p, 12 + limit, &r));
        word(p + 8, UINT32_MAX);
        assert(b41_agps_receiver_decode(p, 12 + limit, &r) == -EBADMSG);
        word(p + 8, 0);
        assert(b41_agps_receiver_decode(p, 12, &r) == -EBADMSG);
    }
    assert(b41_agps_receiver_decode(p, sizeof(p), &r) == -EMSGSIZE);
#if !defined(__aarch64__) || !defined(__BIONIC__)
    assert(__real_b41_agps_native_deliver(NULL, NULL) == -EOPNOTSUPP);
#else
    assert(__real_b41_agps_native_deliver(NULL, NULL) == -EINVAL);
#endif
}
static void lifecycle(void)
{
    int fd = sender();
    start(getpid());
    struct sockaddr_un actual = {0}, expected = address();
    socklen_t extent = sizeof(actual);
    assert(!getsockname(owner.fd[0], (struct sockaddr *)&actual, &extent));
    assert(extent == 15 && !memcmp(&actual, &expected, extent));
    for (unsigned i = 0; i < 4; ++i) assert(fcntl(owner.fd[i], F_GETFD) & FD_CLOEXEC);
    assert(fcntl(owner.fd[0], F_GETFL) & O_NONBLOCK);
    unsigned char p[512];
    for (unsigned type = 250; type <= 264; ++type) {
        if (type != 250 && !(type >= 256 && type <= 262) && type != 264) continue;
        size_t n = packet(p, type, "\x80\x00", 2);
        send_packet(fd, p, n); memset(p, 0x55, n);
        ready(receipts[0]); struct receipt r;
        assert(read(receipts[0], &r, sizeof(r)) == (ssize_t)sizeof(r));
        assert(r.type == type && r.length == 2 && r.bytes[0] == 0x80 && !r.bytes[1]);
    }
    stop(0);
    assert(atomic_load(&owner.delivered) == 9);
    for (unsigned i = 0; i < 4; ++i) assert(owner.fd[i] == -1);
    close(fd);
}
static void wrong_peer(void)
{
    int fd = sender(); start(getpid() + 1);
    unsigned char p[32]; size_t n = packet(p, 250, "X", 2);
    send_packet(fd, p, n); ready(owner.fd[2]);
    stop(-EACCES); assert(!atomic_load(&owner.delivered));
    close(fd);
}
static void malformed(void)
{
    int fd = sender(); start(getpid());
    unsigned char p[32]; size_t n = packet(p, 250, "X", 2);
    word(p + 9, 8);
    send_packet(fd, p, n); ready(owner.fd[2]);
    stop(-EBADMSG); assert(!atomic_load(&owner.delivered)); close(fd);
}
static void unsupported(void)
{
    int fd = sender(); start(getpid());
    unsigned char p[32]; size_t n = packet(p, 200, "X", 2);
    send_packet(fd, p, n); ready(owner.fd[2]);
    stop(-EOPNOTSUPP); assert(!atomic_load(&owner.delivered)); close(fd);
}
static void native_failure(void)
{
    int fd = sender(); delivery_error = -EIO; start(getpid());
    unsigned char p[32]; size_t n = packet(p, 250, "X", 2);
    send_packet(fd, p, n); ready(owner.fd[2]);
    stop(-EIO); assert(!atomic_load(&owner.delivered)); close(fd);
}
static void timeout_ownership(void)
{
    int gate[2], fd = sender(); assert(!pipe2(gate, O_CLOEXEC)); block_fd = gate[0];
    start(getpid());
    unsigned char p[32]; size_t n = packet(p, 250, "X", 2);
    send_packet(fd, p, n); ready(receipts[0]);
    int saved[4]; memcpy(saved, owner.fd, sizeof(saved));
    struct timespec t = deadline(20);
    assert(b41_agps_receiver_quiesce(&owner, &t) == -ETIMEDOUT);
    assert(owner.state == B41_AGPS_RX_QUARANTINED);
    assert(b41_agps_receiver_close(&owner) == -EPERM);
    assert(b41_agps_receiver_quiesce(&owner, &t) == -EBUSY);
    for (unsigned i = 0; i < 4; ++i) assert(owner.fd[i] == saved[i] && fcntl(saved[i], F_GETFD) >= 0);
    /* Exit child with worker blocked; no free/DSO unload or false cleanup ACK. */
}
static void rights(void)
{
    int fd = sender(), pipefd[2]; assert(!pipe2(pipefd, O_CLOEXEC)); start(getpid());
    unsigned char p[32]; size_t n = packet(p, 250, "X", 2);
    struct sockaddr_un a = address(); struct iovec iov = {p, n};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(int))]; } c = {0};
    struct msghdr msg = {0}; msg.msg_name = &a; msg.msg_namelen = 15;
    msg.msg_iov = &iov; msg.msg_iovlen = 1; msg.msg_control = c.bytes; msg.msg_controllen = sizeof(c);
    struct cmsghdr *h = CMSG_FIRSTHDR(&msg); h->cmsg_level = SOL_SOCKET; h->cmsg_type = SCM_RIGHTS;
    h->cmsg_len = CMSG_LEN(sizeof(int)); memcpy(CMSG_DATA(h), &pipefd[0], sizeof(int));
    unsigned before = fd_count();
    assert(sendmsg(fd, &msg, MSG_NOSIGNAL) == (ssize_t)n);
    ready(owner.fd[2]); assert(fd_count() == before);
    stop(-EBADMSG); assert(!atomic_load(&owner.delivered));
}
static void collision(void)
{
    struct b41_agps_receiver other = {0};
    assert(!b41_agps_receiver_open(&owner, getpid(), getuid()));
    assert(b41_agps_receiver_open(&other, getpid(), getuid()) == -EADDRINUSE);
    assert(other.state == B41_AGPS_RX_CLOSED && fcntl(owner.fd[0], F_GETFD) >= 0);
    assert(!b41_agps_receiver_close(&owner));
}
static void replacement(void)
{
    int pipes[2]; assert(!b41_agps_receiver_open(&owner, getpid(), getuid()));
    int fd = owner.fd[0]; assert(!close(fd)); assert(!pipe2(pipes, O_CLOEXEC));
    if (pipes[0] != fd) assert(dup2(pipes[0], fd) == fd);
    assert(b41_agps_receiver_close(&owner) == -ESTALE);
    assert(owner.state == B41_AGPS_RX_QUARANTINED && fcntl(fd, F_GETFD) >= 0);
}
static void association_refused(void)
{
    association_error = -ESTALE;
    assert(!b41_agps_receiver_open(&owner, getpid(), getuid()));
    assert(b41_agps_receiver_start(&owner, NULL, 0, NULL) == -ESTALE);
    assert(owner.state == B41_AGPS_RX_BOUND);
    assert(b41_agps_receiver_close(&owner) == -ESTALE);
}
static void parked(void)
{
    int fd = sender();
    assert(!pipe2(receipts, O_CLOEXEC)); delivery_fd = receipts[1];
    assert(!b41_agps_receiver_open(&owner, getpid(), getuid()));
    assert(b41_agps_receiver_prepare(&owner, NULL, 0, NULL) == 1);
    assert(owner.state == B41_AGPS_RX_PREPARED);
    unsigned char p[32]; size_t n = packet(p, 250, "X", 2);
    send_packet(fd, p, n);
    struct pollfd output = {receipts[0], POLLIN, 0};
    assert(poll(&output, 1, 50) == 0);
    assert(!atomic_load(&owner.delivered));
    assert(!b41_agps_receiver_activate(&owner));
    ready(receipts[0]);
    stop(0); assert(atomic_load(&owner.delivered) == 1);
}
static void failed_activation(void)
{
    assert(!pipe2(receipts, O_CLOEXEC)); delivery_fd = receipts[1];
    assert(!b41_agps_receiver_open(&owner, getpid(), getuid()));
    assert(b41_agps_receiver_prepare(&owner, NULL, 0, NULL) == 1);
    admission_error = -ENODATA;
    assert(b41_agps_receiver_activate(&owner) == -ENODATA);
    assert(owner.state == B41_AGPS_RX_PREPARED);
    stop(-ENODATA);
    assert(!atomic_load(&owner.delivered));
}
static void parked_stop(void)
{
    assert(!pipe2(receipts, O_CLOEXEC)); delivery_fd = receipts[1];
    assert(!b41_agps_receiver_open(&owner, getpid(), getuid()));
    assert(b41_agps_receiver_prepare(&owner, NULL, 0, NULL) == 1);
    struct timespec bad = {0, 1000000000};
    assert(b41_agps_receiver_quiesce(&owner, &bad) == -EINVAL);
    assert(!atomic_load(&owner.stop));
    stop(0); assert(!atomic_load(&owner.delivered));
}
static void truncated(void)
{
    int fd = sender(); start(getpid());
    static unsigned char p[B41_AGPS_RX_MAX + 1];
    word(p, 1); word(p + 4, 264); word(p + 8, sizeof(p) - 12);
    send_packet(fd, p, sizeof(p)); ready(owner.fd[2]);
    stop(-EBADMSG); assert(!atomic_load(&owner.delivered));
}
static void *foreign_controller(void *context)
{
    struct timespec t = deadline(100);
    assert(context == &owner);
    assert(b41_agps_receiver_observe(&owner) == -EPERM);
    assert(b41_agps_receiver_activate(&owner) == -EPERM);
    assert(b41_agps_receiver_quiesce(&owner, &t) == -EPERM);
    assert(b41_agps_receiver_close(&owner) == -EPERM);
    return NULL;
}
static void observer_ownership(void)
{
    pthread_t thread;
    assert(!b41_agps_receiver_open(&owner, getpid(), getuid()));
    assert(b41_agps_receiver_prepare(&owner, NULL, 0, NULL) == 1);
    assert(!b41_agps_receiver_observe(&owner));
    assert(!pthread_create(&thread, NULL, foreign_controller, &owner));
    assert(!pthread_join(thread, NULL));
    pid_t child = fork(); assert(child >= 0);
    if (!child) { foreign_controller(&owner); _exit(0); }
    int status; assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && !WEXITSTATUS(status));
    assert(owner.state == B41_AGPS_RX_PREPARED);
    assert(!atomic_load(&owner.stop) && !atomic_load(&owner.first_error));
    stop(0);
    assert(b41_agps_receiver_observe(&owner) == -ESHUTDOWN);
}
static void observer_failure(void)
{
    int fd = sender(); delivery_error = -EPIPE; start(getpid());
    unsigned char p[32]; size_t n = packet(p, 250, "X", 2);
    send_packet(fd, p, n); ready(owner.fd[2]);
    assert(b41_agps_receiver_observe(&owner) == -EPIPE);
    assert(b41_agps_receiver_observe(&owner) == -EPIPE);
    struct pollfd done = {owner.fd[2], POLLIN, 0};
    assert(poll(&done, 1, 0) == 1 && done.revents == POLLIN);
    stop(-EPIPE); assert(!atomic_load(&owner.delivered)); close(fd);
}
int main(void)
{
    void (*cases[])(void) = {decode, lifecycle, wrong_peer, malformed, unsupported,
        native_failure, timeout_ownership, rights, collision, replacement, association_refused,
        parked, failed_activation, parked_stop, truncated, observer_ownership, observer_failure};
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        pid_t p = fork(); assert(p >= 0);
        if (!p) { cases[i](); _exit(0); }
        int status; assert(waitpid(p, &status, 0) == p);
        assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
    puts("17 receiver fixtures passed (synthetic native sink, real Linux IPC)");
    return 0;
}
