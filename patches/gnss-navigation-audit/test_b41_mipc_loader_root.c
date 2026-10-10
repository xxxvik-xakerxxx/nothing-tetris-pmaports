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
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__ || __SIZEOF_POINTER__ != 8
#error This syscall fault fixture requires little-endian 64-bit native CI
#endif

#define LONG_SIZE (65536u + 17u)
static unsigned char long_payload[LONG_SIZE];

static void check_payload(int fd, size_t length)
{
    unsigned char bytes[4096];
    size_t offset = 0;
    assert(length <= LONG_SIZE);
    while (offset < length) {
        size_t amount = length - offset;
        if (amount > sizeof(bytes)) amount = sizeof(bytes);
        ssize_t n = pread(fd, bytes, amount, (off_t)offset);
        assert(n > 0 && (size_t)n <= amount);
        assert(!memcmp(bytes, long_payload + offset, (size_t)n));
        offset += (size_t)n;
    }
}

static void deny_second_read(int source)
{
    /* Native CI is little-endian 64-bit: pread64 offset is argument 3.
     * Permit the complete first chunk; fail only its real next syscall.
     */
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_pread64, 0, 7),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned)source, 0, 5),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[3])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 65536, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[3]) + 4),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EIO),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = { .len = sizeof(filter) / sizeof(filter[0]), .filter = filter };
    assert(!prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0));
    assert(!prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program));
}

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

static void failed_root(const int *providers, unsigned denied_flags, int copy_error)
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
        if (copy_error == EIO) deny_second_read(owner.stage[0]);
        else if (copy_error == EFBIG) {
            const struct rlimit bound = {8192, 8192};
            assert(signal(SIGXFSZ, SIG_IGN) != SIG_ERR);
            assert(!setrlimit(RLIMIT_FSIZE, &bound));
        } else deny_mount_flags(denied_flags);
        int expected = copy_error ? -copy_error : -EACCES;
        int result = b41_mipc_loader_root(root, owner.stage, owner.count);
        if (result != expected)
            fprintf(stderr, "loader root fault flags=%u returned=%d expected=%d\n",
                    denied_flags, result, expected);
        assert(result == expected);
        if (copy_error) {
            char partial[512];
            assert(snprintf(partial, sizeof(partial), "%s/apex/com.android.runtime/bin/linker64",
                root) < (int)sizeof(partial));
            int fd = open(partial, O_RDONLY | O_CLOEXEC);
            struct stat info;
            off_t length = copy_error == EIO ? 65536 : 8192;
            assert(fd >= 0 && !fstat(fd, &info));
            assert(info.st_size == length && (info.st_mode & 0777) == 0600);
            /* Reading the copied prefix does not hit the denied source fd. */
            check_payload(fd, (size_t)length);
            assert(!close(fd));
        }
        assert(write(report[1], &result, sizeof(result)) == (ssize_t)sizeof(result));
        char byte;
        assert(read(release[0], &byte, 1) == 1);
        _exit(7);
    }
    close(report[1]); close(release[0]);
    assert(!b41_mipc_supervision_bind(&owner, child));
    int failure;
    assert(read(report[0], &failure, sizeof(failure)) == (ssize_t)sizeof(failure));
    assert(failure == (copy_error ? -copy_error : -EACCES) && !owner.reaped);
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT; ++i)
        assert(fcntl(retained[i], F_GETFD) >= 0);
    check_payload(retained[0], LONG_SIZE);
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
    for (unsigned i = 0; i < LONG_SIZE; ++i)
        long_payload[i] = (unsigned char)((i * 37u + 11u) % 251u);
    char root[] = "/tmp/b41-loader-root-XXXXXX";
    assert(mkdtemp(root));
    int fd[B41_MIPC_PROVIDER_COUNT + 2];
    const int seals = F_SEAL_SEAL | F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK;
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT + 2; ++i) {
        fd[i] = memfd_create("filesystem-fixture-not-ELF", MFD_ALLOW_SEALING | MFD_CLOEXEC);
        assert(fd[i] >= 0);
        if (!i) assert(write(fd[i], long_payload, LONG_SIZE) == (ssize_t)LONG_SIZE);
        else assert(write(fd[i], &i, sizeof(i)) == (ssize_t)sizeof(i));
        assert(!fchmod(fd[i], i == 0 || i == B41_MIPC_PROVIDER_COUNT ? 0555 : 0444));
        assert(!fcntl(fd[i], F_ADD_SEALS, seals));
    }
    assert(b41_mipc_loader_root(root, fd, 0) == -EINVAL);
    int oversized[B41_MIPC_PROVIDER_COUNT];
    for (unsigned i = 0; i < B41_MIPC_PROVIDER_COUNT; ++i) oversized[i] = fd[i];
    for (unsigned i = 0; i < 2; ++i) {
        oversized[i] = memfd_create("oversized-fixture-not-ELF", MFD_ALLOW_SEALING | MFD_CLOEXEC);
        assert(oversized[i] >= 0 && !ftruncate(oversized[i], 64 * 1024 * 1024));
        assert(!fchmod(oversized[i], i ? 0444 : 0555));
        assert(!fcntl(oversized[i], F_ADD_SEALS, seals));
    }
    assert(b41_mipc_loader_root(root, oversized, B41_MIPC_PROVIDER_COUNT) == -EFBIG);
    for (unsigned i = 0; i < 2; ++i) assert(!close(oversized[i]));
    failed_root(fd, MS_NOSUID | MS_NODEV, 0);
    failed_root(fd, MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV, 0);
    failed_root(fd, 0, EIO);
    failed_root(fd, 0, EFBIG);
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
            assert(from.st_size == mounted.st_size);
            assert((from.st_mode & 0777) == (mounted.st_mode & 0777));
            assert(from.st_ino != mounted.st_ino || from.st_dev != mounted.st_dev);
            if (!i) {
                assert(mounted.st_size == LONG_SIZE);
                check_payload(opened, LONG_SIZE);
                check_payload(fd[i], LONG_SIZE);
            } else {
                unsigned value;
                assert(read(opened, &value, sizeof(value)) == (ssize_t)sizeof(value) && value == i);
            }
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
