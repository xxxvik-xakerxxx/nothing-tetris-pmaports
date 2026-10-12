#include "wire.h"

#include <assert.h>
#include <string.h>

/* Synthetic framing fixtures only; never ROM keys, calibration or DSO state. */
static size_t ack_frame(uint8_t *frame, uint8_t command, uint16_t sequence,
                        size_t payload_size, uint8_t flags)
{
    uint32_t checksum = 0;
    uint16_t length = (uint16_t)((payload_size + 4u) | ((unsigned int)flags << 12));

    memset(frame, 0, payload_size + 10u);
    frame[0] = 0xaa;
    frame[1] = 0xf0;
    frame[2] = (uint8_t)length;
    frame[3] = (uint8_t)(length >> 8);
    frame[4] = command;
    frame[5] = 0xfe;
    if (payload_size >= 2u) {
        frame[6] = (uint8_t)sequence;
        frame[7] = (uint8_t)(sequence >> 8);
    }
    if (payload_size >= 4u) {
        frame[8] = 0x34;
        frame[9] = 0x12;
    }
    for (size_t index = 2; index < payload_size + 6u; ++index)
        checksum += frame[index];
    frame[payload_size + 6u] = (uint8_t)checksum;
    frame[payload_size + 7u] = (uint8_t)(checksum >> 8);
    frame[payload_size + 8u] = 0xaa;
    frame[payload_size + 9u] = 0x0f;
    return payload_size + 10u;
}

static void request_tests(void)
{
    uint8_t payload[B41_MVCD_BOOTSTRAP_SIZE] = {0};
    uint8_t frame[B41_MVCD_BOOTSTRAP_FRAME_SIZE + 1u];
    uint8_t before[sizeof(frame)];
    size_t written = 999;

    payload[0] = 0x1a;
    payload[28] = 5;
    payload[104] = 0x4e;
    payload[105] = 0x4f;
    memset(frame, 0x5a, sizeof(frame));
    assert(b41_mvcd_encode_bootstrap(payload, sizeof(payload), frame, sizeof(frame), &written) == 0);
    assert(written == 116);
    assert(memcmp(frame, (const uint8_t[]){0xaa, 0xf0, 0x6e, 0, 8, 0xfe}, 6) == 0);
    assert(memcmp(frame + 6, payload, sizeof(payload)) == 0);
    assert(frame[112] == 0x30 && frame[113] == 2);
    assert(frame[114] == 0xaa && frame[115] == 0x0f && frame[116] == 0x5a);
    memcpy(before, frame, sizeof(frame));
    written = 999;
    for (size_t capacity = 0; capacity < 116; ++capacity)
        assert(b41_mvcd_encode_bootstrap(payload, sizeof(payload), frame, capacity, &written) == B41_MVCD_CAPACITY);
    assert(written == 999 && memcmp(before, frame, sizeof(frame)) == 0);
    assert(b41_mvcd_encode_bootstrap(payload, 105, frame, sizeof(frame), &written) == B41_MVCD_FORMAT);
    assert(b41_mvcd_encode_bootstrap(payload, 212, frame, sizeof(frame), &written) == B41_MVCD_FORMAT);
    payload[2] = 1;
    assert(b41_mvcd_encode_bootstrap(payload, sizeof(payload), frame, sizeof(frame), &written) == B41_MVCD_FORMAT);
    payload[2] = 0;
    assert(b41_mvcd_encode_bootstrap(frame, 106, frame, sizeof(frame), &written) == B41_MVCD_ARGUMENT);
    assert(b41_mvcd_encode_bootstrap(NULL, 106, frame, sizeof(frame), &written) == B41_MVCD_ARGUMENT);
    assert(b41_mvcd_encode_bootstrap(payload, 106, frame, sizeof(frame), NULL) == B41_MVCD_ARGUMENT);
    assert(written == 999 && memcmp(before, frame, sizeof(frame)) == 0);
}

static void ack_tests(void)
{
    uint8_t frame[B41_MVCD_ACK_PAYLOAD_MAX + 11u];
    struct b41_mvcd_ack ack = {0};
    struct b41_mvcd_ack before;
    size_t length;

    for (unsigned int flags = 0; flags < 16; ++flags) {
        length = ack_frame(frame, 0x31, 0, 4, (uint8_t)flags);
        assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) == 0);
        assert(ack.sequence == 0 && ack.bootstrap_auxiliary == 0x1234);
        assert(ack.has_bootstrap_auxiliary && ack.payload_size == 4);
        assert(ack.length_high_nibble == flags);
    }
    length = ack_frame(frame, 0x32, 0xffff, 2, 0);
    assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_FRAGMENT_ACK, 0xffff, &ack) == 0);
    assert(ack.sequence == 0xffff && ack.payload_size == 2);
    assert(!ack.has_bootstrap_auxiliary && ack.bootstrap_auxiliary == 0);
    memcpy(&before, &ack, sizeof(before));
    assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_FRAGMENT_ACK, 0, &ack) == B41_MVCD_UNEXPECTED_ACK);
    assert(memcmp(&before, &ack, sizeof(ack)) == 0);
    length = ack_frame(frame, 0x33, 0xffff, 2, 0);
    assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_FRAGMENT_ACK, 0xffff, &ack) == B41_MVCD_UNEXPECTED_ACK);

    for (size_t size = 0; size < 4; ++size) {
        length = ack_frame(frame, 0x31, 0, size, 0);
        assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) == B41_MVCD_FORMAT);
    }
    for (size_t size = 0; size < 2; ++size) {
        length = ack_frame(frame, 0x32, 0, size, 0);
        assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_FRAGMENT_ACK, 0, &ack) == B41_MVCD_FORMAT);
    }
    length = ack_frame(frame, 0x31, 0, B41_MVCD_ACK_PAYLOAD_MAX, 15);
    for (size_t index = 10; index < length - 4u; ++index)
        frame[index] = 0xff;
    {
        uint32_t sum = 0;

        for (size_t index = 2; index < length - 4u; ++index)
            sum += frame[index];
        assert(sum > 65535u);
        frame[length - 4u] = (uint8_t)sum;
        frame[length - 3u] = (uint8_t)(sum >> 8);
    }
    assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) == 0);
    for (size_t truncated = 0; truncated < length; ++truncated)
        assert(b41_mvcd_decode_ack(frame, truncated, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) != 0);
    assert(b41_mvcd_decode_ack(frame, length + 1, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) != 0);
    length = ack_frame(frame, 0x31, 0, B41_MVCD_ACK_PAYLOAD_MAX + 1u, 0);
    assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) == B41_MVCD_FORMAT);

    length = ack_frame(frame, 0x31, 0, 4, 0);
    for (size_t index = 0; index < length; ++index) {
        memcpy(&before, &ack, sizeof(before));
        frame[index] ^= 1;
        assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) != 0);
        assert(memcmp(&before, &ack, sizeof(ack)) == 0);
        frame[index] ^= 1;
    }
    assert(b41_mvcd_decode_ack(NULL, length, B41_MVCD_BOOTSTRAP_ACK, 0, &ack) == B41_MVCD_ARGUMENT);
    assert(b41_mvcd_decode_ack(frame, length, B41_MVCD_BOOTSTRAP_ACK, 0, NULL) == B41_MVCD_ARGUMENT);
    assert(b41_mvcd_decode_ack(frame, length, (enum b41_mvcd_ack_kind)0x33, 0, &ack) == B41_MVCD_ARGUMENT);
}

int main(void)
{
    request_tests();
    ack_tests();
    return 0;
}
