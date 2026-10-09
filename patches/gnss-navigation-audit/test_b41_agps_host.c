#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "b41_agps_host.h"

static int short_send;
static int block_send, send_entered, release_send;
static pthread_mutex_t test_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t test_condition = PTHREAD_COND_INITIALIZER;
ssize_t __real_send(int fd, const void *buffer, size_t length, int flags);
ssize_t __wrap_send(int fd, const void *buffer, size_t length, int flags)
{
    if (short_send)
        return (ssize_t)length - 1;
    if (block_send) {
        assert(pthread_mutex_lock(&test_lock) == 0);
        send_entered = 1;
        assert(pthread_cond_broadcast(&test_condition) == 0);
        while (!release_send)
            assert(pthread_cond_wait(&test_condition, &test_lock) == 0);
        assert(pthread_mutex_unlock(&test_lock) == 0);
    }
    return __real_send(fd, buffer, length, flags);
}

struct worker { struct b41_agps_owner *owner; int result; };
static void *sender(void *argument)
{
    struct worker *w = argument;
    w->result = b41_agps_owner_send_selector1(w->owner);
    return NULL;
}
static void *stopper(void *argument)
{
    struct worker *w = argument;
    w->result = b41_agps_owner_stop(w->owner);
    return NULL;
}

static void take(struct b41_agps_owner *owner, int *fd)
{
    struct sockaddr_un peer = {0};
    socklen_t length = sizeof(peer);
    assert(getpeername(*fd, (struct sockaddr *)&peer, &length) == 0);
    assert(b41_agps_owner_take(owner, fd, &peer, length) == 0);
    assert(*fd == -1);
}

