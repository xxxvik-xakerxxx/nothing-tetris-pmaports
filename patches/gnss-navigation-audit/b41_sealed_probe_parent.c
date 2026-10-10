/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_mipc_sealed_isolate.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <sys/sysmacros.h>
#include <sys/wait.h>
#include <unistd.h>

static int number(const char *text, unsigned long long *value)
{
    if (!text || !*text || strspn(text, "0123456789") != strlen(text)) return -EINVAL;
    errno = 0;
    *value = strtoull(text, NULL, 10);
    return errno ? -errno : 0;
}

static int trusted_stdio(void)
{
    struct stat input, output, error;
    if (fstat(0, &input) || fstat(1, &output) || fstat(2, &error)) return -errno;
    int input_flags = fcntl(0, F_GETFL), output_flags = fcntl(1, F_GETFL), error_flags = fcntl(2, F_GETFL);
    if (input_flags < 0 || output_flags < 0 || error_flags < 0) return -errno;
    if (!S_ISCHR(input.st_mode) || major(input.st_rdev) != 1 || minor(input.st_rdev) != 3 ||
        (input_flags & O_ACCMODE) != O_RDONLY || !S_ISREG(output.st_mode) ||
        output.st_uid || (output.st_mode & 0777) != 0600 ||
        output.st_dev != error.st_dev || output.st_ino != error.st_ino ||
        !(output_flags & O_APPEND) || !(error_flags & O_APPEND) ||
        (output_flags & O_ACCMODE) != O_WRONLY || (error_flags & O_ACCMODE) != O_WRONLY) return -EPERM;
    return 0;
}

static int dedicated(void)
{
    DIR *tasks = opendir("/proc/self/task");
    if (!tasks) return -errno;
    unsigned count = 0;
    struct dirent *entry;
    while ((entry = readdir(tasks))) if (entry->d_name[0] != '.') ++count;
    if (closedir(tasks)) return -errno;
    if (count != 1) return -EBUSY;
    char path[128], byte;
    snprintf(path, sizeof(path), "/proc/self/task/%ld/children", (long)getpid());
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -errno;
    ssize_t size = read(fd, &byte, 1);
    int error = size < 0 ? -errno : size ? -EBUSY : 0;
    if (close(fd) && !error) error = -errno;
    return error;
}

static int admitted_descriptors(const int *stage, unsigned count)
{
    DIR *directory = opendir("/proc/self/fd");
    if (!directory) return -errno;
    int error = 0, inventory = dirfd(directory);
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(directory))) {
        if (entry->d_name[0] == '.') continue;
        unsigned long long fd;
        if (number(entry->d_name, &fd)) { error = -EPROTO; break; }
        if (fd < 3 || fd == (unsigned)inventory) continue;
        unsigned admitted = 0;
        for (unsigned i = 0; i < count; ++i) admitted |= fd == (unsigned)stage[i];
        if (!admitted) { error = -EPERM; break; }
    }
    if (!error && errno) error = -errno;
    if (closedir(directory) && !error) error = -errno;
    return error;
}

int main(int argc, char **argv)
{
    struct b41_mipc_supervision owner = {0};
    int stage[13], first = 0;
    unsigned long long deadline_ns, cleanup_ns, value;
    char root[] = "/run/b41-sealed-probe-XXXXXX";
    struct stat run;
    /* This executable is a trusted root admission endpoint, not an ELF oracle.
     * Python admits independently pinned copies before exec transfers ownership. */
    if (argc < 2) return 2;
    int xml_snapshot = !strcmp(argv[1], "xml-load") || !strcmp(argv[1], "xml-control");
    const char *mode = xml_snapshot ? argv[1] + 4 : argv[1];
    unsigned count = xml_snapshot ? 13 : 12;
    if (argc != (int)count + 4 || geteuid() || (strcmp(mode, "load") && strcmp(mode, "control")) ||
        number(argv[2], &deadline_ns) || number(argv[3], &cleanup_ns) ||
        deadline_ns > LLONG_MAX || cleanup_ns > LLONG_MAX || cleanup_ns < deadline_ns ||
        cleanup_ns - deadline_ns > 5000000000ULL || trusted_stdio() || dedicated()) return 2;
    for (unsigned i = 0; i < count; ++i) {
        if (number(argv[i + 4], &value) || value < 3 || value > INT_MAX) return 2;
        stage[i] = (int)value;
        if (fcntl(stage[i], F_SETFD, FD_CLOEXEC)) return 2;
    }
    if (admitted_descriptors(stage, count)) return 2;
    const struct rlimit log_bound = { 1024 * 1024, 64 * 1024 * 1024 };
    if (setrlimit(RLIMIT_FSIZE, &log_bound)) return 2;
    /* No handler/reaper can consume child status or release the sole lease. */
    sigset_t mask;
    if (sigfillset(&mask) || sigprocmask(SIG_SETMASK, &mask, NULL)) return 2;
    struct sigaction action = { .sa_handler = SIG_DFL };
    if (sigemptyset(&action.sa_mask) || sigaction(SIGCHLD, &action, NULL)) return 2;
    struct timespec deadline = { (time_t)(deadline_ns / 1000000000ULL),
        (long)(deadline_ns % 1000000000ULL) };
    struct timespec cleanup = { (time_t)(cleanup_ns / 1000000000ULL),
        (long)(cleanup_ns % 1000000000ULL) };
    first = b41_mipc_supervision_prepare(&owner, stage, count, &deadline, &cleanup);
    if (first) return 2;
    if (lstat("/run", &run) || !S_ISDIR(run.st_mode) || run.st_uid || (run.st_mode & 022) ||
        !mkdtemp(root)) {
        b41_mipc_supervision_abort_unstarted(&owner);
        return 2;
    }
    first = xml_snapshot ? b41_mipc_sealed_xml_probe_spawn(&owner, root, mode) :
        b41_mipc_sealed_probe_spawn(&owner, root, mode);
    if (!owner.bind_attempted) {
        int error = b41_mipc_supervision_abort_unstarted(&owner);
        if (!first) first = error;
    } else {
        unsigned reported = 0;
        do {
            int error = b41_mipc_supervision_finish(&owner);
            if (!first && error) first = owner.wait_error ? owner.wait_error : error;
            if (!owner.reaped) {
                if (!reported) {
                    reported = 1;
                    fprintf(stderr, "QUARANTINE: unreaped child=%ld first=%d; retaining all FDs\n",
                        (long)owner.child, first);
                    fflush(stderr);
                }
                /* Operation budget is exhausted, not extended. Wait only for
                 * terminal acknowledgement; no retry, unload or lease release. */
                struct timespec pause = {0, 100000000};
                nanosleep(&pause, NULL);
            }
        } while (!owner.reaped);
        fprintf(stderr, "TERMINAL: status=%d first=%d\n", owner.wait_status, first);
    }
    if (rmdir(root) && !first) first = -errno;
    return first ? 1 : 0;
}
