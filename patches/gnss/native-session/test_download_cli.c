/* SPDX-License-Identifier: GPL-2.0-only */
/* Synthetic main-loop history only; no device or firmware is accessed. */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE 1
#include "session.h"
#include "../../gnss-navigation-audit/dsp-download/download.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum { SUCCESS, ATTACH_FAIL, INHERITED_WORK, METADATA_FAIL, DOWNLOAD_FAIL,
       WAIT_FAIL, STOP_FAIL, INTERRUPTED, CASES };
enum { PROFILE_FD = 100, CONN_FD = 101, GPS_FD = 102 };
static int scenario, gps_closes, opens, download_done, waits, stops;
int b41_retained_main(int argc, char **argv);

int __wrap_open(const char *path, int flags, ...)
{
    opens++;
    if (!strcmp(path, "fixture-profile")) return PROFILE_FD;
    if (!strcmp(path, "/dev/conninfra_dev")) return CONN_FD;
    assert(!strcmp(path, "/dev/gpsdl0"));
    assert((flags & O_ACCMODE) == O_RDWR && (flags & O_NONBLOCK));
    assert(opens == 3);
    return GPS_FD;
}

int __wrap_fstat(int fd, struct stat *st)
{
    assert(fd == PROFILE_FD || fd == GPS_FD);
    memset(st, 0, sizeof(*st));
    st->st_mode = (fd == PROFILE_FD ? S_IFREG : S_IFCHR) | 0600;
    st->st_size = 54;
    return 0;
}

int __wrap_fcntl(int fd, int command, ...)
{
    assert(fd == GPS_FD && command == F_GETFL);
    return O_RDWR | O_NONBLOCK;
}

ssize_t __wrap_pread(int fd, void *buffer, size_t count, off_t offset)
{
    const uint8_t numeric[10] = {0x80, 0xba, 0x8c, 0x01, 0, 0, 0, 0, 255, 0};
    assert(fd == PROFILE_FD);
    if (!offset) { assert(count == 1); *(uint8_t *)buffer = 't'; }
    else { assert(offset == 24 && count == sizeof(numeric)); memcpy(buffer, numeric, count); }
    return (ssize_t)count;
}

int __wrap_close(int fd)
{
    if (fd == GPS_FD) {
        assert(scenario == SUCCESS && stops == 3);
        gps_closes++;
    } else assert(fd == PROFILE_FD || fd == CONN_FD);
    return 0;
}

int __wrap_clock_gettime(clockid_t clock, struct timespec *time)
{
    assert(clock == CLOCK_MONOTONIC);
    *time = (struct timespec){10, 0};
    return 0;
}

int __wrap_ioctl(int fd, unsigned long command, ...)
{
    va_list args;
    if (fd == CONN_FD) {
        assert(command == 0x8004c200UL || command == 0x8004c203UL);
        return command == 0x8004c200UL ? 0x6878 : 0x6631;
    }
    assert(fd == GPS_FD);
    if (command == 11) return 33;
    if (command == 30) return 0;
    if (command == 16 || command == 29) { errno = EFAULT; return -1; }
    assert(command == 23);
    if (scenario == METADATA_FAIL) { errno = EIO; return -1; }
    va_start(args, command);
    struct b41_bootstrap_boot_info *info = va_arg(args, struct b41_bootstrap_boot_info *);
    *info = (struct b41_bootstrap_boot_info){.code_size = 8, .frag_num = 1};
    va_end(args);
    return 0;
}

int __wrap_b41_session_attach(struct b41_native_session *owner, int fd, uint64_t deadline)
{
    assert(fd == GPS_FD && deadline == UINT64_C(15000000000));
    if (scenario == ATTACH_FAIL) return -EFAULT;
    owner->fd = fd;
    owner->stage = B41_SESSION_WAIT_WORK;
    owner->latest.dsp_state = scenario == INHERITED_WORK ? 3u : 2u;
    return 0;
}

int __wrap_b41_download_linux_step(struct b41_download *owner)
{
    assert(!gps_closes && !waits && !stops);
    if (scenario == DOWNLOAD_FAIL) return -EPROTO;
    owner->stage = B41_DOWNLOAD_ACKS_COMPLETE;
    download_done = 1;
    return 0;
}

int __wrap_b41_session_wait_step(struct b41_native_session *owner)
{
    assert(download_done && !gps_closes && !stops);
    waits++;
    if (scenario == WAIT_FAIL) return -ESTALE;
    if (waits == 2) owner->stage = B41_SESSION_WORKING;
    return 0;
}

int __wrap_b41_session_stop_begin(struct b41_native_session *owner)
{
    assert(download_done && waits == 2 && owner->stage == B41_SESSION_WORKING);
    assert(!gps_closes && !stops);
    if (scenario == STOP_FAIL) return -EIO;
    owner->stage = B41_SESSION_STOP_TX;
    return 0;
}

int __wrap_b41_session_stop_step(struct b41_native_session *owner)
{
    assert(download_done && waits == 2 && !gps_closes);
    stops++;
    owner->stage = stops == 3 ? B41_SESSION_STOPPED :
        stops == 2 ? B41_SESSION_WAIT_HWSTOP : B41_SESSION_WAIT_RESET;
    return 0;
}

int __wrap_nanosleep(const struct timespec *request, struct timespec *remaining)
{
    (void)remaining;
    assert(request->tv_sec == 0 && request->tv_nsec == 1000000);
    if (scenario == INTERRUPTED) assert(!raise(SIGTERM));
    return 0;
}

int __wrap_pause(void)
{
    assert(scenario != SUCCESS && !gps_closes && opens == 3);
    /* Reaching this intercepted wait proves the real main did not exit/close.
     * Exit only the synthetic child; there is no actual GPS file reference.
     */
    _Exit(0);
}

int main(void)
{
    for (scenario = 0; scenario < CASES; scenario++) {
        pid_t child = fork();
        assert(child >= 0);
        if (!child) {
            char *argv[] = {"gnss-l1-retained", "fixture-profile", NULL};
            int status = b41_retained_main(2, argv);
            assert(scenario == SUCCESS && status == 0 && gps_closes == 1 && opens == 3);
            _Exit(0);
        }
        int status;
        assert(waitpid(child, &status, 0) == child);
        assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
    puts("retained download CLI lifecycle and recovery-hold fixtures passed; synthetic only");
    return 0;
}
