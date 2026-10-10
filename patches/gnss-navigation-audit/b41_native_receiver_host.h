/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_NATIVE_RECEIVER_HOST_H
#define B41_NATIVE_RECEIVER_HOST_H
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <sys/types.h>
#include <time.h>
#include "b41_library_association.h"
#include "b41_startup_adapter.h"
#include "b41_engine_arguments.h"
#include "b41_frame_worker.h"

enum b41_native_notice {
    B41_NATIVE_REPORT = 1u, B41_NATIVE_PROHIBITED = 2u,
    B41_NATIVE_RESTART = 4u, B41_NATIVE_UNSUPPORTED = 8u,
};
struct b41_native_control {
    int fd;
    atomic_uint pending;
    atomic_int first_error;
    unsigned initialized;
};
/* Native NMEA-only host, not Android mnld emulation. Event0 is a report notice,
 * never a fabricated position/RTC result. Actual raw output goes to gpsd through
 * the integrated output owner. No FM/raw-measurement/ADC service is enabled.
 * Bind once in a fresh process BEFORE registration/threads; owner lives until
 * process exit. A restart/fix-prohibition requests STOP, not automatic reboot.
 */
/* Initialize fresh ZEROED process-lifetime storage once. */
int b41_native_control_init(struct b41_native_control *control);
int b41_native_control_bind(struct b41_native_control *control,
    struct b41_known_callbacks *callbacks);
/* Sole setup controller only, before callbacks are bound. No close retry.
 * Once bound, the descriptor/storage is retained until engine-process exit.
 */
int b41_native_control_discard_unbound(struct b41_native_control *control);
/* Single controller only. Drain real eventfd, atomically take pending notices.
 * Callback threads never enter vendor stop/getters or perform filesystem I/O.
 */
int b41_native_control_take(struct b41_native_control *control, unsigned *notices);

#define B41_NATIVE_THREADS 17u
struct b41_native_thread_record {
    int32_t marker;
    uint32_t index;
    uint64_t handle, stop, wake;
};
struct b41_native_stop_snapshot {
    uintptr_t base;
    uint32_t offload;
    struct b41_native_thread_record threads[B41_NATIVE_THREADS];
};
/* Checks source join-success evidence, not a return value or elapsed timeout.
 * Source-owned records only; synthetic records are legitimate test fixtures,
 * never runtime proof. Out mask unchanged on failure. Primary RX must have
 * been live, preventing an unused/never-started image from passing.
 */
int b41_native_join_ack(const struct b41_native_stop_snapshot *before,
    const struct b41_native_stop_snapshot *after, unsigned *joined);

enum b41_native_stop_state {
    B41_NATIVE_STOP_EMPTY, B41_NATIVE_STOP_CAPTURED,
    B41_NATIVE_STOP_ENTERED, B41_NATIVE_STOP_ACKED, B41_NATIVE_STOP_QUARANTINED,
};
struct b41_native_stop_owner {
    enum b41_native_stop_state state;
    struct b41_native_stop_snapshot before;
    struct b41_library_association image;
    pthread_t controller;
    int first_error;
};
/* After actual initialization, on the sole controller in a dedicated engine
 * process. Reuses the existing legitimate loader association; does not dlopen,
 * configure/start an engine or make stale argument gates disappear.
 */
int b41_native_stop_capture(struct b41_native_stop_owner *owner,
    const struct b41_library_association *image);
/* Calls the ACTUAL mapped mtk_gps_mnl_stop52e2c0 exactly once, then requires
 * source join markers for all live records. This call can BLOCK in native join.
 * It must execute in an externally supervised dedicated child, never pmOS's
 * main service/USB process or an engine callback/worker. No timeout cancellation
 * or pthread-kill shortcut is installed here. Parent must retain/quarantine
 * resources until waitpid confirms child exit if the call does not return.
 * No fd close, callback unbind, dlclose or automatic restart occurs here.
 */
int b41_native_stop_call(struct b41_native_stop_owner *owner, unsigned *joined);

/* Parent of an exclusively owned dedicated engine child (no other wait/reaper).
 * Both deadlines are absolute CLOCK_MONOTONIC; cleanup_deadline >= deadline.
 * Waits for actual waitpid acknowledgement, not a child-written "stopped" flag.
 * On deadline: one SIGKILL, then bounded reap until cleanup_deadline. Forced
 * exit returns -ETIMEDOUT even when reaped; an unreaped child returns
 * -EINPROGRESS and remains quarantined. Neither is graceful engine-stop proof.
 * Never signals a nonchild, frees live callbacks or starts replacement engines.
 * wait_status changed only when child was actually reaped. No device I/O.
 */
int b41_native_child_wait(pid_t child, const struct timespec *deadline,
    const struct timespec *cleanup_deadline, int *wait_status);

/* Zeroed sole-parent state retained across bounded reap retries. first_error
 * preserves the operation failure; -EINPROGRESS means cleanup is incomplete,
 * not a replacement for the original timeout. STOP/CONTINUE are never reaps.
 */
struct b41_native_child_wait_owner {
    pid_t child;
    int escalated, first_error, reaped;
};
int b41_native_child_wait_owned(struct b41_native_child_wait_owner *owner,
    pid_t child, const struct timespec *deadline,
    const struct timespec *cleanup_deadline, int *wait_status);

struct b41_native_session_result {
    int registration_entered, run_entered;
    uint32_t run_status;
    unsigned notices, joined_threads;
    int native_stop_status, worker_stop_status;
};
/* ACTUAL register/run/control/stop controller, Bionic ARM64 dedicated child
 * only. Existing arguments' unresolved audit contracts must be ZERO; no flags
 * are cleared or replaced with caller opt-ins. Thus today's partial builders
 * are honestly refused. Constructors/calibration/AGPS closure remain required.
 * All objects/DSO/fds process-lifetime and exclusively controller-owned;
 * worker must be running and exposed before registration. Native notify must
 * already be bound before the argument table was constructed. No other reader.
 * After registration entered, caller must exit the dedicated process on EVERY
 * return (even failure); no free/unload/reinit/replacement in this child.
 * Normal deadline ends observation, not proof of a GNSS fix. Host exposure
 * quarantine remains visible as worker_stop_status=-EBUSY, never cleared.
 */
int b41_native_session_execute(const struct b41_library_association *image,
    const struct b41_engine_arguments *arguments, struct b41_native_control *control,
    struct b41_frame_worker *worker, struct b41_native_stop_owner *stop,
    const struct timespec *run_deadline, const struct timespec *worker_deadline,
    struct b41_native_session_result *result);
#endif
