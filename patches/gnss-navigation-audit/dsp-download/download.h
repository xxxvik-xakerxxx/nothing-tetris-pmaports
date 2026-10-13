/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_DSP_DOWNLOAD_H
#define B41_DSP_DOWNLOAD_H

#include "bootstrap.h"

enum b41_download_stage {
    B41_DOWNLOAD_NEW,
    B41_DOWNLOAD_BOOTSTRAP_TX,
    B41_DOWNLOAD_BOOTSTRAP_RX,
    B41_DOWNLOAD_FRAGMENT_IOCTL,
    B41_DOWNLOAD_FRAGMENT_RX,
    B41_DOWNLOAD_ACKS_COMPLETE,
    B41_DOWNLOAD_FAILED
};

enum b41_download_action_kind {
    B41_DOWNLOAD_WRITE,
    B41_DOWNLOAD_READ,
    B41_DOWNLOAD_SUBMIT_FRAGMENT,
    B41_DOWNLOAD_DONE
};

struct b41_download_action {
    enum b41_download_action_kind kind;
    int gps0_fd;
    const uint8_t *bytes;
    size_t size;
    unsigned int command;
    unsigned int argument;
    uint64_t deadline_ns;
};

/* Private single-threaded storage for ONE exclusively owned gps0 open.
 * Zero-initialize once before begin; never reset/reuse for that same open.
 * No close, duplicate reader, reset or field mutation may race this owner.
 * ACKS_COMPLETE is protocol completion, NOT kernel RAM_CODE_READY / WORKING.
 * The caller must retain the session and close through its normal lifecycle;
 * this controller does not acquire a descriptor or establish physical ownership.
 */
struct b41_download {
    enum b41_download_stage stage;
    enum b41_download_stage failure_stage;
    int first_error;
    const struct b41_bootstrap_session *session;
    int gps0_fd;
    struct b41_bootstrap_selectors selectors;
    unsigned int fragment_count;
    unsigned int fragment_sequence;
    unsigned int matched_fragments;
    uint64_t deadline_ns;
    uint64_t last_now_ns;
    uint8_t tx[B41_MVCD_BOOTSTRAP_FRAME_SIZE];
    size_t tx_size;
    size_t tx_offset;
    uint8_t rx[B41_MVCD_ACK_PAYLOAD_MAX + 10u];
    size_t rx_size;
};

/* Real normalized ioctl23/24 snapshot, not a fixture or OEM status, is required.
 * deadline_ns is one absolute CLOCK_MONOTONIC deadline for the whole attempt.
 * No synthetic defaults, metadata query, transport operation or retry occurs.
 */
int b41_download_begin(struct b41_download *owner,
                        const struct b41_bootstrap_session *session,
                        const struct b41_bootstrap_query *query,
                        uint64_t now_ns, uint64_t deadline_ns);
int b41_download_next(struct b41_download *owner, uint64_t now_ns,
                       struct b41_download_action *action);
/* result is the immediate normalized write return, or negative errno.
 * EAGAIN means no bytes accepted; no replay of accepted bytes is permitted.
 */
int b41_download_written(struct b41_download *owner, uint64_t now_ns,
                          int result);
/* One actual integer ioctl25/26 result; never a pointer to fragment data. */
int b41_download_submitted(struct b41_download *owner, uint64_t now_ns,
                            int result);
/* Feed entire received chunks, not undersized DMA reads. A request accepts
 * exactly one ACK frame; duplicates/coalesced extra traffic are terminal errors,
 * never retained for a future request that has not yet been issued.
 */
int b41_download_received(struct b41_download *owner, uint64_t now_ns,
                           const uint8_t *bytes, size_t size);
/* Retain a real transport/lifecycle failure and erase private frame storage. */
int b41_download_abort(struct b41_download *owner, int error);

#endif
