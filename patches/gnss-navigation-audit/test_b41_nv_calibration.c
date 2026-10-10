/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "b41_nv_calibration.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static int fault;
static int writer, close_calls;
ssize_t __real_pread(int fd, void *bytes, size_t length, off_t offset);
int __real_close(int fd);
int __wrap_close(int fd)
{
    int status = __real_close(fd);
    if (fault == 5) { ++close_calls; errno = EINTR; return -1; }
    return status;
}
ssize_t __wrap_pread(int fd, void *bytes, size_t length, off_t offset)
{
    assert(length == 16 && offset == 160);
    if (fault == 1) return __real_pread(fd, bytes, 7, offset);
    if (fault == 2) { errno = EINTR; return -1; }
    ssize_t count = __real_pread(fd, bytes, length, offset);
    if (fault == 3) assert(ftruncate(writer, 176) == 0);
    return count;
}
int main(void)
{
    char path[] = "/tmp/b41-nv-fixture-XXXXXX";
    uint8_t synthetic[192];
    struct b41_nv_calibration record, unchanged;
    struct b41_first_config first, original;
    struct b41_first_inputs inputs = {0};
    struct b41_nv_producer producer = {0};
    for (unsigned i = 0; i < sizeof(synthetic); ++i) synthetic[i] = (uint8_t)(i ^ 0x5a);
    assert(mkdtemp(path));
    int root = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC); assert(root >= 0);
    memset(&record, 0xa5, sizeof(record)); unchanged = record;
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -ENOENT);
    assert(!memcmp(&record, &unchanged, sizeof(record)));
    int fd = openat(root, "ML4A_000", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
    assert(fd >= 0);
    writer = fd;
    assert(write(fd, synthetic, sizeof(synthetic)) == (ssize_t)sizeof(synthetic));
    assert(b41_nv_calibration_read(root, 0x6878, &record) == 0);
    assert(!memcmp(record.bytes, synthetic + 160, 16));
    assert(lseek(fd, 0, SEEK_CUR) == (off_t)sizeof(synthetic));
    record = unchanged;
    assert(b41_nv_calibration_read(root, 0x6893, &record) == -EOPNOTSUPP);
    assert(!memcmp(&record, &unchanged, sizeof(record)));
    fault = 1;
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -EMSGSIZE);
    assert(!memcmp(&record, &unchanged, sizeof(record)));
    fault = 2;
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -EINTR);
    assert(!memcmp(&record, &unchanged, sizeof(record)));
    fault = 3;
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -ESTALE);
    assert(!memcmp(&record, &unchanged, sizeof(record)));
    assert(ftruncate(fd, sizeof(synthetic)) == 0);
    fault = 5;
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -EINTR);
    assert(close_calls == 1 && !memcmp(&record, &unchanged, sizeof(record)));
    fault = 0;
    memset(&first, 0xa5, sizeof(first)); original = first;
    assert(b41_first_config_from_nv(root, 0x6878, &producer, &inputs, &first) == -EOPNOTSUPP);
    assert(!memcmp(&first, &original, sizeof(first)));
    inputs.present = B41_FIRST_PLATFORM_PROFILE;
    inputs.default_platform_profile = 1;
    producer.property_branch_de3bc = 1;
    assert(b41_first_config_from_nv(root, 0x6878, &producer, &inputs, &first) == -EOPNOTSUPP);
    assert(!memcmp(&first, &original, sizeof(first)));
    producer.property_branch_de3bc = 0;
    producer.platform_profile_de22c = 1;
    assert(b41_first_config_from_nv(root, 0x6878, &producer, &inputs, &first) == -EOPNOTSUPP);
    producer.platform_profile_de22c = 0;
    assert(b41_first_config_from_nv(root, 0x6878, &producer, &inputs, &first) == 1);
    assert(!memcmp(first.bytes + 0x3c, synthetic + 160, 16));
    for (unsigned i = 0x3c; i < 0x4c; ++i)
        assert(first.provenance[i] == B41_FIRST_CLOCK_CALIBRATION);
    assert(!(first.missing_inputs & B41_FIRST_CALIBRATION));
    assert(first.xml_policy_missing && first.unresolved_bytes);
    inputs.present |= B41_FIRST_CALIBRATION;
    assert(b41_first_config_from_nv(root, 0x6878, &producer, &inputs, &first) == -EALREADY);
    assert(ftruncate(fd, 175) == 0);
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -EMSGSIZE);
    assert(!memcmp(&record, &unchanged, sizeof(record)));
    assert(close(fd) == 0);
    assert(unlinkat(root, "ML4A_000", 0) == 0);
    assert(symlinkat("/dev/null", root, "ML4A_000") == 0);
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -ENOTSUP);
    assert(!memcmp(&record, &unchanged, sizeof(record)));
    assert(unlinkat(root, "ML4A_000", 0) == 0);
    assert(mkfifoat(root, "ML4A_000", 0600) == 0);
    assert(b41_nv_calibration_read(root, 0x6878, &record) == -ENOTSUP);
    assert(unlinkat(root, "ML4A_000", 0) == 0);
    assert(close(root) == 0 && rmdir(path) == 0);
    return 0;
}
