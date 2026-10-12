/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "b41_native_receiver_host.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <string.h>
#include <sys/eventfd.h>
#include <sys/wait.h>
#include <unistd.h>

static struct b41_native_control control;
static struct b41_known_callbacks callbacks;

static void failed_worker_test(void)
{
    struct b41_host_adapter adapter = {0};
    struct b41_known_callbacks worker_callbacks;
    struct b41_agps_owner ipc = {0};
    struct b41_frame_worker worker = {0};
    struct sockaddr_un peer = {0};
    socklen_t length = sizeof(peer);
    int pair[2];
    assert(!socketpair(AF_UNIX, SOCK_DGRAM, 0, pair));
    assert(!getpeername(pair[0], (struct sockaddr *)&peer, &length));
    assert(!b41_agps_owner_init(&ipc));
    assert(!b41_agps_owner_take(&ipc, &pair[0], &peer, length));
    assert(!close(pair[1]));
    assert(!b41_host_adapter_init(&adapter));
    assert(!b41_host_adapter_bind(&adapter, &worker_callbacks));
    assert(!worker_callbacks.frame_network());
    assert(!b41_frame_worker_start(&worker, &adapter, &ipc, NULL, 0));
    struct pollfd done = {worker.done_fd, POLLIN, 0};
    assert(poll(&done, 1, 1000) == 1 && (done.revents & POLLIN));
    int failure = atomic_load(&worker.failure);
    assert(failure < 0 && !b41_host_adapter_error(&adapter));
    assert(worker.state == B41_WORKER_RUNNING);
    assert(b41_native_worker_admission(&worker) == failure);
    struct timespec until;
    assert(!clock_gettime(CLOCK_MONOTONIC, &until));
    ++until.tv_sec;
    assert(b41_frame_worker_quiesce(&worker, &until) == failure);
    assert(worker.state == B41_WORKER_QUARANTINED);
    assert(fcntl(ipc.fd, F_GETFD) >= 0);
    assert(fcntl(worker.done_fd, F_GETFD) >= 0);
    /* Failed resources remain owned until this fixture child exits. */
}

static void worker_admission_test(void)
{
    struct b41_frame_worker worker = {0};
    uint64_t one = 1, received = 0;
    assert(b41_native_worker_admission(NULL) == -EINVAL);
    assert(b41_native_worker_admission(&worker) == -ESHUTDOWN);
    worker.state = B41_WORKER_RUNNING;
    atomic_init(&worker.failure, 0);
    atomic_init(&worker.stop_requested, 0);
    worker.done_fd = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
    assert(worker.done_fd >= 0);
    assert(!b41_native_worker_admission(&worker));
    /* Real dispatch failures retain RUNNING until controller quiescence. */
    atomic_store(&worker.failure, -EPIPE);
    assert(b41_native_worker_admission(&worker) == -EPIPE);
    assert(write(worker.done_fd, &one, sizeof(one)) == (ssize_t)sizeof(one));
    assert(b41_native_worker_admission(&worker) == -EPIPE);
    atomic_store(&worker.failure, 0); /* Fixture only; no runtime error reset. */
    assert(b41_native_worker_admission(&worker) == -ESHUTDOWN);
    assert(b41_native_worker_admission(&worker) == -ESHUTDOWN);
    assert(read(worker.done_fd, &received, sizeof(received)) == (ssize_t)sizeof(received));
    assert(received == 1); /* Admission did not steal the quiescence wake. */
    atomic_store(&worker.stop_requested, 1);
    assert(b41_native_worker_admission(&worker) == -ESHUTDOWN);
    atomic_store(&worker.failure, -ECONNREFUSED);
    assert(b41_native_worker_admission(&worker) == -ECONNREFUSED);
    atomic_store(&worker.failure, 0);
    atomic_store(&worker.stop_requested, 0);
    assert(!close(worker.done_fd));
    assert(b41_native_worker_admission(&worker) == -EIO);
    worker.done_fd = -1;
    assert(b41_native_worker_admission(&worker) == -EBADF);
}

