/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_gpsdl_identity.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/vfs.h>
#include <unistd.h>
#define B41_SYSFS_MAGIC 0x62656572
static int inspect(int fd, unsigned link, dev_t *device)
{
    struct stat actual;
    if (fstat(fd, &actual)) return -errno;
    if (!S_ISCHR(actual.st_mode)) return -ENODEV;
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0) return -errno;
    if ((flags & O_ACCMODE) != O_RDWR) return -EACCES;
    char path[64];
    int n = snprintf(path, sizeof(path), "/sys/class/gpsdl%u/gpsdl%u/dev", link, link);
    if (n < 0 || (size_t)n >= sizeof(path)) return -EOVERFLOW;
    /* This metadata open never invokes gps_each_device_open or release. */
    int metadata = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (metadata < 0) return -errno;
    struct statfs fs;
    int error = fstatfs(metadata, &fs) ? -errno : fs.f_type != B41_SYSFS_MAGIC ? -EXDEV : 0;
    char text[64]; ssize_t length = -1;
    if (!error) {
        length = read(metadata, text, sizeof(text) - 1);
        if (length < 0) error = -errno;
        else if (!length || length == (ssize_t)sizeof(text) - 1) error = -EBADMSG;
    }
    if (close(metadata) && !error) error = -errno; /* No retry of close. */
    if (error) return error;
    text[length] = 0;
    char *end;
    if (text[0] < '0' || text[0] > '9') return -EBADMSG;
    errno = 0; unsigned long major_value = strtoul(text, &end, 10);
    if (errno || major_value > UINT_MAX || *end != ':') return -EBADMSG;
    const char *minor_text = end + 1;
    if (*minor_text < '0' || *minor_text > '9') return -EBADMSG;
    errno = 0; unsigned long minor_value = strtoul(minor_text, &end, 10);
    if (errno || minor_value > UINT_MAX || *end != '\n' || end[1] ||
        end - text + 1 != length) return -EBADMSG;
    unsigned maj = (unsigned)major_value, min = (unsigned)minor_value;
    dev_t rdev = makedev(maj, min);
    if (major(rdev) != maj || minor(rdev) != min || rdev != actual.st_rdev) return -ESTALE;
    *device = rdev;
    return 0;
}
int b41_gpsdl_identity_snapshot(int primary, int secondary, struct b41_gpsdl_identity *out)
{
    if (!out || primary < 0 || secondary < -1 || primary == secondary) return -EINVAL;
    struct b41_gpsdl_identity result = {primary, secondary, 0, 0};
    int error = inspect(primary, 0, &result.primary_device);
    if (!error && secondary >= 0) error = inspect(secondary, 1, &result.secondary_device);
    if (error) return error;
    if (secondary >= 0 && result.primary_device == result.secondary_device) return -ESTALE;
    *out = result;
    return 0;
}
