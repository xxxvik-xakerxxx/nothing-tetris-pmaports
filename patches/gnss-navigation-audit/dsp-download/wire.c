/* SPDX-License-Identifier: GPL-2.0-only */
#include "wire.h"

#include <string.h>

_Static_assert(B41_MVCD_BOOTSTRAP_SIZE == 0x35u * 2u, "halfword count");
_Static_assert(B41_MVCD_BOOTSTRAP_FRAME_SIZE == B41_MVCD_BOOTSTRAP_SIZE + 10u,
               "six header bytes, checksum and trailer");
_Static_assert(B41_MVCD_ACK_PAYLOAD_MAX == 0x3f6u - 1u + 5u - 4u,
               "554770 unsigned length-minus-five guard");

static uint16_t read16(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8));
}

static void write16(uint8_t *bytes, uint16_t value)
{
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
}

static uint16_t sum_bytes(const uint8_t *bytes, size_t count)
{
    uint32_t sum = 0;

    for (size_t index = 0; index < count; ++index)
        sum += bytes[index];
    return (uint16_t)sum;
}

static int overlaps(const void *first, size_t first_size,
                    const void *second, size_t second_size)
{
    uintptr_t a = (uintptr_t)first;
    uintptr_t b = (uintptr_t)second;

    return a <= b ? b - a < first_size : a - b < second_size;
}

int b41_mvcd_encode_bootstrap(const uint8_t *payload, size_t payload_size,
                              uint8_t *frame, size_t capacity, size_t *written)
{
    if (payload == NULL || frame == NULL || written == NULL)
        return B41_MVCD_ARGUMENT;
    if (payload_size != B41_MVCD_BOOTSTRAP_SIZE)
        return B41_MVCD_FORMAT;
    if (capacity < B41_MVCD_BOOTSTRAP_FRAME_SIZE)
        return B41_MVCD_CAPACITY;
    if (overlaps(payload, payload_size, frame, B41_MVCD_BOOTSTRAP_FRAME_SIZE) ||
        overlaps(written, sizeof(*written), payload, payload_size) ||
        overlaps(written, sizeof(*written), frame, B41_MVCD_BOOTSTRAP_FRAME_SIZE))
        return B41_MVCD_ARGUMENT;
    if (read16(payload) != 0x1au || read16(payload + 2) != 0)
        return B41_MVCD_FORMAT;

    /* The pointer in the vendor stack descriptor is not part of this frame. */
    frame[0] = 0xaa;
    frame[1] = 0xf0;
    write16(frame + 2, B41_MVCD_BOOTSTRAP_SIZE + 4u);
    frame[4] = 8;
    frame[5] = 0xfe;
    memcpy(frame + 6, payload, payload_size);
    write16(frame + 6 + payload_size, sum_bytes(frame + 2, payload_size + 4u));
    frame[8 + payload_size] = 0xaa;
    frame[9 + payload_size] = 0x0f;
    *written = B41_MVCD_BOOTSTRAP_FRAME_SIZE;
    return B41_MVCD_OK;
}

int b41_mvcd_decode_ack(const uint8_t *frame, size_t frame_size,
                        enum b41_mvcd_ack_kind expected_kind,
                        uint16_t expected_sequence, struct b41_mvcd_ack *ack)
{
    struct b41_mvcd_ack decoded = {0};
    uint16_t encoded_length;
    size_t payload_size;
    size_t minimum;

    if (frame == NULL || ack == NULL ||
        (expected_kind != B41_MVCD_BOOTSTRAP_ACK &&
         expected_kind != B41_MVCD_FRAGMENT_ACK))
        return B41_MVCD_ARGUMENT;
    if (frame_size < 10u || frame_size > B41_MVCD_ACK_PAYLOAD_MAX + 10u)
        return B41_MVCD_FORMAT;
    if (overlaps(frame, frame_size, ack, sizeof(*ack)))
        return B41_MVCD_ARGUMENT;
    if (frame[0] != 0xaa || frame[1] != 0xf0 || frame[5] != 0xfe)
        return B41_MVCD_FORMAT;
    encoded_length = read16(frame + 2);
    if ((encoded_length & 0xfffu) < 4u)
        return B41_MVCD_FORMAT;
    payload_size = (encoded_length & 0xfffu) - 4u;
    if (payload_size > B41_MVCD_ACK_PAYLOAD_MAX || frame_size != payload_size + 10u)
        return B41_MVCD_FORMAT;
    minimum = expected_kind == B41_MVCD_BOOTSTRAP_ACK ? 4u : 2u;
    if (payload_size < minimum || frame[frame_size - 2u] != 0xaa ||
        frame[frame_size - 1u] != 0x0f)
        return B41_MVCD_FORMAT;
    if (read16(frame + 6u + payload_size) != sum_bytes(frame + 2, payload_size + 4u))
        return B41_MVCD_CHECKSUM;
    if (frame[4] != (uint8_t)expected_kind || read16(frame + 6) != expected_sequence)
        return B41_MVCD_UNEXPECTED_ACK;

    decoded.sequence = read16(frame + 6);
    decoded.payload_size = (uint16_t)payload_size;
    decoded.length_high_nibble = (uint8_t)(encoded_length >> 12);
    if (expected_kind == B41_MVCD_BOOTSTRAP_ACK) {
        decoded.bootstrap_auxiliary = read16(frame + 8);
        decoded.has_bootstrap_auxiliary = 1;
    }
    *ack = decoded;
    return B41_MVCD_OK;
}