static void control_test(void)
{
    unsigned events = 77;
    struct b41_native_control spare = {0};
    assert(!b41_native_control_init(&control));
    assert(b41_native_control_init(&control) == -EALREADY);
    assert(!b41_native_control_init(&spare));
    assert(!b41_native_control_discard_unbound(&spare));
    assert(b41_native_control_init(&spare) == -EALREADY);
    assert(!b41_native_control_bind(&control, &callbacks));
    assert(b41_native_control_bind(&control, &callbacks) == -EALREADY);
    assert(b41_native_control_discard_unbound(&control) == -EBUSY);
    assert(!callbacks.notify(0) && !callbacks.notify(7) && !callbacks.notify(13));
    assert(!b41_native_control_take(&control, &events));
    assert(events == (B41_NATIVE_REPORT | B41_NATIVE_PROHIBITED | B41_NATIVE_RESTART));
    assert(!b41_native_control_take(&control, &events) && !events);
    for (unsigned i = 0; i < 14; ++i)
        if (i != 0 && i != 3 && i != 7 && i != 13) assert(!callbacks.notify(i));
    assert(callbacks.notify(3) == -EOPNOTSUPP);
    assert(b41_native_control_take(&control, &events) == -EOPNOTSUPP);
    assert(events == B41_NATIVE_UNSUPPORTED);
    assert(callbacks.notify(0) == -EOPNOTSUPP);
    assert(b41_native_control_take(&control, &events) == -EOPNOTSUPP);
    assert(events == B41_NATIVE_REPORT);
    /* Bound process-lifetime storage/fd intentionally retained until _exit. */
}

static void ack_test(void)
{
    struct b41_native_stop_snapshot a = {0}, b;
    unsigned mask = 99;
    a.base = 0x10000000u;
    for (unsigned i = 0; i < B41_NATIVE_THREADS; ++i) {
        a.threads[i].marker = 7;
        a.threads[i].index = i;
        a.threads[i].handle = 1234 + i;
        a.threads[i].stop = a.base + 0x529f18u;
        a.threads[i].wake = a.base + 0x529418u;
    }
    b = a;
    for (unsigned i = 0; i < B41_NATIVE_THREADS; ++i) b.threads[i].marker = -1;
    assert(!b41_native_join_ack(&a, &b, &mask));
    assert(mask == (1u << B41_NATIVE_THREADS) - 1);
    for (unsigned i = 0; i < B41_NATIVE_THREADS; ++i) {
        mask = 99;
        b.threads[i].marker = 7;
        assert(b41_native_join_ack(&a, &b, &mask) == -EBUSY && mask == 99);
        b.threads[i].marker = -1;
        ++b.threads[i].handle;
        assert(b41_native_join_ack(&a, &b, &mask) == -ESTALE && mask == 99);
        --b.threads[i].handle;
    }
    a.offload = 1;
    assert(b41_native_join_ack(&a, &b, &mask) == -EOPNOTSUPP);
    a.offload = 0;
    a.threads[0].marker = -1;
    assert(b41_native_join_ack(&a, &b, &mask) == -ENODATA);
    a.threads[0].marker = 7;
    a.threads[5].marker = b.threads[5].marker = -1;
    a.threads[5].handle = b.threads[5].handle = UINT64_MAX;
    assert(!b41_native_join_ack(&a, &b, &mask));
    assert(mask == (((1u << B41_NATIVE_THREADS) - 1) & ~(1u << 5)));
    a.threads[5].handle = b.threads[5].handle = 1239;
    assert(b41_native_join_ack(&a, &b, &mask) == -ESTALE);
}

static void supervisor_test(void)
{
    struct timespec now, deadline, cleanup;
    int status = 99;
    pid_t child;
    assert(!clock_gettime(CLOCK_MONOTONIC, &now));
    deadline = cleanup = now;
    deadline.tv_sec += 2;
    cleanup.tv_sec += 3;
    child = fork();
    assert(child >= 0);
    if (!child) _exit(0);
    assert(!b41_native_child_wait(child, &deadline, &cleanup, &status));
    assert(WIFEXITED(status) && !WEXITSTATUS(status));
    assert(b41_native_child_wait(child, &deadline, &cleanup, &status) == -ECHILD);
    child = fork();
    assert(child >= 0);
    if (!child) { for (;;) pause(); }
    assert(!clock_gettime(CLOCK_MONOTONIC, &now));
    deadline = now;
    cleanup = now; cleanup.tv_sec += 2;
    assert(b41_native_child_wait(child, &deadline, &cleanup, &status) == -ETIMEDOUT);
    assert(WIFSIGNALED(status));
    assert(b41_native_child_wait(0, &deadline, &cleanup, &status) == -EINVAL);
}

int main(void)
{
    pid_t child;
    int status;
    worker_admission_test();
    ack_test();
    supervisor_test();
    child = fork();
    assert(child >= 0);
    if (!child) { failed_worker_test(); _exit(0); }
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && !WEXITSTATUS(status));
    child = fork();
    assert(child >= 0);
    if (!child) { control_test(); _exit(0); }
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && !WEXITSTATUS(status));
    return 0;
}
