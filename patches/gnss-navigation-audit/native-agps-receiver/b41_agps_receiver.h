/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_AGPS_RECEIVER_H
#define B41_AGPS_RECEIVER_H
#include "../b41_library_association.h"
#include <stdatomic.h>
#include <pthread.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>

#define B41_AGPS_RX_MAX 65536u
#define B41_AGPS_PMTK_MAX 256u /* Includes NUL: lib6b18d4 limit0x101. */
struct b41_agps_request {
    unsigned type, parameter, length;
    const unsigned char *payload;
};
/* Borrowed view, synchronous use only; output unchanged on refusal. Strict
 * extents replace stock's zero-filled/truncating parser, never create data.
 * 250: optional C string, absent refused; 256..262/264: u32LE size + bytes.
 */
int b41_agps_receiver_decode(const void *packet, size_t length,
                            struct b41_agps_request *out);

enum b41_agps_rx_state { B41_AGPS_RX_FRESH, B41_AGPS_RX_BOUND, B41_AGPS_RX_PREPARED,
    B41_AGPS_RX_RUNNING, B41_AGPS_RX_QUIESCED, B41_AGPS_RX_QUARANTINED,
    B41_AGPS_RX_CLOSED };
struct b41_agps_receiver {
    unsigned entered;
    enum b41_agps_rx_state state;
    int fd[4]; /* Private socket, stop, completion, activation eventfds. */
    struct stat identity[4];
    pid_t peer_pid;
    uid_t peer_uid;
    pid_t controller_pid;
    pthread_t controller;
    struct b41_library_association image;
    atomic_int stop, first_error;
    atomic_uint delivered;
    unsigned char packet[B41_AGPS_RX_MAX];
};
/* Fresh zeroed, process-lifetime owner, sole controller. Abstract B4.1 route
 * only: binds NUL+mtk_agps2mnl with sockaddr length15. No filesystem fallback,
 * unlink, inherited fd, dup, property, library call or readiness assertion.
 * Peer PID/UID must identify a legitimate supervisor-owned assistance service.
 * Every datagram requires matching SCM_CREDENTIALS; names are not credentials.
 */
int b41_agps_receiver_open(struct b41_agps_receiver *owner, pid_t peer, uid_t uid);
/* PRE-INIT: Bionic ARM64 only. Authenticate the immutable complete ELF and closure in
 * trusted staging BEFORE this call. Association validates the actual loader
 * mapping, not its hash. No caller callback/function pointer or ready flag.
 * Associate then start a PARKED receiver worker: it cannot read or dispatch
 * socket messages until activate. Return1 means incomplete service contract;
 * no AGPS/INIT gate is cleared. Bound socket/peer identity is not a service
 * implementation or a pre-INIT assistance readiness acknowledgement.
 */
int b41_agps_receiver_prepare(struct b41_agps_receiver *owner,
    const void *elf, size_t size, const struct b41_library_view *view);
/* Sole controller, PREPARED/RUNNING only. Sample sticky failure, descriptor
 * identities and completion without consuming its acknowledgement. No native
 * calls, readiness assertion or cleanup. Zero is a sampled observation only.
 */
int b41_agps_receiver_observe(struct b41_agps_receiver *owner);
/* POST-INIT: controller calls only after real native run returned18. Checks
 * actual live primary RX/nonoffload records, then wakes the parked worker via
 * its owned activation eventfd. No caller run-status/ready flag is accepted.
 * Still not evidence that the forward assistance service exists. A failed
 * activation leaves the worker parked for explicit quiescence/child exit.
 */
int b41_agps_receiver_activate(struct b41_agps_receiver *owner);
/* Convenience post-INIT prepare+activate; prefer the two-stage API in the
 * controller. Does not bypass existing native argument admission gates.
 */
int b41_agps_receiver_start(struct b41_agps_receiver *owner,
    const void *elf, size_t size, const struct b41_library_view *view);
/* Quiesce BEFORE native stop/queue destruction. Detached worker publishes
 * completion only after its last owner/DSO access. Timeout retains ALL fds,
 * owner and DSO until supervised child exit/reap; no cancellation or retry.
 * Native dispatch can block: parent process deadline remains mandatory.
 */
int b41_agps_receiver_quiesce(struct b41_agps_receiver *owner,
                             const struct timespec *deadline);
/* Only bound-never-started or completion-acknowledged owners. Close once,
 * checking retained identities first. No engine stop/unbind/unload here.
 */
int b41_agps_receiver_close(struct b41_agps_receiver *owner);

/* Separate translation unit permits CI linker interception without injecting
 * runtime callbacks. Production always uses the exact associated native image.
 */
int b41_agps_native_associate(const void *elf, size_t size,
    const struct b41_library_view *view, struct b41_library_association *out);
int b41_agps_native_admit(const struct b41_library_association *image);
int b41_agps_native_deliver(const struct b41_library_association *image,
                          const struct b41_agps_request *request);
#endif
