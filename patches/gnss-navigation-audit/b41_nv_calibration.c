/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "b41_nv_calibration.h"
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <unistd.h>

static int same(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
        a->st_mode == b->st_mode && a->st_size == b->st_size &&
        a->st_mtim.tv_sec == b->st_mtim.tv_sec && a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec == b->st_ctim.tv_sec && a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}
int b41_nv_calibration_read(int root, uint32_t chip, struct b41_nv_calibration *out)
{
    struct b41_nv_calibration result;
    struct stat directory, entry, after;
    int fd, status = 0;
    ssize_t count;
    if (!out || root < 0) return -EINVAL;
    if (chip != 0x6878u) return -EOPNOTSUPP;
    if (fstat(root, &directory)) return -errno;
    if (!S_ISDIR(directory.st_mode)) return -ENOTDIR;
    if (fstatat(root, "ML4A_000", &entry, AT_SYMLINK_NOFOLLOW)) return -errno;
    if (!S_ISREG(entry.st_mode)) return -ENOTSUP;
    fd = openat(root, "ML4A_000", O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return -errno;
    if (fstat(fd, &result.identity)) status = -errno;
    else if (!S_ISREG(result.identity.st_mode)) status = -ENOTSUP;
    else if (!same(&entry, &result.identity)) status = -ESTALE;
    else if (result.identity.st_size < 176) status = -EMSGSIZE;
    if (!status) {
        count = pread(fd, result.bytes, sizeof(result.bytes), 160);
        if (count < 0) status = -errno;
        else if (count != (ssize_t)sizeof(result.bytes)) status = -EMSGSIZE;
    }
    if (!status && fstat(fd, &after)) status = -errno;
    if (!status && !same(&result.identity, &after)) status = -ESTALE;
    /* Exact opened inode must still be the directory's record, not a replaced
     * pathname. fstatat never follows a new symlink during this check.
     */
    if (!status && fstatat(root, "ML4A_000", &after, AT_SYMLINK_NOFOLLOW)) status = -errno;
    if (!status && !same(&result.identity, &after)) status = -ESTALE;
    if (close(fd) && !status) status = -errno; /* One close, no retry. */
    if (status) return status;
    *out = result;
    return 0;
}
int b41_first_config_from_nv(int root, uint32_t chip,
    const struct b41_nv_producer *producer,
    const struct b41_first_inputs *inputs, struct b41_first_config *out)
{
    struct b41_nv_calibration record;
    struct b41_first_inputs actual;
    int status;
    if (!producer || !inputs || !out) return -EINVAL;
    /* Explicit source branch applicability; no file read to satisfy a profile
     * that would actually take property/profile overrides instead.
     */
    if (producer->property_branch_de3bc || producer->platform_profile_de22c ||
        !(inputs->present & B41_FIRST_PLATFORM_PROFILE) ||
        inputs->default_platform_profile != 1) return -EOPNOTSUPP;
    if (inputs->present & B41_FIRST_CALIBRATION) return -EALREADY;
    status = b41_nv_calibration_read(root, chip, &record);
    if (status) return status;
    actual = *inputs;
    actual.present |= B41_FIRST_CALIBRATION;
    actual.clock_calibration = record.bytes;
    actual.clock_calibration_size = sizeof(record.bytes);
    return b41_first_config_build(&actual, out);
}
