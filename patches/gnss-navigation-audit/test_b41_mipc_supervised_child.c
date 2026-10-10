/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_mipc_supervised_child.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/ptrace.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

static struct timespec future(long ms)
{
    struct timespec t;
    assert(!clock_gettime(CLOCK_MONOTONIC, &t));
    t.tv_nsec += ms * 1000000L;
    t.tv_sec += t.tv_nsec / 1000000000L;
    t.tv_nsec %= 1000000000L;
    return t;
}

static int stage(int sealed)
{
    int fd = memfd_create("fixture", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    assert(fd >= 0 && write(fd, "fixture", 7) == 7);
    if (sealed) assert(!fcntl(fd, F_ADD_SEALS,
        F_SEAL_SEAL | F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK));
    return fd;
}

static void completed(int code)
{
    struct b41_mipc_supervision o = {0};
    struct timespec deadline = future(1000), cleanup = future(2000);
    int fd = stage(1), retained = fd;
    assert(!b41_mipc_supervision_prepare(&o, &fd, 1, &deadline, &cleanup));
    assert(fd == -1);
    pid_t child = fork();
    assert(child >= 0);
    if (!child) _exit(code);
    assert(!b41_mipc_supervision_bind(&o, child));
    assert(b41_mipc_supervision_finish(&o) == (code ? -ECHILD : 0));
    assert(o.reaped && o.terminal && WIFEXITED(o.wait_status));
    assert(WEXITSTATUS(o.wait_status) == code);
    assert(fcntl(retained, F_GETFD) == -1 && errno == EBADF);
    assert(b41_mipc_supervision_finish(&o) == -EINVAL);
}

static void traced_stop(void)
{
    struct b41_mipc_supervision o = {0};
    struct timespec deadline = future(100), cleanup = future(2000);
    int fd = stage(1);
    assert(!b41_mipc_supervision_prepare(&o, &fd, 1, &deadline, &cleanup));
    pid_t child = fork();
    assert(child >= 0);
    if (!child) {
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL)) _exit(90);
        raise(SIGSTOP);
        for (;;) pause();
    }
    siginfo_t info = {0};
    /* Leave the actual traced STOP pending for the production waiter. */
    assert(!waitid(P_PID, (id_t)child, &info, WSTOPPED | WNOWAIT));
    assert(info.si_code == CLD_TRAPPED);
    assert(!b41_mipc_supervision_bind(&o, child));
    assert(b41_mipc_supervision_finish(&o) == -ETIMEDOUT);
    assert(o.reaped && WIFSIGNALED(o.wait_status));
    assert(WTERMSIG(o.wait_status) == SIGKILL);
    assert(o.wait_owner.escalated && o.wait_error == -ETIMEDOUT);
}

