/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_DSP_BOOTSTRAP_H
#define B41_DSP_BOOTSTRAP_H

#include "bootstrap_fields.h"
#include "wire.h"

/* Constructor-only codes stay outside Linux's negative errno range. */
enum b41_bootstrap_result {
    B41_BOOTSTRAP_OK = 0,
    B41_BOOTSTRAP_ARGUMENT = -10020,
    B41_BOOTSTRAP_MISSING = -10021,
    B41_BOOTSTRAP_EMBEDDED_IMAGE = -10022,
    B41_BOOTSTRAP_SESSION = -10023,
    B41_BOOTSTRAP_QUERY = -10024,
    B41_BOOTSTRAP_METADATA = -10025,
    B41_BOOTSTRAP_CAPACITY = -10026,
    B41_BOOTSTRAP_OVERLAP = -10027
};

struct b41_bootstrap_selectors {
    uint8_t secure_download_7178b8_33e;
    uint8_t dsp_selector_717cb0;
};

struct b41_bootstrap_route {
    uint8_t metadata_ioctl;
    uint8_t fragment_ioctl;
};

/* A fresh immutable object for one actual exclusively owned gps0 open.
 * Its address binds query snapshots, not a fabricated firmware/session ID.
 * Retain it, its descriptor and all input storage until transport completes;
 * never reuse it across close/reopen while a query snapshot remains live.
 * The pure constructor cannot establish device identity or exclusive ownership.
 */
struct b41_bootstrap_session {
    int gps0_fd;
    struct b41_bootstrap_selectors selectors;
    const struct b41_mvcd_bootstrap_inputs *fields;
};

/* Exact five-u32 ioctl23/24 output ABI. Secret storage, never diagnostics. */
struct b41_bootstrap_boot_info {
    uint32_t code_size;
    uint32_t start_addr;
    uint32_t exec_addr;
    uint32_t cipher_key;
    uint32_t frag_num;
};

/* Capture from one real ioctl on session->gps0_fd. status is the immediate
 * normalized syscall result: zero, or negative errno. Never OEM status2/18.
 * bytes_returned denotes the complete copied ABI record (20 bytes on success),
 * not ioctl's return value. Keep the actual full metadata; no low16 substitutes.
 */
struct b41_bootstrap_query {
    const struct b41_bootstrap_session *session;
    int gps0_fd;
    struct b41_bootstrap_selectors selectors;
    unsigned int command;
    int status;
    const struct b41_bootstrap_boot_info *info;
    size_t bytes_returned;
};

/* Nonzero secure flag: selector1..63 ->24/26 (CW), otherwise23/25 (MVCD).
 * Zero flag selects embedded images and is explicitly unsupported here.
 * No output modification on error.
 */
int b41_bootstrap_route_select(const struct b41_bootstrap_selectors *selectors,
                               struct b41_bootstrap_route *out);

/* Construct all106 bytes / the complete116-byte frame in private owner storage.
 * These buffers contain the session key and are ONLY for the owned transport;
 * never log, publish, save as an artifact or send them to a diagnostics sink.
 * Wipe caller metadata and output when their owned transport lifetime ends.
 * Capacity/argument/session/query/metadata/field errors leave every output
 * untouched. Negative query status and field/clock errors propagate unchanged.
 * Success certifies assembly from supplied snapshots, not hardware readiness.
 */
int b41_bootstrap_payload_build(const struct b41_bootstrap_session *session,
                                const struct b41_bootstrap_query *query,
                                uint8_t *payload, size_t capacity);
int b41_bootstrap_frame_build(const struct b41_bootstrap_session *session,
                              const struct b41_bootstrap_query *query,
                              uint8_t *frame, size_t capacity, size_t *written);

#endif
