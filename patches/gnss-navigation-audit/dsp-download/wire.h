/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MVCD_WIRE_H
#define B41_MVCD_WIRE_H

#include <stddef.h>
#include <stdint.h>

#define B41_MVCD_BOOTSTRAP_SIZE 106u
#define B41_MVCD_BOOTSTRAP_FRAME_SIZE 116u
#define B41_MVCD_ACK_PAYLOAD_MAX 1014u

enum b41_mvcd_result {
    B41_MVCD_OK = 0,
    B41_MVCD_ARGUMENT = -1,
    B41_MVCD_CAPACITY = -2,
    B41_MVCD_FORMAT = -3,
    B41_MVCD_CHECKSUM = -4,
    B41_MVCD_UNEXPECTED_ACK = -5
};

enum b41_mvcd_ack_kind {
    B41_MVCD_BOOTSTRAP_ACK = 0x31,
    B41_MVCD_FRAGMENT_ACK = 0x32
};

struct b41_mvcd_ack {
    uint16_t sequence;
    uint16_t bootstrap_auxiliary;
    uint16_t payload_size;
    uint8_t length_high_nibble;
    uint8_t has_bootstrap_auxiliary;
};

/* Payload must come from a separately validated MVCD producer. No defaults. */
int b41_mvcd_encode_bootstrap(const uint8_t *payload, size_t payload_size,
                              uint8_t *frame, size_t capacity, size_t *written);

/* Complete frame only. ACK is not proof of fragment submission or DSP WORKING. */
int b41_mvcd_decode_ack(const uint8_t *frame, size_t frame_size,
                        enum b41_mvcd_ack_kind expected_kind,
                        uint16_t expected_sequence, struct b41_mvcd_ack *ack);

#endif
