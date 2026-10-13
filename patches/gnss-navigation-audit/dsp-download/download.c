/* SPDX-License-Identifier: GPL-2.0-only */
#include "download.h"

#include <errno.h>
#include <string.h>

static void erase(void *storage, size_t size)
{
    volatile uint8_t *bytes = storage;

    while (size-- != 0)
        *bytes++ = 0;
}

static int overlaps(const void *a, size_t a_size, const void *b, size_t b_size)
{
    uintptr_t first = (uintptr_t)a;
    uintptr_t second = (uintptr_t)b;

    return first <= second ? second - first < a_size : first - second < b_size;
}

int b41_download_abort(struct b41_download *owner, int error)
{
    if (owner == NULL)
        return -EINVAL;
    if (owner->stage == B41_DOWNLOAD_FAILED)
        return owner->first_error;
    owner->first_error = error < 0 ? error : -EPROTO;
    owner->failure_stage = owner->stage;
    owner->stage = B41_DOWNLOAD_FAILED;
    erase(owner->tx, sizeof(owner->tx));
    erase(owner->rx, sizeof(owner->rx));
    owner->tx_size = owner->tx_offset = owner->rx_size = 0;
    return owner->first_error;
}

static int check(struct b41_download *owner, uint64_t now_ns)
{
    if (owner == NULL)
        return -EINVAL;
    if (owner->stage == B41_DOWNLOAD_FAILED)
        return owner->first_error;
    if (owner->stage == B41_DOWNLOAD_NEW)
        return -EINVAL;
    if (owner->session == NULL || owner->session->gps0_fd != owner->gps0_fd ||
        owner->session->selectors.secure_download_7178b8_33e !=
            owner->selectors.secure_download_7178b8_33e ||
        owner->session->selectors.dsp_selector_717cb0 != owner->selectors.dsp_selector_717cb0)
        return b41_download_abort(owner, -ESTALE);
    if (now_ns < owner->last_now_ns)
        return b41_download_abort(owner, -EINVAL);
    owner->last_now_ns = now_ns;
    if (owner->stage != B41_DOWNLOAD_ACKS_COMPLETE && now_ns >= owner->deadline_ns)
        return b41_download_abort(owner, -ETIMEDOUT);
    return 0;
}

int b41_download_begin(struct b41_download *owner,
                        const struct b41_bootstrap_session *session,
                        const struct b41_bootstrap_query *query,
                        uint64_t now_ns, uint64_t deadline_ns)
{
    uint8_t frame[B41_MVCD_BOOTSTRAP_FRAME_SIZE];
    size_t size = 0;
    int status;

    if (owner == NULL)
        return -EINVAL;
    if (owner->stage != B41_DOWNLOAD_NEW)
        return owner->stage == B41_DOWNLOAD_FAILED ? owner->first_error : -EALREADY;
    if (session == NULL || query == NULL || session->fields == NULL || query->info == NULL)
        return b41_download_abort(owner, -EINVAL);
    /* The assembler checks its temporary frame; also exclude aliases with the
     * retained owner before storing the completed private request there.
     */
    if (overlaps(owner, sizeof(*owner), session, sizeof(*session)) ||
        overlaps(owner, sizeof(*owner), query, sizeof(*query)) ||
        overlaps(owner, sizeof(*owner), query->info, sizeof(*query->info)) ||
        overlaps(owner, sizeof(*owner), session->fields, sizeof(*session->fields)) ||
        (session->fields->feature_name != NULL &&
         overlaps(owner, sizeof(*owner), session->fields->feature_name,
                    session->fields->feature_name_size < 0x296u ?
                    session->fields->feature_name_size : 0x296u)) ||
        (session->fields->private_clock != NULL &&
         overlaps(owner, sizeof(*owner), session->fields->private_clock,
                    sizeof(*session->fields->private_clock))))
        return -EINVAL; /* Do not erase aliased input storage. */
    if (deadline_ns <= now_ns)
        return b41_download_abort(owner, -ETIMEDOUT);
    status = b41_bootstrap_frame_build(session, query, frame, sizeof(frame), &size);
    if (status != 0) {
        erase(frame, sizeof(frame));
        return b41_download_abort(owner, status);
    }
    owner->session = session;
    owner->gps0_fd = session->gps0_fd;
    owner->selectors = session->selectors;
    owner->fragment_count = query->info->frag_num;
    owner->fragment_sequence = 1;
    owner->deadline_ns = deadline_ns;
    owner->last_now_ns = now_ns;
    memcpy(owner->tx, frame, size);
    owner->tx_size = size;
    owner->stage = B41_DOWNLOAD_BOOTSTRAP_TX;
    erase(frame, sizeof(frame));
    return 0;
}

int b41_download_next(struct b41_download *owner, uint64_t now_ns,
                       struct b41_download_action *action)
{
    struct b41_download_action next = {0};
    struct b41_bootstrap_route route;
    int status = check(owner, now_ns);

