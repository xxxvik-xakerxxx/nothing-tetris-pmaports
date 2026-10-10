/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_mipc_loader_root.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>

static const char *const targets[B41_MIPC_PROVIDER_COUNT + 2] = {
    "apex/com.android.runtime/bin/linker64",
    "apex/com.android.runtime/lib64/bionic/libc.so",
    "apex/com.android.runtime/lib64/bionic/libm.so",
    "apex/com.android.runtime/lib64/bionic/libdl.so",
    "system/lib64/libc++.so", "system/lib64/liblog.so",
    "vendor/lib64/libmipc.so", "vendor/lib64/libmtkrillog.so",
    "vendor/lib64/libtrm.so", "vendor/lib64/libmtkproperty.so",
    "probe", "vendor/lib64/libmnl.so",
};
static const char *const directories[] = {
    "apex", "apex/com.android.runtime", "apex/com.android.runtime/bin",
    "apex/com.android.runtime/lib64", "apex/com.android.runtime/lib64/bionic",
    "system", "system/lib64", "vendor", "vendor/lib64", "proc",
};

static int build_root(const char *root, const int *providers, unsigned count)
{
    struct stat info, identities[B41_MIPC_PROVIDER_COUNT + 2];
    char canonical[PATH_MAX], target[PATH_MAX], source[64];
    const int seals = F_SEAL_SEAL | F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK;
    if (!root || root[0] != '/' || !providers ||
        (count != B41_MIPC_PROVIDER_COUNT && count != B41_MIPC_PROVIDER_COUNT + 2))
        return -EINVAL;
    if (!realpath(root, canonical)) return -errno;
    if (strcmp(root, canonical)) return -EINVAL;
    if (lstat(root, &info)) return -errno;
    if (!S_ISDIR(info.st_mode) || info.st_uid || (info.st_mode & 022)) return -EPERM;
    DIR *directory = opendir(root);
    if (!directory) return -errno;
    int error = 0;
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(directory)))
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) { error = -ENOTEMPTY; break; }
    if (!error && errno) error = -errno;
    if (closedir(directory) && !error) error = -errno;
    if (error) return error;
    for (unsigned i = 0; i < count; ++i) {
        if (fstat(providers[i], &identities[i])) return -errno;
        if (!S_ISREG(identities[i].st_mode) || identities[i].st_size <= 0 ||
            identities[i].st_size > 64 * 1024 * 1024) return -EINVAL;
        int actual = fcntl(providers[i], F_GET_SEALS);
        if (actual < 0) return -errno;
        if ((actual & seals) != seals) return -EPERM;
        if ((identities[i].st_mode & 0777) !=
            ((!i || i == B41_MIPC_PROVIDER_COUNT) ? 0555 : 0444)) return -EPERM;
        for (unsigned j = 0; j < i; ++j)
            if (identities[j].st_dev == identities[i].st_dev &&
                identities[j].st_ino == identities[i].st_ino) return -EEXIST;
    }
    if (unshare(CLONE_NEWNS) || mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL)) return -errno;
    /* New namespace-local tmpfs prevents external source-root writers from
     * replacing provider target paths after binding immutable source bytes. */
    if (mount("b41-mipc-resources", root, "tmpfs", MS_NOSUID | MS_NODEV,
              "size=1m,mode=0755")) return -errno;
    for (unsigned i = 0; i < sizeof(directories) / sizeof(directories[0]); ++i) {
        if (snprintf(target, sizeof(target), "%s/%s", root, directories[i]) >= (int)sizeof(target))
            return -ENAMETOOLONG;
        if (mkdir(target, 0555) || chmod(target, 0555)) return -errno;
    }
    for (unsigned i = 0; i < count; ++i) {
        if (snprintf(target, sizeof(target), "%s/%s", root, targets[i]) >= (int)sizeof(target))
            return -ENAMETOOLONG;
        int fd = open(target, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC | O_NOFOLLOW, 0444);
        if (fd < 0) return -errno;
        if (close(fd)) return -errno;
        if (snprintf(source, sizeof(source), "/proc/self/fd/%d", providers[i]) >= (int)sizeof(source))
            return -ENAMETOOLONG;
        if (mount(source, target, NULL, MS_BIND, NULL) ||
            mount(NULL, target, NULL, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL))
            return -errno;
    }
    if (mount(NULL, root, NULL, MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL)) return -errno;
    return 0;
}

int b41_mipc_loader_root(const char *root, const int *providers, unsigned count)
{
    if (count != B41_MIPC_PROVIDER_COUNT) return -EINVAL;
    return build_root(root, providers, count);
}

int b41_mipc_loader_root_probe(const char *root, const int *providers,
    unsigned count, int probe, int mnl)
{
    int descriptors[B41_MIPC_PROVIDER_COUNT + 2];
    if (!providers || count != B41_MIPC_PROVIDER_COUNT) return -EINVAL;
    memcpy(descriptors, providers, sizeof(int) * count);
    descriptors[count] = probe;
    descriptors[count + 1] = mnl;
    return build_root(root, descriptors, count + 2);
}
