/* SPDX-License-Identifier: GPL-2.0-only */
#include "bootstrap_fields.h"
#include "clock.h"
#include "wire.h"

#include <string.h>

#if defined(__FAST_MATH__)
#error "B4.1 frequency adjustment requires strict floating point"
#endif

static uint32_t read32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void write16(uint8_t *p, uint32_t word)
{
    p[0] = (uint8_t)word;
    p[1] = (uint8_t)(word >> 8);
}

/* 662820/6628c0 validate a decoded byte sum but return the RAW stored word. */
static int private_word(const uint8_t record[8], uint32_t *word)
{
    uint32_t a = (uint32_t)record[4] ^ 0xd9u;
    uint32_t state = a * 0xce6du + 0xaf55dbdcu;
    uint32_t b = (uint32_t)record[5] ^ ((state >> 8) & 0xffu);
    uint32_t c, d;

    state = ((state + b) & 0xffffu) * 0xce6du + 0x58bfu;
    c = (uint32_t)record[6] ^ ((state >> 8) & 0xffu);
    state = (state + c) * 0xce6du + 0x58bfu;
    d = (uint32_t)record[7] ^ ((state >> 8) & 0xffu);
    if (read32(record) != a + b + c + d)
        return 0;
    *word = read32(record + 4);
    return 1;
}

static uint32_t effective_frequency(const struct b41_mvcd_bootstrap_inputs *in)
{
    uint32_t hz, adjustment;
    double adjusted;

    if (in->context_mode_13 != 0xfeu)
        return in->context_hz_18;
    if (!private_word(in->private_clock->frequency_1670, &hz)) {
        hz = in->context_hz_18 ? in->context_hz_18 : 26000000u;
        if (private_word(in->private_clock->adjustment_1668, &adjustment)) {
            adjustment %= 3u;
            if (adjustment == 1u || adjustment == 2u) {
                /* 552478..5524a0: exact binary64 +/-909.9999999999999,
                 * then AArch64 FCVTZU w8 (unsigned saturating truncation).
                 */
                adjusted = (double)hz + (adjustment == 1u ?
                    0x1.c6fffffffffffp+9 : -0x1.c6fffffffffffp+9);
                hz = adjusted <= 0.0 ? 0u : adjusted >= (double)UINT32_MAX ?
                     UINT32_MAX : (uint32_t)adjusted;
            }
        }
    }
    /* 4f0680/84: -1 from5523c0 preserves the original argument. */
    return hz == UINT32_MAX ? in->context_hz_18 : hz;
}

static uint8_t baud_code(uint32_t baud)
{
    switch (baud) {
    case 4800u: return 9;
    case 9600u: return 8;
    case 14400u: return 7;
    case 19200u: return 6;
    case 38400u: return 5;
    case 57600u: return 4;
    case 230400u: return 3;
    case 460800u: return 2;
    case 921600u: return 1;
    default: return 0;
    }
}

static int feature_predicate(const struct b41_mvcd_bootstrap_inputs *in,
                             uint8_t *predicate)
{
    size_t length = 0;

    if (in->feature_name == NULL)
        return B41_MVCD_FIELDS_MISSING;
    while (length < 0x296u) {
        if (length == in->feature_name_size)
            return B41_MVCD_FIELDS_MISSING;
        if (in->feature_name[length] == 0)
            break;
        ++length;
    }
    if (length == 0x296u)
        return B41_MVCD_FIELDS_FORMAT;
    *predicate = (uint8_t)(length > 4u && in->secondary_fd_6edeec != -1);
    return 0;
}

int b41_mvcd_bootstrap_fields_build(const struct b41_mvcd_bootstrap_inputs *in,
                                   struct b41_mvcd_bootstrap_fields *out)
{
    struct b41_mvcd_bootstrap_fields result = {0};
    struct b41_mvcd_clock_fields clock;
    uint8_t predicate, mode, profile;
    uint32_t chip, shifted;
    int status;