int main(void)
{
    uint8_t packet[64], before[64], received[64];
    const uint8_t data[] = {1,0,0,0,150,0,0,0,1,4,0,0,0,'a','b','c',0};
    const uint8_t absent[] = {1,0,0,0,150,0,0,0,0};
    const uint8_t control[] = {1,0,0,0,152,0,0,0};
    size_t length = 99;
    struct b41_agps_owner *owner = calloc(1, sizeof(*owner));
    int sockets[2], fd, old, replacement;
    struct sockaddr_un bad = {.sun_family = AF_INET};
    struct b41_host_event event = {.kind = B41_HOST_OUTPUT};
    assert(owner);
    assert(b41_agps_data_packet("abc", 3, packet, sizeof(packet), &length) == 0);
    assert(length == sizeof(data) && !memcmp(packet, data, length));
    assert(b41_agps_data_packet(NULL, 0, packet, sizeof(packet), &length) == 0);
    assert(length == sizeof(absent) && !memcmp(packet, absent, length));
    assert(b41_agps_selector1_packet(packet, sizeof(packet), &length) == 0);
    assert(length == sizeof(control) && !memcmp(packet, control, length));
    memset(before, 0xa5, sizeof(before)); memcpy(packet, before, sizeof(packet)); length = 99;
    assert(b41_agps_data_packet("a\0b", 3, packet, sizeof(packet), &length) == -EPROTO);
    assert(b41_agps_data_packet("abc", 3, packet, 16, &length) == -ENOSPC);
    assert(b41_agps_data_packet(NULL, 1, packet, sizeof(packet), &length) == -EINVAL);
    assert(b41_agps_data_packet(packet, 3, packet, sizeof(packet), &length) < 0);
    assert(length == 99 && !memcmp(packet, before, sizeof(packet)));

    assert(b41_agps_owner_init(owner) == 0);
    assert(b41_agps_owner_init(owner) == -EALREADY);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0);
    fd = sockets[0];
    assert(b41_agps_owner_take(owner, &fd, &bad, sizeof(bad)) == -EINVAL && fd == sockets[0]);
    take(owner, &fd);
    assert(b41_agps_owner_send_event(owner, &event) == -EOPNOTSUPP);
    assert(b41_agps_owner_send_data(owner, "abc", 3) == 0);
    assert(recv(sockets[1], received, sizeof(received), 0) == (ssize_t)sizeof(data));
    assert(!memcmp(received, data, sizeof(data)));
    assert(b41_agps_owner_send_selector1(owner) == 0);
    assert(recv(sockets[1], received, sizeof(received), 0) == (ssize_t)sizeof(control));
    assert(!memcmp(received, control, sizeof(control)));
    old = owner->fd;
    assert(b41_agps_owner_stop(owner) == 0);
    assert(b41_agps_owner_init(owner) == -EALREADY);
    assert(fcntl(old, F_GETFD) == -1 && errno == EBADF);
    assert(b41_agps_owner_stop(owner) == 0);
    assert(b41_agps_owner_send_selector1(owner) == -ESHUTDOWN);
    assert(close(sockets[1]) == 0);
    /* The mutex lifetime is process-wide; fresh test owners are distinct. */
    assert(pthread_mutex_destroy(&owner->lock) == 0); free(owner);

    owner = calloc(1, sizeof(*owner)); assert(owner && b41_agps_owner_init(owner) == 0);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0); fd = sockets[0]; take(owner, &fd);
    {
        pthread_t send_thread, stop_thread;
        struct worker sending = {.owner = owner}, stopping = {.owner = owner};
        old = owner->fd;
        block_send = 1;
        assert(pthread_create(&send_thread, NULL, sender, &sending) == 0);
        assert(pthread_mutex_lock(&test_lock) == 0);
        while (!send_entered)
            assert(pthread_cond_wait(&test_condition, &test_lock) == 0);
        assert(pthread_create(&stop_thread, NULL, stopper, &stopping) == 0);
        assert(fcntl(old, F_GETFD) >= 0); /* Send holds owner lock; stop cannot close. */
        release_send = 1;
        assert(pthread_cond_broadcast(&test_condition) == 0);
        assert(pthread_mutex_unlock(&test_lock) == 0);
        assert(pthread_join(send_thread, NULL) == 0);
        assert(pthread_join(stop_thread, NULL) == 0);
        block_send = 0;
        assert(sending.result == 0 && stopping.result == 0);
        assert(recv(sockets[1], received, sizeof(received), 0) == (ssize_t)sizeof(control));
        assert(fcntl(old, F_GETFD) == -1 && errno == EBADF);
        assert(owner->state == B41_AGPS_CLOSED);
    }
    assert(close(sockets[1]) == 0);
    assert(pthread_mutex_destroy(&owner->lock) == 0); free(owner);

    owner = calloc(1, sizeof(*owner)); assert(owner && b41_agps_owner_init(owner) == 0);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0); fd = sockets[0]; take(owner, &fd);
    assert(close(sockets[1]) == 0);
    assert(b41_agps_owner_send_selector1(owner) < 0);
    old = owner->first_error;
    assert(b41_agps_owner_send_data(owner, "abc", 3) == old);
    assert(b41_agps_owner_stop(owner) == old);
    assert(pthread_mutex_destroy(&owner->lock) == 0); free(owner);

    owner = calloc(1, sizeof(*owner)); assert(owner && b41_agps_owner_init(owner) == 0);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0); fd = sockets[0]; take(owner, &fd);
    old = owner->fd;
    assert(close(old) == 0);
    replacement = open("/dev/null", O_RDONLY); assert(replacement >= 0);
    if (replacement != old) { assert(dup2(replacement, old) == old); assert(close(replacement) == 0); }
    assert(b41_agps_owner_send_selector1(owner) == -ESTALE);
    assert(b41_agps_owner_stop(owner) == -ESTALE);
    assert(fcntl(old, F_GETFD) >= 0); /* Never close an already-reused foreign fd. */
    assert(close(old) == 0 && close(sockets[1]) == 0);
    assert(pthread_mutex_destroy(&owner->lock) == 0); free(owner);

    owner = calloc(1, sizeof(*owner)); assert(owner && b41_agps_owner_init(owner) == 0);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0); fd = sockets[0]; take(owner, &fd);
    short_send = 1;
    assert(b41_agps_owner_send_selector1(owner) == -EIO);
    short_send = 0;
    assert(b41_agps_owner_send_selector1(owner) == -EIO);
    assert(b41_agps_owner_stop(owner) == -EIO);
    assert(close(sockets[1]) == 0);
    assert(pthread_mutex_destroy(&owner->lock) == 0); free(owner);

    owner = calloc(1, sizeof(*owner)); assert(owner && b41_agps_owner_init(owner) == 0);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0); fd = sockets[0]; take(owner, &fd);
    for (unsigned i = 0; i < 4096; ++i) {
        int status = b41_agps_owner_send_selector1(owner);
        if (status) { assert(status == -EAGAIN || status == -EWOULDBLOCK); break; }
    }
    assert(owner->first_error == -EAGAIN || owner->first_error == -EWOULDBLOCK);
    assert(b41_agps_owner_stop(owner) == owner->first_error);
    assert(close(sockets[1]) == 0);
    assert(pthread_mutex_destroy(&owner->lock) == 0); free(owner);
    return 0;
}
