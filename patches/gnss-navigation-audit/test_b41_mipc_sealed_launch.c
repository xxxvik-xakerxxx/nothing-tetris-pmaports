/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_mipc_sealed_isolate.h"
#include "b41_mipc_loader_root.h"
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/wait.h>
#include <unistd.h>

static struct timespec future(unsigned seconds)
{
    struct timespec t;
    assert(!clock_gettime(CLOCK_MONOTONIC, &t));
    t.tv_sec += seconds;
    return t;
}

static void read_file(const char *path, char *text, size_t size)
{
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    assert(fd >= 0);
    ssize_t n = read(fd, text, size - 1);
    assert(n >= 0 && (size_t)n < size - 1);
    text[n] = 0;
    assert(!close(fd));
}

static void child_path(char *path, size_t size, pid_t child, const char *suffix)
{
    assert(snprintf(path, size, "/proc/%ld/%s", (long)child, suffix) < (int)size);
}

static void check_namespaces(pid_t child)
{
    const char *names[] = { "ns/pid", "ns/mnt", "ns/net" };
    char path[128], self[128];
    struct stat a, b;
    for (unsigned i = 0; i < 3; ++i) {
        child_path(path, sizeof(path), child, names[i]);
        assert(snprintf(self, sizeof(self), "/proc/self/%s", names[i]) < (int)sizeof(self));
        assert(!stat(path, &a) && !stat(self, &b));
        /* NEWNET changes the launcher too; compare that namespace to its parent. */
        if (i == 2) {
            child_path(self, sizeof(self), getppid(), names[i]);
            assert(!stat(self, &b));
        }
        assert(a.st_ino != b.st_ino || a.st_dev != b.st_dev);
    }
}

static void observe_blocked_control(pid_t child)
{
    char path[128], text[8192];
    int ready = 0;
    for (unsigned attempt = 0; attempt < 500 && !ready; ++attempt) {
        siginfo_t info = {0};
        assert(!waitid(P_PID, (id_t)child, &info, WEXITED | WNOHANG | WNOWAIT));
        assert(!info.si_pid); /* Early startup/capability failure is never a skip. */
        child_path(path, sizeof(path), child, "status");
        read_file(path, text, sizeof(text));
        ready = strstr(text, "Uid:\t65534\t65534\t65534\t65534") &&
            strstr(text, "Gid:\t65534\t65534\t65534\t65534") &&
            strstr(text, "NoNewPrivs:\t1") && strstr(text, "Seccomp:\t2");
        if (!ready) { struct timespec delay = {0, 10000000}; assert(!nanosleep(&delay, NULL)); }
    }
    assert(ready);
    assert(strstr(text, "SigBlk:\t0000000000000000"));
    assert(strstr(text, "CapEff:\t0000000000000000"));
    assert(strstr(text, "CapPrm:\t0000000000000000"));
    assert(strstr(text, "CapBnd:\t0000000000000000"));
    child_path(path, sizeof(path), child, "root/vendor/lib64/libmnl.so");
    struct stat library;
    assert(!stat(path, &library) && library.st_size == (1UL << 20) + 17);
    child_path(path, sizeof(path), child, "limits");
    read_file(path, text, sizeof(text));
    char *limit_row = strstr(text, "Max file size");
    unsigned long soft, hard;
    assert(limit_row && sscanf(limit_row, "Max file size %lu %lu", &soft, &hard) == 2);
    assert(soft == (1UL << 20) && hard == (1UL << 20));
    child_path(path, sizeof(path), child, "fd");
    DIR *fds = opendir(path);
    assert(fds); /* Observing the nondumpable child requires CAP_SYS_PTRACE. */
    unsigned count = 0;
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(fds))) {
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        assert(!strcmp(entry->d_name, "0") || !strcmp(entry->d_name, "1") ||
            !strcmp(entry->d_name, "2"));
        ++count;
    }
    assert(!errno && count == 3 && !closedir(fds));
    check_namespaces(child);
    child_path(path, sizeof(path), child, "root");
    struct statfs fs;
    struct statvfs flags;
    assert(!statfs(path, &fs) && fs.f_type == TMPFS_MAGIC);
    assert(!statvfs(path, &flags) && (flags.f_flag & ST_RDONLY));
    child_path(path, sizeof(path), child, "root/proc/1/status");
    read_file(path, text, sizeof(text));
    assert(strstr(text, "\nPid:\t1\n"));
}

enum scenario { CONTROL, START_FAILURE, DEADLINE };

