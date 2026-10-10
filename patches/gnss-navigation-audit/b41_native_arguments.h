/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_NATIVE_ARGUMENTS_H
#define B41_NATIVE_ARGUMENTS_H
#include "b41_native_receiver_host.h"
#include "b41_navigation_output.h"
#include "b41_gpsdl_identity.h"

struct b41_native_arguments_owner {
    unsigned entered;
    int first_error;
    struct b41_library_association image;
    struct b41_gpsdl_identity devices;
    struct b41_host_adapter adapter;
    struct b41_native_control control;
    struct b41_navigation_output output;
    struct b41_frame_worker worker;
    struct b41_native_stop_owner stop;
    struct b41_engine_arguments arguments;
};
/* Configuration-only requirement projection, NOT engine arguments/readiness.
 * Native ownership requirements are established separately by prepare().
 * Unknown bits and producer first/config/AGPS requirements are preserved.
 */
unsigned b41_native_arguments_config_missing(const struct b41_startup_bundle *bundle);
/* Sole controller in a fresh supervised engine child, zeroed process-lifetime
 * owner. Immutable ELF must already pass the existing whole-file SHA gate.
 * Association is derived here from the real loader view, not caller flags.
 * Move actual gpsdl descriptors and distinct app/raw FIFO or PTY sinks; ipc is
 * an already-owned audited datagram endpoint, NOT proof of an AGPS receiver.
 * No register/run call. Returns 1 with config/AGPS requirements still missing.
 * After entered becomes nonzero EVERY return requires child process exit;
 * resources may have moved/bound, no retry/free/close/unload is permitted.
 * Parent must use b41_native_child_wait, retaining resources until real reap.
 */
int b41_native_arguments_prepare(struct b41_native_arguments_owner *owner,
    const struct b41_startup_bundle *bundle,
    const void *elf, size_t elf_size, const struct b41_library_view *view,
    struct b41_agps_owner *ipc, int receiver_fds[2], unsigned receiver_count,
    int *app_fd, int *raw_fd);
/* Uses only this producer's retained objects, not an independently mutable
 * argument table. Existing session validation and missing masks still apply.
 */
int b41_native_arguments_execute(struct b41_native_arguments_owner *owner,
    const struct timespec *run_deadline, const struct timespec *worker_deadline,
    struct b41_native_session_result *result);
#endif
