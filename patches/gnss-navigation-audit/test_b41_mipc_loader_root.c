/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_mipc_loader_root.h"
#include "b41_mipc_supervised_child.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static void deny_mount_flags(unsigned flags)
{
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_mount, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[3])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, flags, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EACCES),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = { .len = sizeof(filter) / sizeof(filter[0]), .filter = filter };
    assert(!prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0));
    assert(!prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program));
}

static struct timespec future(unsigned seconds)
{
    struct timespec t;
    assert(!clock_gettime(CLOCK_MONOTONIC, &t));
    t.tv_sec += seconds;
    return t;
}

static void failed_mount(const int *providers, unsigned denied_flags)
{
    char root[] = "/tmp/b41-loader-fault-XXXXXX";
    assert(mkdtemp(root));
    struct b41_mipc_supervision owner = {0};
    int moved[B41_MIPC_PROVIDER_COUNT], retained[B41_MIPC_PROVIDER_COUNT];
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT; ++i) {
        moved[i] = retained[i] = dup(providers[i]);
        assert(moved[i] >= 0);
    }
    struct timespec deadline = future(5), cleanup = future(7);
    assert(!b41_mipc_supervision_prepare(&owner, moved, B41_MIPC_PROVIDER_COUNT, &deadline, &cleanup));
    int report[2], release[2];
    assert(!pipe(report) && !pipe(release));
    pid_t child = fork();
    assert(child >= 0);
    if (!child) {
        close(report[0]); close(release[1]);
        deny_mount_flags(denied_flags);
        int result = b41_mipc_loader_root(root, owner.stage, owner.count);
        assert(result == -EACCES); /* Real denial at bind/remount, not unshare failure. */
        assert(write(report[1], &result, sizeof(result)) == (ssize_t)sizeof(result));
        char byte;
        assert(read(release[0], &byte, 1) == 1);
        _exit(7);
    }
    close(report[1]); close(release[0]);
    assert(!b41_mipc_supervision_bind(&owner, child));
    int failure;
    assert(read(report[0], &failure, sizeof(failure)) == (ssize_t)sizeof(failure));
    assert(failure == -EACCES && !owner.reaped);
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT; ++i)
        assert(fcntl(retained[i], F_GETFD) >= 0);
    char unchanged[512];
    assert(snprintf(unchanged, sizeof(unchanged), "%s/apex", root) < (int)sizeof(unchanged));
    assert(access(unchanged, F_OK) == -1 && errno == ENOENT);
    assert(write(release[1], "X", 1) == 1);
    assert(b41_mipc_supervision_finish(&owner) == -ECHILD);
    assert(owner.reaped && WIFEXITED(owner.wait_status) && WEXITSTATUS(owner.wait_status) == 7);
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT; ++i)
        assert(fcntl(retained[i], F_GETFD) == -1 && errno == EBADF);
    close(report[0]); close(release[1]);
    assert(!rmdir(root));
}

int main(void)
{
    /* Filesystem fixture only: these bytes are NOT library authentication. */
    assert(geteuid() == 0);
    char root[] = "/tmp/b41-loader-root-XXXXXX";
    assert(mkdtemp(root));
    int fd[B41_MIPC_PROVIDER_COUNT + 2];
    const int seals = F_SEAL_SEAL | F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK;
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT + 2; ++i) {
        fd[i] = memfd_create("filesystem-fixture-not-ELF", MFD_ALLOW_SEALING | MFD_CLOEXEC);
        assert(fd[i] >= 0);
        assert(write(fd[i], &i, sizeof(i)) == (ssize_t)sizeof(i));
        assert(!fchmod(fd[i], i == 0 || i == B41_MIPC_PROVIDER_COUNT ? 0555 : 0444));
        assert(!fcntl(fd[i], F_ADD_SEALS, seals));
    }
    assert(b41_mipc_loader_root(root, fd, 0) == -EINVAL);
    failed_mount(fd, MS_BIND);
    failed_mount(fd, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOSUID | MS_NODEV);
    pid_t child = fork();
    assert(child >= 0);
    if (!child) {
        assert(!b41_mipc_loader_root_probe(root, fd, B41_MIPC_PROVIDER_COUNT,
            fd[B41_MIPC_PROVIDER_COUNT], fd[B41_MIPC_PROVIDER_COUNT + 1]));
        const char *paths[] = {
            "apex/com.android.runtime/bin/linker64", "apex/com.android.runtime/lib64/bionic/libc.so",
            "apex/com.android.runtime/lib64/bionic/libm.so", "apex/com.android.runtime/lib64/bionic/libdl.so",
            "system/lib64/libc++.so", "system/lib64/liblog.so", "vendor/lib64/libmipc.so",
            "vendor/lib64/libmtkrillog.so", "vendor/lib64/libtrm.so", "vendor/lib64/libmtkproperty.so",
            "probe", "vendor/lib64/libmnl.so",
        };
        for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT + 2; ++i) {
            char target[512];
            assert(snprintf(target, sizeof(target), "%s/%s", root, paths[i]) < (int)sizeof(target));
            int opened = open(target, O_RDONLY | O_CLOEXEC);
            assert(opened >= 0);
            struct stat from, mounted;
            assert(!fstat(fd[i], &from) && !fstat(opened, &mounted));
            assert(from.st_ino == mounted.st_ino && from.st_dev == mounted.st_dev);
            unsigned value;
            assert(read(opened, &value, sizeof(value)) == (ssize_t)sizeof(value) && value == i);
            close(opened);
            assert(open(target, O_WRONLY) == -1 && errno == EROFS);
            assert(pwrite(fd[i], "X", 1, 0) == -1 && errno == EPERM);
        }
        /* No linker or shared-library bytes executed. Namespace exit cleans mounts. */
        _exit(0);
    }
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT + 2; ++i) close(fd[i]);
    assert(!rmdir(root));  /* Child's private tmpfs never populated parent directory. */
    return 0;
}
