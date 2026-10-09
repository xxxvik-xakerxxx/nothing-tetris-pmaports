/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_navigation_output.h"
#include "b41_frame_worker.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>
static struct b41_navigation_output output;
static struct b41_host_adapter adapter;
static struct b41_known_callbacks callbacks;
static struct b41_agps_owner ipc;
static struct b41_frame_worker worker;
static int short_fd = -1;
ssize_t __real_write(int, const void *, size_t);
ssize_t __wrap_write(int fd, const void *data, size_t size)
{
    return __real_write(fd, data, fd == short_fd && size > 1 ? size / 2 : size);
}
static struct timespec deadline(void)
{
    struct timespec t; assert(!clock_gettime(CLOCK_MONOTONIC, &t));
    t.tv_sec += 2; return t;
}
static void sinks(int app[2], int raw[2])
{
    assert(!pipe2(app, O_NONBLOCK | O_CLOEXEC));
    assert(!pipe2(raw, O_NONBLOCK | O_CLOEXEC));
    int original_app = app[1], original_raw = raw[1];
    assert(b41_navigation_output_take(&output, &app[0], &raw[1]) == -EACCES);
    assert(app[1] == original_app && raw[1] == original_raw && output.state == B41_NAV_OUTPUT_EMPTY);
    assert(!b41_navigation_output_take(&output, &app[1], &raw[1]));
    assert(app[1] == -1 && raw[1] == -1);
    assert(!b41_navigation_output_bind(&output));
    assert(b41_navigation_output_bind(&output) == -EALREADY);
}
static struct b41_host_event event(enum b41_host_event_kind kind)
{
    struct b41_host_event e = {0}; e.kind = kind; e.length = 5;
    memcpy(e.bytes, "a\0b\r\n", e.length); return e;
}
static void read_exact(int fd, const void *data, size_t length)
{
    struct pollfd p = {fd, POLLIN, 0}; unsigned char bytes[256];
    assert(length <= sizeof(bytes));
    size_t have = 0; struct timespec end = deadline(), now;
    while (have < length) {
        assert(!clock_gettime(CLOCK_MONOTONIC, &now));
        int64_t ns = (int64_t)(end.tv_sec - now.tv_sec) * 1000000000 + end.tv_nsec - now.tv_nsec;
        assert(ns > 0);
        int ms = (int)((ns + 999999) / 1000000);
        assert(poll(&p, 1, ms) == 1 && (p.revents & POLLIN));
        ssize_t n = read(fd, bytes + have, sizeof(bytes) - have);
        assert(n > 0 && (size_t)n <= length - have);
        have += (size_t)n;
    }
    assert(!memcmp(data, bytes, length));
}
static void integrated_delivery(void)
{
    int app[2], raw[2], pair[2]; sinks(app, raw);
    assert(!socketpair(AF_UNIX, SOCK_DGRAM, 0, pair));
    struct sockaddr_un peer; socklen_t peer_len = sizeof(peer);
    memset(&peer, 0, sizeof(peer));
    assert(!getpeername(pair[0], (struct sockaddr *)&peer, &peer_len));
    assert(!b41_agps_owner_init(&ipc));
    assert(!b41_agps_owner_take(&ipc, &pair[0], &peer, peer_len));
    assert(!b41_host_adapter_init(&adapter));
    assert(!b41_host_adapter_bind(&adapter, &callbacks));
    struct b41_host_event raw_event = event(B41_HOST_OUTPUT), app_event = event(B41_HOST_APP_OUTPUT);
    app_event.bytes[0] = 'x';
    assert(!callbacks.output(raw_event.bytes, raw_event.length));
    assert(!callbacks.app_output(app_event.bytes, app_event.length));
    assert(!callbacks.frame_network());
    memset(raw_event.bytes, 0xff, raw_event.length);
    assert(!b41_frame_worker_start(&worker, &adapter, &ipc, NULL, 0));
    const unsigned char expected_raw[] = {'a', 0, 'b', '\r', '\n'};
    read_exact(raw[0], expected_raw, sizeof(expected_raw));
    read_exact(app[0], app_event.bytes, app_event.length);
    char payload[32]; size_t payload_size, packet_size; unsigned char packet[256];
    assert(!b41_frame_sync_encode(4, 0, payload, sizeof(payload), &payload_size));
    assert(!b41_agps_data_packet(payload, payload_size, packet, sizeof(packet), &packet_size));
    read_exact(pair[1], packet, packet_size);
    struct timespec end = deadline();
    assert(!b41_frame_worker_quiesce(&worker, &end));
    assert(!output.first_error && output.delivered[0] == 5 && output.delivered[1] == 5);
    assert(!b41_frame_worker_release_unused(&worker));
    assert(fcntl(output.fd[0], F_GETFD) >= 0 && fcntl(output.fd[1], F_GETFD) >= 0);
    assert(!close(app[0]) && !close(raw[0]) && !close(pair[1]));
}
static void broken_peer(void)
{
    int app[2], raw[2]; sinks(app, raw);
    struct sigaction before, after;
    assert(!sigaction(SIGPIPE, NULL, &before));
    assert(!close(raw[0]));
    struct b41_host_event e = event(B41_HOST_OUTPUT);
    assert(b41_navigation_dispatch_event(NULL, &e) == -EPIPE);
    assert(output.state == B41_NAV_OUTPUT_FAILED && output.delivered[1] == 0);
    assert(b41_navigation_dispatch_event(NULL, &e) == -EPIPE);
    assert(!sigaction(SIGPIPE, NULL, &after));
    assert(before.sa_handler == after.sa_handler && before.sa_flags == after.sa_flags);
    assert(fcntl(output.fd[1], F_GETFD) >= 0);
}
static void backpressure(void)
{
    int app[2], raw[2]; sinks(app, raw); char fill[4096] = {0};
    while (write(output.fd[1], fill, sizeof(fill)) > 0) {}
    assert(errno == EAGAIN);
    struct b41_host_event e = event(B41_HOST_OUTPUT);
    assert(b41_navigation_dispatch_event(NULL, &e) == -EAGAIN);
    assert(output.state == B41_NAV_OUTPUT_FAILED && output.delivered[1] == 0);
}
static void replaced_fd(void)
{
    int app[2], raw[2], other[2]; sinks(app, raw);
    assert(!pipe2(other, O_NONBLOCK));
    assert(dup2(other[1], output.fd[1]) == output.fd[1]);
    struct b41_host_event e = event(B41_HOST_OUTPUT);
    assert(b41_navigation_dispatch_event(NULL, &e) == -ESTALE);
    assert(fcntl(output.fd[1], F_GETFD) >= 0); /* Foreign replacement not closed. */
}
static void partial_delivery(void)
{
    int app[2], raw[2]; sinks(app, raw); short_fd = output.fd[1];
    struct b41_host_event e = event(B41_HOST_OUTPUT);
    assert(b41_navigation_dispatch_event(NULL, &e) == -EIO);
    assert(output.delivered[1] == 2);
    read_exact(raw[0], e.bytes, 2);
    assert(b41_navigation_dispatch_event(NULL, &e) == -EIO);
    struct pollfd p = {raw[0], POLLIN, 0}; assert(poll(&p, 1, 0) == 0);
}
static void existing_sigpipe(void)
{
    int app[2], raw[2]; sinks(app, raw);
    sigset_t set, pending, mask;
    sigemptyset(&set); sigaddset(&set, SIGPIPE);
    assert(!pthread_sigmask(SIG_BLOCK, &set, NULL));
    assert(!pthread_kill(pthread_self(), SIGPIPE));
    assert(!close(raw[0]));
    struct b41_host_event e = event(B41_HOST_OUTPUT);
    assert(b41_navigation_dispatch_event(NULL, &e) == -EPIPE);
    assert(!sigpending(&pending) && sigismember(&pending, SIGPIPE) == 1);
    assert(!pthread_sigmask(SIG_BLOCK, NULL, &mask) && sigismember(&mask, SIGPIPE) == 1);
}
static void unresolved_agps(void)
{
    int app[2], raw[2]; sinks(app, raw);
    struct b41_host_event e = event(B41_HOST_AGPS_DATA);
    assert(b41_navigation_dispatch_event(NULL, &e) == -EOPNOTSUPP);
    assert(!output.delivered[0] && !output.delivered[1]);
}
static void real_ptys(void)
{
    int master[2], slave[2];
    for (unsigned i = 0; i < 2; ++i) {
        master[i] = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
        assert(master[i] >= 0 && !grantpt(master[i]) && !unlockpt(master[i]));
        const char *path = ptsname(master[i]); assert(path);
        slave[i] = open(path, O_RDONLY | O_NOCTTY | O_NONBLOCK);
        assert(slave[i] >= 0);
        struct termios raw;
        assert(!tcgetattr(slave[i], &raw)); cfmakeraw(&raw);
        assert(!tcsetattr(slave[i], TCSANOW, &raw));
    }
    assert(!b41_navigation_output_take(&output, &master[0], &master[1]));
    assert(output.pty[0] >= 0 && output.pty[1] >= 0 && output.pty[0] != output.pty[1]);
    assert(!b41_navigation_output_bind(&output));
    struct b41_host_event e = event(B41_HOST_OUTPUT);
    assert(!b41_navigation_dispatch_event(NULL, &e)); read_exact(slave[1], e.bytes, e.length);
    e.kind = B41_HOST_APP_OUTPUT;
    assert(!b41_navigation_dispatch_event(NULL, &e)); read_exact(slave[0], e.bytes, e.length);
}
static void subprocess(void (*test)(void))
{
    pid_t child = fork(); assert(child >= 0);
    if (!child) { test(); _exit(0); }
    int status; assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && !WEXITSTATUS(status));
}
int main(void)
{
    subprocess(integrated_delivery); subprocess(broken_peer); subprocess(backpressure);
    subprocess(replaced_fd); subprocess(partial_delivery); subprocess(existing_sigpipe);
    subprocess(unresolved_agps);
    subprocess(real_ptys);
    puts("B41 navigation output: existing-worker callback delivery/frame coexistence and stream faults pass");
    return 0;
}