    if (status != 0)
        return status;
    if (action == NULL || overlaps(owner, sizeof(*owner), action, sizeof(*action)))
        return b41_download_abort(owner, -EINVAL);
    next.gps0_fd = owner->gps0_fd;
    next.deadline_ns = owner->deadline_ns;
    switch (owner->stage) {
    case B41_DOWNLOAD_BOOTSTRAP_TX:
        next.kind = B41_DOWNLOAD_WRITE;
        next.bytes = owner->tx + owner->tx_offset;
        next.size = owner->tx_size - owner->tx_offset;
        break;
    case B41_DOWNLOAD_BOOTSTRAP_RX:
    case B41_DOWNLOAD_FRAGMENT_RX:
        next.kind = B41_DOWNLOAD_READ;
        break;
    case B41_DOWNLOAD_FRAGMENT_IOCTL:
        status = b41_bootstrap_route_select(&owner->selectors, &route);
        if (status != 0)
            return b41_download_abort(owner, status);
        next.kind = B41_DOWNLOAD_SUBMIT_FRAGMENT;
        next.command = route.fragment_ioctl;
        next.argument = owner->fragment_sequence - 1u;
        break;
    case B41_DOWNLOAD_ACKS_COMPLETE:
        next.kind = B41_DOWNLOAD_DONE;
        break;
    default:
        return b41_download_abort(owner, -EPROTO);
    }
    *action = next;
    return 0;
}

int b41_download_written(struct b41_download *owner, uint64_t now_ns, int result)
{
    int status = check(owner, now_ns);

    if (status != 0)
        return status;
    if (owner->stage != B41_DOWNLOAD_BOOTSTRAP_TX)
        return b41_download_abort(owner, -EPROTO);
    if (result == -EAGAIN)
        return 0;
    if (result < 0)
        return b41_download_abort(owner, result);
    if (result == 0 || (size_t)result > owner->tx_size - owner->tx_offset)
        return b41_download_abort(owner, -EIO);
    owner->tx_offset += (size_t)result;
    if (owner->tx_offset == owner->tx_size) {
        erase(owner->tx, sizeof(owner->tx));
        owner->tx_offset = owner->tx_size = 0;
        owner->stage = B41_DOWNLOAD_BOOTSTRAP_RX;
    }
    return 0;
}

int b41_download_submitted(struct b41_download *owner, uint64_t now_ns, int result)
{
    int status = check(owner, now_ns);

    if (status != 0)
        return status;
    if (owner->stage != B41_DOWNLOAD_FRAGMENT_IOCTL)
        return b41_download_abort(owner, -EPROTO);
    if (result != 0)
        return b41_download_abort(owner, result);
    owner->stage = B41_DOWNLOAD_FRAGMENT_RX;
    return 0;
}

int b41_download_received(struct b41_download *owner, uint64_t now_ns,
                           const uint8_t *bytes, size_t size)
{
    struct b41_mvcd_ack ack;
    size_t frame_size;
    enum b41_mvcd_ack_kind kind;
    uint16_t sequence;
    int status = check(owner, now_ns);

    if (status != 0)
        return status;
    if (owner->stage != B41_DOWNLOAD_BOOTSTRAP_RX && owner->stage != B41_DOWNLOAD_FRAGMENT_RX)
        return b41_download_abort(owner, -EPROTO);
    if (bytes == NULL || size == 0 || size > sizeof(owner->rx) - owner->rx_size ||
        overlaps(owner, sizeof(*owner), bytes, size))
        return b41_download_abort(owner, -EMSGSIZE);
    memcpy(owner->rx + owner->rx_size, bytes, size);
    owner->rx_size += size;
    if (owner->rx_size < 6u)
        return 0;
    if (owner->rx[0] != 0xaa || owner->rx[1] != 0xf0 || owner->rx[5] != 0xfe)
        return b41_download_abort(owner, -EPROTO);
    frame_size = ((size_t)owner->rx[2] | ((size_t)(owner->rx[3] & 15u) << 8)) + 6u;
    if (frame_size < 10u || frame_size > sizeof(owner->rx) || owner->rx_size > frame_size)
        return b41_download_abort(owner, -EPROTO);
    if (owner->rx_size < frame_size)
        return 0;
    kind = owner->stage == B41_DOWNLOAD_BOOTSTRAP_RX ? B41_MVCD_BOOTSTRAP_ACK : B41_MVCD_FRAGMENT_ACK;
    sequence = owner->stage == B41_DOWNLOAD_BOOTSTRAP_RX ? 0 : (uint16_t)owner->fragment_sequence;
    status = b41_mvcd_decode_ack(owner->rx, frame_size, kind, sequence, &ack);
    erase(owner->rx, sizeof(owner->rx));
    owner->rx_size = 0;
    if (status != 0)
        return b41_download_abort(owner, status);
    if (owner->stage == B41_DOWNLOAD_FRAGMENT_RX) {
        ++owner->matched_fragments;
        ++owner->fragment_sequence;
        if (owner->matched_fragments == owner->fragment_count) {
            owner->stage = B41_DOWNLOAD_ACKS_COMPLETE;
            return 0;
        }
    }
    /* Secure L1 bypasses the embedded command0c writer. The sole trigger is
     * ioctl25/26 with sequence-1; never fabricate a per-fragment wire packet.
     */
    owner->stage = B41_DOWNLOAD_FRAGMENT_IOCTL;
    return 0;
}
