/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MIPC_SUPERVISED_CHILD_H
#define B41_MIPC_SUPERVISED_CHILD_H
#include <sys/types.h>
#include <time.h>
#include "b41_native_receiver_host.h"
#define B41_MIPC_STAGE_MAX 16u
struct b41_mipc_supervision {
    unsigned entered, count, bind_attempted, reaped, terminal;
    pid_t child;
    int stage[B41_MIPC_STAGE_MAX];
    struct timespec deadline, cleanup_deadline;
    int wait_status, wait_error;
    struct b41_native_child_wait_owner wait_owner;
};
/* Zeroed single-use owner. Moves actual fully sealed memfds (sets inputs=-1)
 * before child creation. Deadlines are absolute CLOCK_MONOTONIC and cover ALL
 * child startup, including0x305 init retries and141, not reset between phases.
 * Seals prove staging immutability, NOT ELF identity/closure/config readiness.
 */
int b41_mipc_supervision_prepare(struct b41_mipc_supervision *owner,
    int *stage, unsigned count, const struct timespec *deadline,
    const struct timespec *cleanup_deadline);
/* Called only with the actual newly created sole-parent child. This module
 * does not launch any initializer or provide missing runtime prerequisites.
 * Failed/ambiguous bind is quarantined; no lease release is authorized.
 */
int b41_mipc_supervision_bind(struct b41_mipc_supervision *owner, pid_t child);
/* Uses existing controller with persistent wait state. Only terminal waitpid
 * acknowledgement (EXITED/SIGNALED, never traced STOP/CONTINUE)
 * authorizes closing the retained stage. Timeout/forced exit is not graceful
 * RX join, calibration success or permission to restart. Unreaped retains all.
 */
int b41_mipc_supervision_finish(struct b41_mipc_supervision *owner);
/* Rollback only before ANY child bind attempt; never unloads a live child. */
int b41_mipc_supervision_abort_unstarted(struct b41_mipc_supervision *owner);
#endif
