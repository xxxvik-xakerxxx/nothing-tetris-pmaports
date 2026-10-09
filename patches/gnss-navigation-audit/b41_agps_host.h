/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_AGPS_HOST_H
#define B41_AGPS_HOST_H
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include "b41_startup_adapter.h"

#define B41_AGPS_PACKET_MAX 65536u
enum b41_agps_owner_state { B41_AGPS_EMPTY, B41_AGPS_OWNED, B41_AGPS_FAILED, B41_AGPS_CLOSED };
struct b41_agps_owner {
    unsigned initialized;
    pthread_mutex_t lock;
    enum b41_agps_owner_state state;
    int fd, first_error;
    dev_t device;
    ino_t inode;
    uint8_t packet[B41_AGPS_PACKET_MAX];
};

/* Pure producers: mnld39490 -> type150 optional C string, 39540 -> type152.
 * Input string excludes its terminator; embedded NUL is rejected, not truncated.
 * NULL+length0 means absent, nonNULL+length0 means present empty string.
 * Error leaves output/length untouched. Input/output must not overlap.
 */
int b41_agps_data_packet(const void *string, size_t length, void *output,
                         size_t capacity, size_t *written);
int b41_agps_selector1_packet(void *output, size_t capacity, size_t *written);
/* Initialize fresh ZEROED storage once before worker start. Mutex lives until
 * process exit. Reinitialization is refused, including after stop.
 */
int b41_agps_owner_init(struct b41_agps_owner *owner);
/* Move an exclusively owned, already-connected Unix datagram fd. Exact peer
 * bytes must come from the runtime's audited endpoint, not a guessed pathname.
 * No dup/open/connect/bind here; success sets *fd=-1. Failure retains ownership.
 * Neither this fd nor this owner may be placed in libMNL's gpsdl fd fields.
 */
int b41_agps_owner_take(struct b41_agps_owner *owner, int *fd,
    const struct sockaddr_un *peer, socklen_t peer_length);
/* Worker only, not a library callback. One datagram; no partial/retry/blocking.
 * Zero means accepted by the socket, NOT frame measurement/navigation success.
 */
int b41_agps_owner_send_data(struct b41_agps_owner *owner, const void *string, size_t length);
int b41_agps_owner_send_selector1(struct b41_agps_owner *owner);
int b41_agps_owner_send_event(struct b41_agps_owner *owner, const struct b41_host_event *event);
/* Close ONLY this IPC fd after worker use. This is not libMNL engine stop and
 * does not close receiver fds or unregister retained callbacks. Never retry close.
 */
int b41_agps_owner_stop(struct b41_agps_owner *owner);
#endif