static void traced_late_reap(void)
{
    int ready[2], status;
    assert(!pipe(ready));
    pid_t child = fork();
    assert(child >= 0);
    if (!child) {
        close(ready[0]);
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL)) _exit(90);
        raise(SIGSTOP);
        assert(write(ready[1], "R", 1) == 1);
        for (;;) pause();
    }
    close(ready[1]);
    assert(waitpid(child, &status, 0) == child && WIFSTOPPED(status));
    assert(!ptrace(PTRACE_SETOPTIONS, child, NULL, (void *)(unsigned long)PTRACE_O_TRACEEXIT));
    assert(!ptrace(PTRACE_CONT, child, NULL, NULL));
    char byte;
    assert(read(ready[0], &byte, 1) == 1 && byte == 'R');
    close(ready[0]);
    struct b41_mipc_supervision o = {0};
    struct timespec deadline = future(100);
    int fd = stage(1), retained = fd;
    assert(!b41_mipc_supervision_prepare(&o, &fd, 1, &deadline, &deadline));
    assert(!b41_mipc_supervision_bind(&o, child));
    /* TRACEEXIT holds the killed child before terminal reap. No invented ACK. */
    assert(b41_mipc_supervision_finish(&o) == -EINPROGRESS);
    assert(!o.reaped && !o.terminal && o.wait_error == -ETIMEDOUT);
    assert(o.wait_owner.escalated && fcntl(retained, F_GETFD) >= 0);
    assert(b41_mipc_supervision_abort_unstarted(&o) == -EINVAL);
    int resumed = 0;
    for (int i = 0; i < 1000 && !resumed; ++i) {
        pid_t result = waitpid(child, &status, WNOHANG);
        assert(result == 0 || (result == child && WIFSTOPPED(status)));
        if (!ptrace(PTRACE_CONT, child, NULL, NULL)) resumed = 1;
        else { assert(errno == ESRCH); struct timespec pause_time = {0, 1000000};
            nanosleep(&pause_time, NULL); }
    }
    assert(resumed);
    int rc = -EINPROGRESS;
    for (int i = 0; i < 1000 && !o.reaped; ++i) {
        rc = b41_mipc_supervision_finish(&o);
        if (!o.reaped) {
            assert(rc == -EINPROGRESS && o.wait_error == -ETIMEDOUT);
            assert(fcntl(retained, F_GETFD) >= 0);
            struct timespec pause_time = {0, 1000000};
            nanosleep(&pause_time, NULL);
        }
    }
    assert(rc == -ETIMEDOUT && o.reaped && o.terminal);
    assert(WIFSIGNALED(o.wait_status) && WTERMSIG(o.wait_status) == SIGKILL);
    assert(o.wait_error == -ETIMEDOUT && o.wait_owner.first_error == -ETIMEDOUT);
    assert(fcntl(retained, F_GETFD) == -1 && errno == EBADF);
}

int main(void)
{
    completed(0);
    completed(7);
    traced_stop();
    traced_late_reap();
    struct timespec deadline = future(100), cleanup = future(2000);
    struct b41_mipc_supervision o = {0};
    int fd = stage(0);
    assert(b41_mipc_supervision_prepare(&o, &fd, 1, &deadline, &cleanup) == -EPERM);
    assert(!o.entered && fd >= 0);
    close(fd);
    fd = stage(1);
    int aliases[2] = {fd, dup(fd)};
    assert(b41_mipc_supervision_prepare(&o, aliases, 2, &deadline, &cleanup) == -EEXIST);
    close(aliases[1]);
    assert(!b41_mipc_supervision_prepare(&o, &fd, 1, &deadline, &cleanup));
    pid_t child = fork();
    assert(child >= 0);
    if (!child) { for (;;) pause(); }
    assert(!b41_mipc_supervision_bind(&o, child));
    assert(b41_mipc_supervision_abort_unstarted(&o) == -EINVAL);
    assert(b41_mipc_supervision_finish(&o) == -ETIMEDOUT);
    assert(o.reaped && WIFSIGNALED(o.wait_status) && WTERMSIG(o.wait_status) == SIGKILL);

    struct b41_mipc_supervision unstarted = {0};
    deadline = future(1000); cleanup = future(2000); fd = stage(1);
    assert(!b41_mipc_supervision_prepare(&unstarted, &fd, 1, &deadline, &cleanup));
    assert(!b41_mipc_supervision_abort_unstarted(&unstarted));
    assert(unstarted.terminal && !unstarted.reaped);

    struct b41_mipc_supervision ambiguous = {0};
    fd = stage(1);
    int retained = fd;
    assert(!b41_mipc_supervision_prepare(&ambiguous, &fd, 1, &deadline, &cleanup));
    assert(b41_mipc_supervision_bind(&ambiguous, getpid()) == -ECHILD);
    assert(b41_mipc_supervision_finish(&ambiguous) == -ECHILD);
    assert(!ambiguous.reaped && !ambiguous.terminal);
    assert(fcntl(retained, F_GETFD) >= 0);
    assert(b41_mipc_supervision_abort_unstarted(&ambiguous) == -EINVAL);
    /* Fixture process exit owns quarantine disposal, not a production reset. */
    close(retained);
    return 0;
}
