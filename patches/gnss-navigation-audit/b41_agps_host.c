/* SPDX-License-Identifier: GPL-2.0-only */
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include "b41_agps_host.h"

static void word(uint8_t *out, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i)
        out[i] = (uint8_t)(value >> (8 * i));
}

int b41_agps_data_packet(const void *string, size_t length, void *output,
                         size_t capacity, size_t *written)
{
    size_t size;
    uint8_t *out = output;
    if (!output || !written || (!string && length))
        return -EINVAL;
    if (length > B41_AGPS_PACKET_MAX - 14u)
        return -EMSGSIZE;
    if (string && memchr(string, 0, length))
        return -EPROTO;
    size = string ? length + 14u : 9u;
    if (capacity < size)
        return -ENOSPC;
    if (string) {
        uintptr_t source = (uintptr_t)string, destination = (uintptr_t)output;
        if (source > UINTPTR_MAX - length || destination > UINTPTR_MAX - size ||
            (source < destination + size && destination < source + length))
            return -EINVAL;
    }
    word(out, 1);
    word(out + 4, 150);
    out[8] = string ? 1 : 0;
    if (string) {
        word(out + 9, (uint32_t)length + 1);
        memcpy(out + 13, string, length);
        out[13 + length] = 0;
    }
    *written = size;
    return 0;
}

int b41_agps_selector1_packet(void *output, size_t capacity, size_t *written)
{
    if (!output || !written)
        return -EINVAL;
    if (capacity < 8)
        return -ENOSPC;
    word(output, 1);
    word((uint8_t *)output + 4, 152);
    *written = 8;
    return 0;
}

int b41_agps_owner_init(struct b41_agps_owner *owner)
{
    int status;
    if (!owner)
        return -EINVAL;
    if (owner->initialized)
        return -EALREADY;
    /* Caller provides a fresh object; do not reinitialize a live mutex. */
    memset(owner, 0, sizeof(*owner));
    owner->fd = -1;
    status = pthread_mutex_init(&owner->lock, NULL);
    if (!status)
        owner->initialized = 1;
    return status ? -status : 0;
}

static int identity(struct b41_agps_owner *owner)
{
    struct stat current;
    if (fstat(owner->fd, &current))
        return -errno;
    if (!S_ISSOCK(current.st_mode) || current.st_dev != owner->device || current.st_ino != owner->inode)
        return -ESTALE;
    return 0;
}

int b41_agps_owner_take(struct b41_agps_owner *owner, int *fd,
    const struct sockaddr_un *peer, socklen_t peer_length)
{
    struct sockaddr_un actual = {0};
    socklen_t actual_length = sizeof(actual), type_length = sizeof(int);
    struct stat stat;
    int type, status;
    if (!owner || !owner->initialized || !fd || *fd < 0 || !peer || peer->sun_family != AF_UNIX ||
        peer_length < offsetof(struct sockaddr_un, sun_path) || peer_length > sizeof(*peer))
        return -EINVAL;
    status = pthread_mutex_lock(&owner->lock);
    if (status)
        return -status;
    if (owner->state != B41_AGPS_EMPTY) {
        status = -EALREADY;
        goto out;
    }
    if (getsockopt(*fd, SOL_SOCKET, SO_TYPE, &type, &type_length) ||
        getpeername(*fd, (struct sockaddr *)&actual, &actual_length) || fstat(*fd, &stat)) {
        status = -errno;
        goto out;
    }
    if (type_length != sizeof(type) || type != SOCK_DGRAM || !S_ISSOCK(stat.st_mode) ||
        actual.sun_family != AF_UNIX || actual_length != peer_length ||
        memcmp(&actual, peer, peer_length)) {
        status = -EPROTO;
        goto out;
    }
    owner->fd = *fd;
    owner->device = stat.st_dev;
    owner->inode = stat.st_ino;
    owner->state = B41_AGPS_OWNED;
    *fd = -1;
    status = 0;
out:
    pthread_mutex_unlock(&owner->lock);
    return status;
}

static int send_packet(struct b41_agps_owner *owner, const void *string, size_t length, int selector1)
{
    size_t written;
    ssize_t sent;
    int status;
    if (!owner || !owner->initialized)
        return -EINVAL;
    status = pthread_mutex_lock(&owner->lock);
    if (status)
        return -status;
    if (owner->first_error) {
        status = owner->first_error;
        goto out;
    }
    if (owner->state != B41_AGPS_OWNED) {
        status = -ESHUTDOWN;
        goto out;
    }
    status = identity(owner);
    if (status)
        goto failed;
    status = selector1 ? b41_agps_selector1_packet(owner->packet, sizeof(owner->packet), &written) :
        b41_agps_data_packet(string, length, owner->packet, sizeof(owner->packet), &written);
    if (status)
        goto failed;
    sent = send(owner->fd, owner->packet, written, MSG_DONTWAIT | MSG_NOSIGNAL);
    if (sent < 0) {
        status = -errno;
        goto failed;
    }
    if ((size_t)sent != written) {
        status = -EIO;
        goto failed;
    }
    status = 0;
    goto out;
failed:
    owner->first_error = status;
    owner->state = B41_AGPS_FAILED;
out:
    pthread_mutex_unlock(&owner->lock);
    return status;
}

int b41_agps_owner_send_data(struct b41_agps_owner *owner, const void *string, size_t length)
{
    return send_packet(owner, string, length, 0);
}

int b41_agps_owner_send_selector1(struct b41_agps_owner *owner)
{
    return send_packet(owner, NULL, 0, 1);
}

int b41_agps_owner_send_event(struct b41_agps_owner *owner, const struct b41_host_event *event)
{
    if (!event || event->length > sizeof(event->bytes))
        return -EINVAL;
    switch (event->kind) {
    case B41_HOST_FRAME_SLEEP:
    case B41_HOST_FRAME_NETWORK:
    case B41_HOST_FRAME_MEASUREMENT:
        return b41_agps_owner_send_data(owner, event->bytes, event->length);
    default:
        return -EOPNOTSUPP; /* Raw NMEA/app output is NOT an AGPS request. */
    }
}

int b41_agps_owner_stop(struct b41_agps_owner *owner)
{
    int status, close_status;
    if (!owner || !owner->initialized)
        return -EINVAL;
    status = pthread_mutex_lock(&owner->lock);
    if (status)
        return -status;
    status = owner->first_error;
    if (owner->fd >= 0) {
        close_status = identity(owner);
        if (!close_status && close(owner->fd))
            close_status = -errno;
        /* A foreign/reused fd must not be closed. close(EINTR) is not retried. */
        if (!status)
            status = close_status;
        owner->fd = -1;
    }
    owner->state = B41_AGPS_CLOSED;
    if (status && !owner->first_error)
        owner->first_error = status;
    pthread_mutex_unlock(&owner->lock);
    return status;
}
