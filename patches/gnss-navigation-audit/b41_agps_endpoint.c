/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "b41_agps_endpoint.h"
#include <errno.h>
#include <string.h>
#include <unistd.h>

int b41_agps_endpoint_open(struct b41_agps_endpoint *endpoint)
{
    static const char path[] = "/data/agps_supl/mnl_to_agps";
    static const char name[] = "mtk_mnl2agps";
    struct sockaddr_un peer = {0};
    struct stat before, after;
    socklen_t length;
    int fd = -1, status, saved;
    _Static_assert(sizeof(peer) == 110 && offsetof(struct sockaddr_un, sun_path) == 2,
                   "pinned Linux/Bionic Unix socket ABI");
    _Static_assert(sizeof(name) + 2 == 15, "pinned abstract address excludes final NUL");
    if (!endpoint) return -EINVAL;
    if (endpoint->entered)
        return endpoint->first_error ? endpoint->first_error : -EALREADY;
    endpoint->entered = 1;
    status = b41_agps_owner_init(&endpoint->ipc);
    if (status) goto fail;
    peer.sun_family = AF_UNIX;
    if (lstat(path, &before)) {
        status = -errno;
        if (status != -ENOENT) goto cleanup;
        endpoint->route = B41_AGPS_ENDPOINT_ABSTRACT;
    } else if (S_ISDIR(before.st_mode)) {
        endpoint->route = B41_AGPS_ENDPOINT_ABSTRACT;
    } else if (S_ISSOCK(before.st_mode)) {
        endpoint->route = B41_AGPS_ENDPOINT_FILESYSTEM;
    } else {
        status = -EPROTO;
        goto cleanup;
    }
    if (endpoint->route == B41_AGPS_ENDPOINT_FILESYSTEM) {
        memcpy(peer.sun_path, path, sizeof(path));
        length = offsetof(struct sockaddr_un, sun_path) + sizeof(path);
    } else {
        /* Abstract name ends at byte14 WITHOUT a terminating zero. Adding a
         * terminator or padding to110 bytes addresses a different Linux socket.
         */
        memcpy(peer.sun_path + 1, name, sizeof(name) - 1);
        length = offsetof(struct sockaddr_un, sun_path) + sizeof(name);
    }
    fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) { status = -errno; goto cleanup; }
    if (connect(fd, (const struct sockaddr *)&peer, length)) {
        status = -errno;
        goto cleanup;
    }
    if (endpoint->route == B41_AGPS_ENDPOINT_FILESYSTEM) {
        if (lstat(path, &after)) { status = -errno; goto cleanup; }
        if (!S_ISSOCK(after.st_mode) || before.st_dev != after.st_dev ||
            before.st_ino != after.st_ino || before.st_mode != after.st_mode) {
            status = -ESTALE;
            goto cleanup;
        }
    }
    status = b41_agps_owner_take(&endpoint->ipc, &fd, &peer, length);
    if (!status) return 0;
cleanup:
    /* Ownership transfers only after peer/type/inode checks. No close retry,
     * including EINTR; cleanup must never replace the first causal error.
     */
    if (fd >= 0) (void)close(fd);
    saved = status;
    (void)b41_agps_owner_stop(&endpoint->ipc);
    status = saved;
fail:
    endpoint->first_error = status;
    return status;
}