static void run_case(enum scenario scenario)
{
    char root[] = "/tmp/b41-sealed-launch-XXXXXX", path[256];
    assert(mkdtemp(root));
    int stage[B41_MIPC_PROVIDER_COUNT + 2], retained[B41_MIPC_PROVIDER_COUNT + 2];
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT + 2; ++i) {
        stage[i] = retained[i] = memfd_create("mount-fixture-not-authenticated-ELF",
            MFD_CLOEXEC | MFD_ALLOW_SEALING);
        assert(stage[i] >= 3);
        assert(write(stage[i], &i, sizeof(i)) == (ssize_t)sizeof(i));
        if (i == B41_MIPC_PROVIDER_COUNT + 1) {
            char bytes[65536];
            memset(bytes, 'L', sizeof(bytes));
            size_t remaining = (1UL << 20) + 17 - sizeof(i);
            while (remaining) {
                size_t count = remaining < sizeof(bytes) ? remaining : sizeof(bytes);
                assert(write(stage[i], bytes, count) == (ssize_t)count);
                remaining -= count;
            }
        }
        assert(!fchmod(stage[i], !i || i == B41_MIPC_PROVIDER_COUNT ? 0555 : 0444));
        assert(!fcntl(stage[i], F_ADD_SEALS,
            F_SEAL_SEAL | F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK));
    }
    struct b41_mipc_supervision owner = {0};
    struct timespec deadline = future(10), cleanup = future(15);
    assert(!b41_mipc_supervision_prepare(&owner, stage,
        B41_MIPC_PROVIDER_COUNT + 2, &deadline, &cleanup));
    int output[2];
    assert(!pipe2(output, O_CLOEXEC));
    assert(fcntl(output[1], F_SETPIPE_SZ, 4096) == 4096);
    assert(!fcntl(output[1], F_SETFL, O_NONBLOCK));
    char fill[4096];
    memset(fill, 'X', sizeof(fill));
    ssize_t n;
    while ((n = write(output[1], fill, sizeof(fill))) > 0) assert(n == (ssize_t)sizeof(fill));
    assert(n == -1 && errno == EAGAIN);
    assert(!fcntl(output[1], F_SETFL, 0));
    assert(dup2(output[1], STDOUT_FILENO) == STDOUT_FILENO);
    assert(!close(output[1]));
    int input = open("/dev/null", O_RDONLY | O_CLOEXEC);
    assert(input >= 3 && dup2(input, STDIN_FILENO) == STDIN_FILENO && !close(input));
    if (scenario == START_FAILURE) {
        assert(snprintf(path, sizeof(path), "%s/not-empty", root) < (int)sizeof(path));
        int fd = open(path, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
        assert(fd >= 0 && !close(fd));
    }
    sigset_t signals;
    const struct rlimit log_bound = { 1UL << 20, 64UL << 20 };
    assert(!setrlimit(RLIMIT_FSIZE, &log_bound));
    assert(!sigfillset(&signals) && !sigprocmask(SIG_SETMASK, &signals, NULL));
    assert(!b41_mipc_sealed_probe_spawn(&owner, root, "control"));
    assert(owner.bind_attempted && owner.child > 0 && !owner.terminal);
    for (unsigned i = 0; i < owner.count; ++i) assert(fcntl(retained[i], F_GETFD) >= 0);
    assert(b41_mipc_supervision_abort_unstarted(&owner) == -EINVAL);
    assert(!close(STDOUT_FILENO)); /* Only the actual child retains a pipe writer. */
    if (scenario != START_FAILURE) {
        observe_blocked_control(owner.child);
        assert(snprintf(path, sizeof(path), "%s/apex", root) < (int)sizeof(path));
        assert(access(path, F_OK) == -1 && errno == ENOENT);
    }
    if (scenario == CONTROL) {
        char text[32768];
        size_t used = 0;
        while ((n = read(output[0], text + used, sizeof(text) - used - 1)) > 0) {
            used += (size_t)n;
            assert(used < sizeof(text) - 1);
        }
        assert(!n);
        text[used] = 0;
        assert(strstr(text, "CONTROL: eight network/device/namespace/privilege denials, failures=0"));
    }
    int rc = b41_mipc_supervision_finish(&owner);
    assert(owner.reaped && owner.terminal);
    if (scenario == CONTROL) assert(!rc && WIFEXITED(owner.wait_status) && !WEXITSTATUS(owner.wait_status));
    else if (scenario == START_FAILURE)
        assert(rc == -ECHILD && WIFEXITED(owner.wait_status) && WEXITSTATUS(owner.wait_status) == 125);
    else assert(rc == -ETIMEDOUT && owner.wait_owner.escalated &&
        WIFSIGNALED(owner.wait_status) && WTERMSIG(owner.wait_status) == SIGKILL);
    for (unsigned i = 0; i < owner.count; ++i)
        assert(fcntl(retained[i], F_GETFD) == -1 && errno == EBADF);
    assert(!close(output[0]));
    if (scenario == START_FAILURE) {
        assert(snprintf(path, sizeof(path), "%s/not-empty", root) < (int)sizeof(path));
        assert(!unlink(path));
    }
    assert(!rmdir(root));
}

int main(void)
{
    assert(geteuid() == 0);
    for (int fd = 0; fd < 3; ++fd) assert(fcntl(fd, F_GETFD) >= 0);
    for (enum scenario which = CONTROL; which <= DEADLINE; ++which) {
        /* Namespace changes remain in a dedicated launcher, not the test parent. */
        pid_t launcher = fork();
        assert(launcher >= 0);
        if (!launcher) { run_case(which); _exit(0); }
        int status;
        assert(waitpid(launcher, &status, 0) == launcher);
        assert(WIFEXITED(status) && !WEXITSTATUS(status));
    }
    puts("sealed launch fixture: control, startup failure, timeout/reap passed");
    return 0;
}