    if (in == NULL || out == NULL)
        return B41_MVCD_FIELDS_ARGUMENT;
    if (in->context_mode_13 == 0xfeu && in->private_clock == NULL)
        return B41_MVCD_FIELDS_MISSING;
    status = feature_predicate(in, &predicate);
    if (status != 0)
        return status;

    mode = (uint8_t)(in->clock_selector_717cb3 <= 2u ? in->clock_selector_717cb3 : 0u);
    profile = in->profile_selector_717cb6;
    if (profile == 1u || (profile >= 2u && in->context_profile_24 == 1u))
        mode = (uint8_t)(mode | 4u);
    result.effective_hz = effective_frequency(in);
    result.clock_mode = mode;
    status = b41_mvcd_clock_synthesize(result.effective_hz, mode, &clock);
    if (status != 0)
        return status;
    result.baud_and_parameters[1] = baud_code(in->context_baud_1c);
    write16(result.baud_and_parameters + 2, clock.parameter_a);
    write16(result.baud_and_parameters + 4, clock.parameter_b);
    memcpy(result.synthesis_and_profile, clock.synthesis, sizeof(clock.synthesis));

    result.effective_setting_717cb7 = profile >= 5u ? 0x27u : in->setting_717cb7;
    result.synthesis_and_profile[28] = (uint8_t)(profile >= 5u ? 7u :
        (in->setting_717cb7 & 0x0fu));
    if (result.synthesis_and_profile[28] == 5u && predicate != 0)
        result.synthesis_and_profile[28] = 7;
    chip = in->context_chip_30;
    shifted = chip + 0x9a90u;
    /* 4f2880..4f28b0 and the out-of-line4f3000 comparison. */
    if ((shifted <= 0x22u && ((UINT64_C(0x400050007) >> shifted) & 1u) != 0) ||
        chip == UINT32_C(0xfffe6735))
        result.synthesis_and_profile[28] = 5;
    result.synthesis_and_profile[30] = (uint8_t)(in->context_mode_13 == 0xfeu);

    write16(result.board_tail, in->word_7178b0);
    write16(result.board_tail + 2, chip);
    if (chip == UINT32_C(0xffff6771)) {
        result.board_tail[4] = (uint8_t)in->context_lna_54;
        result.board_tail[5] = profile < 4u ? 8u : 10u;
    } else if (chip == UINT32_C(0xffff6632) || profile < 4u) {
        result.board_tail[4] = 0x48;
        result.board_tail[5] = 0x49;
    } else {
        result.board_tail[4] = (uint8_t)in->context_lna_54;
        result.board_tail[5] = 10;
    }
    result.board_tail[6] = (uint8_t)(profile == 4u &&
        (chip == UINT32_C(0xffff6725) || chip == UINT32_C(0xffff6761)));
    result.board_tail[8] = predicate != 0 ? 3u : 1u;
    /* 5cc564(b2): table4ce055 ->5cc8e0 ->5cc8f0, chip == -0x9877. */
    if ((in->feature_flags_717cb8 & 0x40u) != 0 && chip == UINT32_C(0xffff6789))
        result.board_tail[8] = (uint8_t)(result.board_tail[8] | 4u);
    result.board_tail[10] = 0x4e;
    result.board_tail[11] = 0x4f;
    memcpy(out, &result, sizeof(result));
    return 0;
}

int b41_mvcd_bootstrap_fields_apply(const struct b41_mvcd_bootstrap_inputs *in,
                                   uint8_t *payload, size_t payload_size)
{
    struct b41_mvcd_bootstrap_fields fields;
    int status;

    if (payload == NULL || payload_size != B41_MVCD_BOOTSTRAP_SIZE)
        return B41_MVCD_FIELDS_ARGUMENT;
    status = b41_mvcd_bootstrap_fields_build(in, &fields);
    if (status != 0)
        return status;
    memcpy(payload + 4, fields.baud_and_parameters, sizeof(fields.baud_and_parameters));
    memcpy(payload + 30, fields.synthesis_and_profile, sizeof(fields.synthesis_and_profile));
    memcpy(payload + 94, fields.board_tail, sizeof(fields.board_tail));
    return 0;
}
