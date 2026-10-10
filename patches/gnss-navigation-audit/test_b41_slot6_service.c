/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_slot6_service.h"
#include "b41_frame_worker.h"
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <poll.h>
#include <sys/wait.h>
#include <unistd.h>

static void fixture(unsigned scenario)
{
    struct b41_host_adapter adapter = {0};
    struct b41_known_callbacks callbacks;
    struct b41_agps_owner ipc = {0};
    struct b41_host_event event;
    int sockets[2];
    uint8_t received[B41_HOST_OUTPUT_MAX];
    assert(b41_host_adapter_init(&adapter) == 0);
    assert(b41_host_adapter_bind(&adapter, &callbacks) == 0);
    assert(b41_slot6_service_bind(&adapter, &callbacks) == 0);
    assert(b41_slot6_service_bind(&adapter, &callbacks) == -EALREADY);
    assert(b41_agps_owner_init(&ipc) == 0);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0);
    struct sockaddr_un peer = {0};
    socklen_t peer_size = sizeof(peer);
    assert(getpeername(sockets[0], (struct sockaddr *)&peer, &peer_size) == 0);
    assert(b41_agps_owner_take(&ipc, &sockets[0], &peer, peer_size) == 0);
    if (scenario == 0) {
        char string[] = "$PMTK738,1*00\r";
        assert(callbacks.agps(0x10000, 0x12340000, (void *)1) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == -EAGAIN);
        assert(callbacks.agps(0x10000, 0xffff0001, string) == 0);
        string[0] = 'X';
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(event.bytes[13] == '$');
        assert(b41_slot6_service_dispatch(&ipc, &event) == 0);
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == (ssize_t)event.length);
        assert(!memcmp(received, event.bytes, event.length));
        assert(callbacks.agps(0, 1, NULL) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0 && event.length == 9);
        assert(b41_slot6_service_dispatch(&ipc, &event) == 0);
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == 9);
        assert(!memcmp(received, event.bytes, 9));
        assert(callbacks.agps(0, 1, "") == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0 && event.length == 14);
        assert(b41_slot6_service_dispatch(&ipc, &event) == 0);
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == 14);
        assert(!memcmp(received, event.bytes, 14));
        assert(callbacks.agps(0x10001, 0, (void *)1) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0 && event.length == 8);
        assert(b41_slot6_service_dispatch(&ipc, &event) == 0);
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == 8);
        assert(!memcmp(received, event.bytes, 8));
    } else if (scenario == 1) {
        char longest[B41_HOST_OUTPUT_MAX - 13u];
        memset(longest, 'A', sizeof(longest)); longest[sizeof(longest)-1] = 0;
        assert(callbacks.agps(0, 1, longest) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0 && event.length == sizeof(received));
        assert(b41_slot6_service_dispatch(&ipc, &event) == 0);
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == (ssize_t)sizeof(received));
        char too_long[B41_HOST_OUTPUT_MAX - 12u];
        memset(too_long, 'B', sizeof(too_long)); too_long[sizeof(too_long)-1] = 0;
        assert(callbacks.agps(0, 1, too_long) == -EMSGSIZE);
        assert(callbacks.agps(1, 0, NULL) == -EMSGSIZE);
    } else if (scenario == 2) {
        assert(callbacks.agps(0, 1, "abc") == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        struct b41_host_event bad = event;
        bad.bytes[9] = 0xff;
        assert(b41_slot6_service_dispatch(&ipc, &bad) == -EBADMSG);
        bad = event; bad.bytes[8] = 2;
        assert(b41_slot6_service_dispatch(&ipc, &bad) == -EBADMSG);
        bad = event; bad.bytes[14] = 0;
        assert(b41_slot6_service_dispatch(&ipc, &bad) == -EBADMSG);
        bad = event; bad.bytes[bad.length-1] = 'X';
        assert(b41_slot6_service_dispatch(&ipc, &bad) == -EBADMSG);
        bad = event; ++bad.length;
        assert(b41_slot6_service_dispatch(&ipc, &bad) == -EBADMSG);
        bad = event; bad.bytes[4] = 152;
        assert(b41_slot6_service_dispatch(&ipc, &bad) == -EBADMSG);
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == -1 && errno == EAGAIN);
    } else if (scenario == 3) {
        for (unsigned i = 0; i < B41_HOST_QUEUE_SIZE; ++i)
            assert(callbacks.agps(1, 0, NULL) == 0);
        assert(callbacks.agps(1, 0, NULL) == -ENOBUFS);
        assert(callbacks.agps(0, 0, NULL) == -ENOBUFS);
    } else if (scenario == 4) {
        assert(callbacks.agps(15, 1, NULL) == -EOPNOTSUPP);
        assert(callbacks.agps(0, 0, NULL) == -EOPNOTSUPP);
    } else if (scenario == 5) {
        assert(callbacks.agps(1, 0, NULL) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(close(sockets[1]) == 0);
        assert(b41_slot6_service_dispatch(&ipc, &event) < 0);
        assert(ipc.first_error < 0);
    } else {
        struct b41_frame_worker worker = {.dispatch = b41_slot6_service_dispatch};
        struct pollfd peer_fd = {sockets[1], POLLIN, 0};
        struct timespec deadline;
        assert(b41_frame_worker_start(&worker, &adapter, &ipc, NULL, 0) == 0);
        assert(callbacks.agps(0, 1, "abc") == 0);
        assert(poll(&peer_fd, 1, 1000) == 1 && (peer_fd.revents & POLLIN));
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == 17);
        assert(received[4] == 150 && !memcmp(received + 13, "abc", 4));
        assert(callbacks.agps(1, 0, (void *)1) == 0);
        assert(poll(&peer_fd, 1, 1000) == 1 && (peer_fd.revents & POLLIN));
        assert(recv(sockets[1], received, sizeof(received), MSG_DONTWAIT) == 8);
        assert(received[4] == 152);
        assert(clock_gettime(CLOCK_MONOTONIC, &deadline) == 0);
        ++deadline.tv_sec;
        assert(b41_frame_worker_quiesce(&worker, &deadline) == 0);
        assert(b41_frame_worker_release_unused(&worker) == 0);
    }
    /* Process-lifetime callback/storage/IPC ownership: no premature unbind. */
    _exit(0);
}
int main(void)
{
    for (unsigned scenario = 0; scenario < 7; ++scenario) {
        pid_t child = fork(); assert(child >= 0);
        if (!child) fixture(scenario);
        int status;
        assert(waitpid(child, &status, 0) == child);
        assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
    return 0;
}
