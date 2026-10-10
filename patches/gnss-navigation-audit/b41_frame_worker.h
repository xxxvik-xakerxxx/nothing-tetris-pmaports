/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_FRAME_WORKER_H
#define B41_FRAME_WORKER_H
#include "b41_agps_host.h"
#include <stdatomic.h>
#include <time.h>
enum b41_worker_state { B41_WORKER_FRESH, B41_WORKER_RUNNING,
    B41_WORKER_QUIESCED, B41_WORKER_QUARANTINED, B41_WORKER_RELEASED };
struct b41_frame_worker {
    /* Single controller, fresh zeroed process-lifetime storage. No reset/free
     * API: opaque library callbacks may retain adapter even on init failure.
     */
    enum b41_worker_state state;
    struct b41_host_adapter *adapter;
    struct b41_agps_owner *ipc;
    /* Optional source-specific envelope dispatcher, set before start and
     * immutable until process exit. NULL selects the existing navigation ABI.
     */
    int (*dispatch)(struct b41_agps_owner *, const struct b41_host_event *);
    atomic_int stop_requested, failure;
    unsigned exposed;
    int wake_fd, done_fd, receiver[2];
    unsigned receiver_count;
    struct stat identity[2];
};
/* Move exclusive ownership of already-open receiver fds, keeping their exact
 * identities. This is NOT proof of gpsdl device/firmware readiness. IPC owner
 * and callback adapter must live until process exit; no other worker may drain
 * this queue or use IPC while running. Failure retains caller's receiver fds.
 */
int b41_frame_worker_start(struct b41_frame_worker *worker,
    struct b41_host_adapter *adapter, struct b41_agps_owner *ipc,
    int *receiver_fds, unsigned count);
/* Irreversible: call BEFORE any library registration/init can retain resources.
 * The API intentionally provides no fabricated engine-stop/retention release.
 */
int b41_frame_worker_expose(struct b41_frame_worker *worker);
/* Cooperative quiescence of THIS worker, not native engine stop. Absolute
 * CLOCK_MONOTONIC deadline. No pthread_join/cancel or blocking send on control
 * thread. Deadline failure, worker failure, or exposure quarantines all receiver
 * fds/callback storage until process exit. A late worker exit never revives it.
 */
int b41_frame_worker_quiesce(struct b41_frame_worker *worker,
                            const struct timespec *deadline);
/* Separate cleanup for a worker NEVER exposed to the library and successfully
 * quiesced. Device close may itself block in the kernel: this is NOT the bounded
 * quiescence path. Any failure latches quarantine; no cleanup/reinit retry.
 */
int b41_frame_worker_release_unused(struct b41_frame_worker *worker);
#endif
