/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_control_notify.h"
#include <errno.h>
#include <stddef.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

int b41_control_notify(unsigned event, uint8_t runtime_policy)
{
    static const char endpoint[] = "mnld_gps_control_socket";
    static const unsigned char packet[4] = {3, 0, 0, 0};
    struct sockaddr_un peer;
    ssize_t sent;
    int fd, error = 0;

    if (event != 7)
        return -ENOTSUP;
    if (runtime_policy & 0x10)
        return 1;
    /* Pinned36bb0..36c08: abstract name at byte3, zero-filled 110-byte
     * address including trailing zeros. A short sockaddr is a DIFFERENT name.
     */
    _Static_assert(sizeof(peer) == 110 && offsetof(struct sockaddr_un, sun_path) == 2,
                   "requires pinned Linux/Bionic sockaddr_un ABI");
    memset(&peer, 0, sizeof(peer));
    peer.sun_family = AF_UNIX;
    memcpy(peer.sun_path + 1, endpoint, sizeof(endpoint) - 1);
    fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return -errno;
    sent = sendto(fd, packet, sizeof(packet), MSG_DONTWAIT | MSG_NOSIGNAL,
                  (const struct sockaddr *)&peer, sizeof(peer));
    if (sent < 0)
        error = -errno;
    else if (sent != (ssize_t)sizeof(packet))
        error = -EIO;
    /* This local fd never escapes. No close retry: EINTR may have consumed it.
     * Preserve the first send error; no OEM sleeps/retry/reset escalation.
     */
    if (close(fd) < 0 && !error)
        error = -errno;
    return error;
}
