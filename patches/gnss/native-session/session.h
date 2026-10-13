/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_NATIVE_SESSION_H
#define B41_NATIVE_SESSION_H

#include "gpsdl_v051_session.h"
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

enum b41_session_stage {
    B41_SESSION_NEW, B41_SESSION_WAIT_WORK, B41_SESSION_WORKING,
    B41_SESSION_STOP_TX, B41_SESSION_WAIT_RESET, B41_SESSION_WAIT_HWSTOP,
    B41_SESSION_STOPPED, B41_SESSION_FAILED
};

struct b41_native_session {
    enum b41_session_stage stage;
    int fd, first_error;
    dev_t device, rdevice;
    ino_t inode;
    uint32_t session_id;
    uint64_t deadline_ns, last_ns;
    struct gpsdl_v051_session_snapshot latest;
    size_t stop_offset;
};

/* Only actual opt-in ioctl31 results. Atomic output on error; no raw setter,
 * dmesg selector, ACK-derived readiness, disabled ioctl fallback or query12.
 */
int b41_session_snapshot(int fd, struct gpsdl_v051_session_snapshot *out);

/* Borrow the sole retained O_RDWR/O_NONBLOCK gps0 fd, preferably before MVCD.
 * Never open, duplicate, close or reset it. Resume wait_step after the same
 * owner's matched download ACKs; WORK means sampled kernel FSM, not a fix.
 */
int b41_session_attach(struct b41_native_session *owner, int fd, uint64_t deadline_ns);
int b41_session_wait_step(struct b41_native_session *owner);

/* Explicit firmware action, never called by snapshot/attach/wait. Stop uses
 * primary FE05/u16(4), waits for real DSP RST while link remains OPENED, then
 * issues exactly one existing ioctl18/arg0. STOPPED requires real STOP/SUSPENDED.
 * No resume/assert/reset, retry, deadline extension or forced close on error.
 */
int b41_session_stop_begin(struct b41_native_session *owner);
int b41_session_stop_step(struct b41_native_session *owner);

#endif
