/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_frame_worker.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <string.h>
#include <unistd.h>
static struct b41_host_adapter adapter;
static struct b41_known_callbacks callbacks;
static struct b41_frame_worker workers[6];
static struct b41_agps_owner ipc[6];
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static int hold, entered;
ssize_t __real_send(int, const void *, size_t, int);
ssize_t __wrap_send(int fd, const void *bytes, size_t length, int flags)
{
    assert(pthread_mutex_lock(&lock) == 0);
    entered = 1; assert(pthread_cond_broadcast(&condition) == 0);
    while (hold) assert(pthread_cond_wait(&condition, &lock) == 0);
    assert(pthread_mutex_unlock(&lock) == 0);
    return __real_send(fd, bytes, length, flags);
}
static struct timespec deadline(void)
{
    struct timespec result; assert(clock_gettime(CLOCK_MONOTONIC, &result) == 0);
    ++result.tv_sec; return result;
}
static int setup(unsigned index, int *receiver)
{
    int pair[2]; struct sockaddr_un peer; socklen_t length = sizeof(peer);
    assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, pair) == 0);
    memset(&peer, 0, sizeof(peer));
    assert(getpeername(pair[0], (struct sockaddr *)&peer, &length) == 0);
    assert(b41_agps_owner_init(&ipc[index]) == 0);
    assert(b41_agps_owner_take(&ipc[index], &pair[0], &peer, length) == 0);
    if (index == 4) { assert(close(pair[1]) == 0); pair[1] = -1; }
    *receiver = open("/dev/null", O_RDONLY); assert(*receiver >= 0);
    int transferred = *receiver;
    assert(b41_frame_worker_start(&workers[index], &adapter, &ipc[index], &transferred, 1) == 0);
    assert(transferred == -1); return pair[1];
}
int main(void)
{
    int receiver, peer;
    struct timespec until;
    unsigned char got[256], expected[256], payload[32]; size_t payload_size, packet_size;
    assert(b41_host_adapter_init(&adapter) == 0);
    assert(b41_host_adapter_bind(&adapter, &callbacks) == 0);
    assert(callbacks.frame_sleep(1) == 0);
    peer = setup(0, &receiver);
    struct pollfd readable = {peer, POLLIN, 0}; assert(poll(&readable, 1, 1000) == 1);
    ssize_t received = recv(peer, got, sizeof(got), 0);
    assert(b41_frame_sync_encode(3, 1, payload, sizeof(payload), &payload_size) == 0);
    assert(b41_agps_data_packet(payload, payload_size, expected, sizeof(expected), &packet_size) == 0);
    assert(received == (ssize_t)packet_size && memcmp(got, expected, packet_size) == 0);
    until = deadline(); assert(b41_frame_worker_quiesce(&workers[0], &until) == 0);
    assert(fcntl(receiver, F_GETFD) >= 0); /* Quiescence never closes device fds. */
    assert(b41_frame_worker_release_unused(&workers[0]) == 0);
    assert(fcntl(receiver, F_GETFD) == -1 && errno == EBADF); assert(close(peer) == 0);
    peer = setup(1, &receiver);
    assert(b41_frame_worker_expose(&workers[1]) == 0);
    until = deadline(); assert(b41_frame_worker_quiesce(&workers[1], &until) == -EBUSY);
    assert(workers[1].state == B41_WORKER_QUARANTINED && fcntl(receiver, F_GETFD) >= 0);
    assert(b41_frame_worker_release_unused(&workers[1]) == -EPERM); assert(close(peer) == 0);
    /* Hold actual worker in send while control deadline expires, without sleeps. */
    assert(pthread_mutex_lock(&lock) == 0); hold = 1; entered = 0;
    assert(pthread_mutex_unlock(&lock) == 0);
    assert(callbacks.frame_network() == 0); peer = setup(2, &receiver);
    assert(pthread_mutex_lock(&lock) == 0);
    while (!entered) assert(pthread_cond_wait(&condition, &lock) == 0);
    assert(pthread_mutex_unlock(&lock) == 0);
    assert(clock_gettime(CLOCK_MONOTONIC, &until) == 0); /* Expired deadline => immediate poll. */
    assert(b41_frame_worker_quiesce(&workers[2], &until) == -ETIMEDOUT);
    assert(fcntl(receiver, F_GETFD) >= 0);
    assert(pthread_mutex_lock(&lock) == 0); hold = 0;
    assert(pthread_cond_broadcast(&condition) == 0); assert(pthread_mutex_unlock(&lock) == 0);
    readable = (struct pollfd){workers[2].done_fd, POLLIN, 0}; assert(poll(&readable, 1, 1000) == 1);
    until = deadline(); assert(b41_frame_worker_quiesce(&workers[2], &until) == -ETIMEDOUT);
    assert(b41_frame_worker_release_unused(&workers[2]) == -EPERM); assert(close(peer) == 0);
    peer = setup(3, &receiver);
    until = deadline(); assert(b41_frame_worker_quiesce(&workers[3], &until) == 0);
    int pipe_fds[2]; assert(pipe(pipe_fds) == 0);
    assert(close(receiver) == 0 && dup2(pipe_fds[0], receiver) == receiver);
    assert(b41_frame_worker_release_unused(&workers[3]) == -ESTALE);
    assert(fcntl(receiver, F_GETFD) >= 0); /* Replaced foreign fd was NOT closed. */
    assert(close(peer) == 0);
    assert(callbacks.frame_measurement(1) == 0);
    peer = setup(4, &receiver); assert(peer == -1);
    readable = (struct pollfd){workers[4].done_fd, POLLIN, 0}; assert(poll(&readable, 1, 1000) == 1);
    int failure = atomic_load(&workers[4].failure); assert(failure < 0);
    until = deadline(); assert(b41_frame_worker_quiesce(&workers[4], &until) == failure);
    assert(fcntl(receiver, F_GETFD) >= 0 && workers[4].state == B41_WORKER_QUARANTINED);
    assert(callbacks.output("$GPGGA", 6) == 0); peer = setup(5, &receiver);
    readable = (struct pollfd){workers[5].done_fd, POLLIN, 0}; assert(poll(&readable, 1, 1000) == 1);
    until = deadline(); assert(b41_frame_worker_quiesce(&workers[5], &until) == -EOPNOTSUPP);
    assert(fcntl(receiver, F_GETFD) >= 0); assert(close(peer) == 0);
    return 0;
}
