/* SPDX-License-Identifier: GPL-2.0-only */
/* Reuse exact frozen limits/denial filter/control; no copied weakened policy.
 * Its legacy main/child are not entry points for this adapter. */
#define main b41_unused_original_isolate_main
#define child b41_unused_original_isolate_child
#include "mnl-isolate.c"
#undef child
#undef main
#include "b41_mipc_sealed_isolate.h"
#include "b41_mipc_loader_root.h"

static int xml_control(void)
{
    struct stat info;
    char bytes[5087];
    size_t used = 0;
    int fd = open("/vendor/etc/MNL_Config.xml", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0 || fstat(fd, &info) || !S_ISREG(info.st_mode) ||
        info.st_size != (off_t)sizeof(bytes) || (info.st_mode & 0777) != 0444)
        die("sealed XML control metadata");
    while (used < sizeof(bytes)) {
        ssize_t n = read(fd, bytes + used, sizeof(bytes) - used);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) die("sealed XML control read");
        used += (size_t)n;
    }
    if (close(fd)) die("sealed XML control close");
    if (!lstat("/data", &info) || errno != ENOENT) die("unexpected XML data root");
    fd = open("/vendor/etc/MNL_Config.xml", O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd >= 0 || (errno != EROFS && errno != EACCES)) die("XML write not denied");
    puts("XML_ROOT_OK: fixed config readable; data absent; writes denied");
    fflush(stdout);
    return 0;
}

static void sealed_child(struct b41_mipc_supervision *owner, const char *root,
    const char *mode, int xml_snapshot)
{
    sigset_t signals;
    /* Only the lease-owning parent blocks termination; restore child limits. */
    if (sigemptyset(&signals) || sigprocmask(SIG_SETMASK, &signals, NULL))
        die("restore child signal mask");
    /* The parent log's soft limit must not truncate authenticated providers. */
    limit(RLIMIT_FSIZE, 64UL << 20);
    char proc[4096];
    char *const environment[] = { "PATH=/", "LC_ALL=C",
        "LD_LIBRARY_PATH=/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64", NULL };
    char *const probe[] = { "/apex/com.android.runtime/bin/linker64", "/probe",
        "/vendor/lib64/libmnl.so", NULL };
    int rc = xml_snapshot ?
        b41_mipc_loader_root_probe_xml(root, owner->stage, B41_MIPC_PROVIDER_COUNT,
            owner->stage[B41_MIPC_PROVIDER_COUNT], owner->stage[B41_MIPC_PROVIDER_COUNT + 1],
            owner->stage[B41_MIPC_PROVIDER_COUNT + 2]) :
        b41_mipc_loader_root_probe(root, owner->stage, B41_MIPC_PROVIDER_COUNT,
            owner->stage[B41_MIPC_PROVIDER_COUNT], owner->stage[B41_MIPC_PROVIDER_COUNT + 1]);
    if (rc) { errno = -rc; die("sealed provider root"); }
    limit(RLIMIT_FSIZE, 1UL << 20);
    if (snprintf(proc, sizeof(proc), "%s/proc", root) >= (int)sizeof(proc)) {
        errno = ENAMETOOLONG; die("private proc path");
    }
    /* Consume the private read-only snapshot without rebinding its root. */
    if (mount("proc", proc, "proc", MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) ||
        chroot(root) || chdir("/")) die("private proc/chroot");
    for (int capability = 0; capability <= CAP_LAST_CAP; ++capability)
        if (prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) && errno != EINVAL)
            die("drop capability bound");
    if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) || setgroups(0, NULL) ||
        setresgid(65534, 65534, 65534) || setresuid(65534, 65534, 65534) ||
        prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)) die("drop privileges");
    limit(RLIMIT_CORE, 0); limit(RLIMIT_CPU, 5); limit(RLIMIT_AS, 16ULL << 30);
    limit(RLIMIT_STACK, 8UL << 20); limit(RLIMIT_NOFILE, 16);
    if (syscall(__NR_close_range, 3U, ~0U, 0U)) die("close child inherited descriptors");
    if (filter()) die("existing seccomp");
    if (!strcmp(mode, "control")) {
        int error = control();
        if (!error && xml_snapshot) error = xml_control();
        _exit(error);
    }
    execve(probe[0], probe, environment);
    die("exec sealed load-only probe");
}

static int sealed_spawn(struct b41_mipc_supervision *owner,
    const char *root, const char *mode, int xml_snapshot)
{
    struct timespec now;
    if (!owner || !owner->entered || owner->bind_attempted || owner->terminal ||
        owner->count != B41_MIPC_PROVIDER_COUNT + 2 + (unsigned)xml_snapshot ||
        !root || root[0] != '/' ||
        !mode || (strcmp(mode, "control") && strcmp(mode, "load"))) return -EINVAL;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
    if (now.tv_sec > owner->deadline.tv_sec ||
        (now.tv_sec == owner->deadline.tv_sec && now.tv_nsec >= owner->deadline.tv_nsec))
        return -ETIMEDOUT;
    if (geteuid() || memory_bound()) return -EPERM;
    /* Runs in a dedicated launcher, never the shared pmOS controller process. */
    if (unshare(CLONE_NEWNET | CLONE_NEWPID)) return -errno;
    pid_t pid = fork();
    if (pid < 0) return -errno;
    if (!pid) sealed_child(owner, root, mode, xml_snapshot);
    return b41_mipc_supervision_bind(owner, pid);
}

int b41_mipc_sealed_probe_spawn(struct b41_mipc_supervision *owner,
    const char *root, const char *mode)
{
    return sealed_spawn(owner, root, mode, 0);
}

int b41_mipc_sealed_xml_probe_spawn(struct b41_mipc_supervision *owner,
    const char *root, const char *mode)
{
    return sealed_spawn(owner, root, mode, 1);
}
