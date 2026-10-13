/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "session.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* Inspect an inherited descriptor; its parent retains the same file lifetime.
 * Default is strictly read-only. The integrated download owner should link
 * session.c directly, avoiding any handoff or extra reader/writer.
 */
int main(int argc, char **argv)
{
    struct b41_native_session owner = {0};
    struct gpsdl_v051_session_snapshot snapshot;
    struct timespec now;
    unsigned long descriptor, ms = 5000;
    uint64_t deadline;
    char *end;
    int status, wait = 0, stop = 0;
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("usage: gnss-session FD [--wait-work|--stop] [TIMEOUT_MS:1..30000]");
        return 0;
    }
    if (argc < 2 || argc > 4 || !argv[1][0] ||
        strspn(argv[1], "0123456789") != strlen(argv[1])) return 2;
    errno = 0;
    descriptor = strtoul(argv[1], &end, 10);
    if (errno || *end || descriptor > INT_MAX) return 2;
    if (argc >= 3) {
        wait = !strcmp(argv[2], "--wait-work");
        stop = !strcmp(argv[2], "--stop");
        if (!wait && !stop) return 2;
    }
    if (argc == 4) {
        if (!argv[3][0] || strspn(argv[3], "0123456789") != strlen(argv[3])) return 2;
        errno = 0;
        ms = strtoul(argv[3], &end, 10);
        if (errno || *end || ms < 1 || ms > 30000) return 2;
    }
    if (!wait && !stop) {
        status = b41_session_snapshot((int)descriptor, &snapshot);
        if (!status) printf("session=%u link=%u dsp=%u sampled=1\n",
            (unsigned)snapshot.session_id, (unsigned)snapshot.link_state, (unsigned)snapshot.dsp_state);
    } else {
        if (clock_gettime(CLOCK_MONOTONIC, &now)) return 1;
        if (now.tv_sec < 0 || now.tv_nsec < 0 || now.tv_nsec >= 1000000000 ||
            (uint64_t)now.tv_sec > (UINT64_MAX - (uint64_t)now.tv_nsec - (uint64_t)ms*1000000u)/1000000000u)
            return 1;
        deadline = (uint64_t)now.tv_sec*1000000000u + (uint64_t)now.tv_nsec + (uint64_t)ms*1000000u;
        /* The parent retains its original file reference even if this child
         * exits on a stalled syscall. Never use this tool as the sole fd owner.
         */
        alarm((unsigned int)((ms + 999u)/1000u + 2u));
        status = b41_session_attach(&owner, (int)descriptor, deadline);
        while (!status && owner.stage == B41_SESSION_WAIT_WORK) {
            struct timespec idle = {0, 1000000};
            status = b41_session_wait_step(&owner);
            if (!status && owner.stage == B41_SESSION_WAIT_WORK && nanosleep(&idle, NULL)) status = -errno;
        }
        if (!status && stop) status = b41_session_stop_begin(&owner);
        while (!status && stop && owner.stage != B41_SESSION_STOPPED) {
            struct timespec idle = {0, 1000000};
            status = b41_session_stop_step(&owner);
            if (!status && owner.stage != B41_SESSION_STOPPED && nanosleep(&idle, NULL)) status = -errno;
        }
        if (!status) puts(stop ? "sampled HW_STOP/SUSPENDED; parent may perform normal close" :
                                   "sampled WORKING; no navigation/fix established; parent retains fd");
    }
    alarm(0);
    if (status) fprintf(stderr, "session_failed status=%d; parent retains fd/recovery responsibility\n", status);
    return status ? 1 : 0;
}
