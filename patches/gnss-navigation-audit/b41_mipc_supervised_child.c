/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_mipc_supervised_child.h"
#include "b41_native_receiver_host.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static int valid(const struct timespec *t)
{
    return t && t->tv_sec >= 0 && t->tv_nsec >= 0 && t->tv_nsec < 1000000000L;
}

static int order(const struct timespec *a, const struct timespec *b)
{
    return a->tv_sec == b->tv_sec ? (a->tv_nsec > b->tv_nsec) - (a->tv_nsec < b->tv_nsec) :
        (a->tv_sec > b->tv_sec) - (a->tv_sec < b->tv_sec);
}

static int close_stage(struct b41_mipc_supervision *o)
{
    int first = 0;
    for (unsigned i = 0; i < o->count; ++i) {
        if (o->stage[i] >= 0 && close(o->stage[i]) && !first)
            first = -errno;
        /* Never retry close(EINTR): fd may already have been closed. */
        o->stage[i] = -1;
    }
    return first;
}

int b41_mipc_supervision_prepare(struct b41_mipc_supervision *o,
    int *stage, unsigned count, const struct timespec *deadline,
    const struct timespec *cleanup)
{
    struct timespec now;
    struct stat identities[B41_MIPC_STAGE_MAX];
    const int required = F_SEAL_SEAL | F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK;
    if (!o || o->entered || !stage || !count || count > B41_MIPC_STAGE_MAX ||
        !valid(deadline) || !valid(cleanup) || order(cleanup, deadline) < 0)
        return -EINVAL;
    if (clock_gettime(CLOCK_MONOTONIC, &now))
        return -errno;
    if (order(deadline, &now) <= 0)
        return -ETIMEDOUT;
    for (unsigned i = 0; i < count; ++i) {
        if (stage[i] < 0)
            return -EBADF;
        if (fstat(stage[i], &identities[i]))
            return -errno;
        if (!S_ISREG(identities[i].st_mode) || identities[i].st_size <= 0)
            return -EINVAL;
        int seals = fcntl(stage[i], F_GET_SEALS);
        if (seals < 0)
            return -errno;
        if ((seals & required) != required)
            return -EPERM;
        for (unsigned j = 0; j < i; ++j)
            if (identities[j].st_dev == identities[i].st_dev &&
                identities[j].st_ino == identities[i].st_ino)
                return -EEXIST;
    }
    o->entered = 1;
    o->count = count;
    o->deadline = *deadline;
    o->cleanup_deadline = *cleanup;
    o->wait_status = INT_MIN;
    for (unsigned i = 0; i < count; ++i) {
        o->stage[i] = stage[i];
        stage[i] = -1;
    }
    return 0;
}

int b41_mipc_supervision_bind(struct b41_mipc_supervision *o, pid_t child)
{
    siginfo_t info = {0};
    if (!o || !o->entered || o->terminal || o->bind_attempted || child <= 0)
        return -EINVAL;
    o->bind_attempted = 1;
    o->child = child;
    /* Prove it is still our unreaped child WITHOUT consuming exit status. */
    if (waitid(P_PID, (id_t)child, &info, WEXITED | WNOHANG | WNOWAIT))
        return -errno;
    return 0;
}

int b41_mipc_supervision_finish(struct b41_mipc_supervision *o)
{
    if (!o || !o->entered || !o->bind_attempted || o->child <= 0 || o->terminal)
        return -EINVAL;
    int status = INT_MIN;
    int rc = b41_native_child_wait_owned(&o->wait_owner, o->child,
        &o->deadline, &o->cleanup_deadline, &status);
    o->wait_error = o->wait_owner.first_error ? o->wait_owner.first_error : rc;
    if (status == INT_MIN || !(WIFEXITED(status) || WIFSIGNALED(status)))
        return rc ? rc : -EPROTO;
    o->wait_status = status;
    o->reaped = 1;
    o->terminal = 1;
    int cleanup = close_stage(o);
    return rc ? rc : cleanup;
}

int b41_mipc_supervision_abort_unstarted(struct b41_mipc_supervision *o)
{
    if (!o || !o->entered || o->bind_attempted || o->terminal)
        return -EINVAL;
    int rc = close_stage(o);
    o->terminal = 1;
    return rc;
}
