/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include <errno.h>
#include <grp.h>
#include <linux/audit.h>
#include <linux/capability.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sched.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#if defined(__aarch64__)
#define PROBE_ARCH AUDIT_ARCH_AARCH64
#elif defined(__x86_64__)
#define PROBE_ARCH AUDIT_ARCH_X86_64
#else
#error Unsupported probe architecture
#endif

#define DENY(nr) BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, nr, 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM)

static int filter(void)
{
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, PROBE_ARCH, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, 0x40000000U, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        DENY(__NR_socket), DENY(__NR_socketpair), DENY(__NR_connect),
        DENY(__NR_bind), DENY(__NR_listen), DENY(__NR_accept), DENY(__NR_accept4),
        DENY(__NR_ioctl), DENY(__NR_mount), DENY(__NR_umount2),
        DENY(__NR_unshare), DENY(__NR_setns), DENY(__NR_ptrace),
        DENY(__NR_process_vm_readv), DENY(__NR_process_vm_writev),
        DENY(__NR_bpf), DENY(__NR_perf_event_open), DENY(__NR_open_by_handle_at),
        DENY(__NR_io_uring_setup), DENY(__NR_io_uring_enter), DENY(__NR_io_uring_register),
        DENY(__NR_mknodat), DENY(__NR_chroot), DENY(__NR_pivot_root),
        DENY(__NR_clone), DENY(__NR_clone3),
#ifdef __NR_fork
        DENY(__NR_fork), DENY(__NR_vfork),
#endif
        DENY(__NR_setuid), DENY(__NR_setgid), DENY(__NR_setresuid),
        DENY(__NR_setresgid), DENY(__NR_setgroups), DENY(__NR_capset),
        DENY(__NR_keyctl), DENY(__NR_add_key), DENY(__NR_request_key),
#ifdef __NR_fsopen
        DENY(__NR_fsopen), DENY(__NR_fsmount), DENY(__NR_fspick),
        DENY(__NR_open_tree), DENY(__NR_move_mount),
#endif
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = sizeof(instructions) / sizeof(instructions[0]),
        .filter = instructions,
    };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0))
        return -1;
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}

static int control(void)
{
    int failures = 0;
#define BLOCKED(call) do { errno = 0; if ((call) != -1 || errno != EPERM) failures++; } while (0)
    BLOCKED(socket(AF_INET, SOCK_STREAM, 0));
    BLOCKED(socket(AF_UNIX, SOCK_STREAM, 0));
    BLOCKED(ioctl(-1, 0, 0));
    BLOCKED(mount("none", "/", "tmpfs", 0, NULL));
    BLOCKED(ptrace(PTRACE_TRACEME, 0, NULL, NULL));
    BLOCKED(unshare(CLONE_NEWUSER));
    BLOCKED(syscall(__NR_clone3, NULL, 0));
    BLOCKED(setuid(0));
#undef BLOCKED
    printf("CONTROL: eight network/device/namespace/privilege denials, failures=%d\n", failures);
    if (fflush(stdout))
        return 1;
    return failures ? 1 : 0;
}

static void die(const char *operation)
{
    perror(operation);
    _exit(125);
}

static void limit(int resource, rlim_t maximum)
{
    const struct rlimit value = { maximum, maximum };
    if (setrlimit(resource, &value))
        die("setrlimit");
}

static void child(const char *root, const char *mode)
{
    char proc[4096];
    char *const environment[] = {
        "PATH=/", "LC_ALL=C",
        "LD_LIBRARY_PATH=/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64",
        NULL,
    };
    char *const probe[] = {
        "/apex/com.android.runtime/bin/linker64",
        "/probe", "/vendor/lib64/libmnl.so", NULL,
    };
    if (snprintf(proc, sizeof(proc), "%s/proc", root) >= (int)sizeof(proc)) {
        errno = ENAMETOOLONG;
        die("proc path");
    }
    if (mount(root, root, NULL, MS_BIND, NULL) ||
        mount(NULL, root, NULL, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL))
        die("read-only root");
    if (mount("proc", proc, "proc", MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL))
        die("private proc");
    if (chroot(root) || chdir("/"))
        die("chroot");
    for (int capability = 0; capability <= CAP_LAST_CAP; capability++)
        if (prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) && errno != EINVAL)
            die("drop capability bound");
    if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) ||
        setgroups(0, NULL) || setresgid(65534, 65534, 65534) ||
        setresuid(65534, 65534, 65534) || prctl(PR_SET_DUMPABLE, 0, 0, 0, 0))
        die("drop privileges");
    limit(RLIMIT_CORE, 0);
    limit(RLIMIT_CPU, 5);
    limit(RLIMIT_AS, 512UL << 20);
    limit(RLIMIT_STACK, 8UL << 20);
    limit(RLIMIT_NOFILE, 16);
    if (syscall(__NR_close_range, 3U, ~0U, 0U))
        die("close inherited descriptors");
    if (filter())
        die("seccomp");
    if (!strcmp(mode, "control"))
        _exit(control());
    execve(probe[0], probe, environment);
    die("exec Android load-only probe");
}

static volatile sig_atomic_t expired;
static void timeout_handler(int signal_number)
{
    (void)signal_number;
    expired = 1;
}

int main(int argc, char **argv)
{
    struct stat root;
    int status;
    pid_t pid, result;
    struct sigaction action = { .sa_handler = timeout_handler };
    if (argc == 2 && !strcmp(argv[1], "--self-test-filter")) {
        if (filter())
            die("seccomp self-test");
        return control();
    }
    if (argc != 3 || (strcmp(argv[2], "control") && strcmp(argv[2], "load")) ||
        geteuid() || argv[1][0] != '/' || stat(argv[1], &root) ||
        !S_ISDIR(root.st_mode) || root.st_uid || (root.st_mode & 022)) {
        fputs("Require root-owned non-writable absolute probe root and control/load mode\n", stderr);
        return 2;
    }
    if (unshare(CLONE_NEWNS | CLONE_NEWNET | CLONE_NEWPID) ||
        mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL))
        die("private namespaces");
    pid = fork();
    if (pid < 0)
        die("fork");
    if (!pid)
        child(argv[1], argv[2]);
    if (sigemptyset(&action.sa_mask) || sigaction(SIGALRM, &action, NULL)) {
        kill(pid, SIGKILL);
        die("watchdog");
    }
    alarm(20);
    do {
        result = waitpid(pid, &status, 0);
        if (result < 0 && errno == EINTR && expired)
            kill(pid, SIGKILL);
    } while (result < 0 && errno == EINTR);
    alarm(0);
    if (result < 0)
        die("waitpid");
    if (expired || !WIFEXITED(status))
        return 124;
    return WEXITSTATUS(status);
}
