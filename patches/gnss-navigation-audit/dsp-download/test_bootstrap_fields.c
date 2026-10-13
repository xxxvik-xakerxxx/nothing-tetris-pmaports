#include "bootstrap_fields.h"
#include "clock.h"
#include "wire.h"

#include <assert.h>
#include <fenv.h>
#include <string.h>

static const uint8_t name[] = "abcde";

static struct b41_mvcd_bootstrap_inputs inputs(void)
{
    struct b41_mvcd_bootstrap_inputs in = {0};

    in.context_mode_13 = 0xff;
    in.context_hz_18 = 26000000u;
    in.context_baud_1c = 921600u;
    in.context_chip_30 = UINT32_C(0xffff6725);
    in.context_lna_54 = 0x123456abu;
    in.word_7178b0 = 0x87654321u;
    in.feature_name = name;
    in.feature_name_size = sizeof(name);
    return in;
}

static void put32(uint8_t *p, uint32_t word)
{
    for (unsigned int i = 0; i < 4; ++i)
        p[i] = (uint8_t)(word >> (i * 8u));
}

/* Entirely synthetic raw words, never provisioning from a device. */
static void record(uint8_t bytes[8], uint32_t raw_word)
{
    uint32_t sum = 0;
    uint32_t key = 0xd9u;
    uint32_t state = 0;

    put32(bytes + 4, raw_word);
    for (unsigned int i = 0; i < 4; ++i) {
        uint32_t decoded = (uint32_t)bytes[4u + i] ^ key;

        sum += decoded;
        if (i == 0)
            state = decoded * 0xce6du + 0xaf55dbdcu;
        else if (i == 1)
            state = ((state + decoded) & 0xffffu) * 0xce6du + 0x58bfu;
        else
            state = (state + decoded) * 0xce6du + 0x58bfu;
        key = (state >> 8) & 255u;
    }
    put32(bytes, sum);
}

static void missing_unchanged(struct b41_mvcd_bootstrap_inputs *in, int expected)
{
    struct b41_mvcd_bootstrap_fields out, before;
    uint8_t payload[B41_MVCD_BOOTSTRAP_SIZE], original[B41_MVCD_BOOTSTRAP_SIZE];

    memset(&out, 0x5a, sizeof(out));
    memcpy(&before, &out, sizeof(before));
    memset(payload, 0xa5, sizeof(payload));
    memcpy(original, payload, sizeof(payload));
    assert(b41_mvcd_bootstrap_fields_build(in, &out) == expected);
    assert(memcmp(&out, &before, sizeof(out)) == 0);
    assert(b41_mvcd_bootstrap_fields_apply(in, payload, sizeof(payload)) == expected);
    assert(memcmp(payload, original, sizeof(payload)) == 0);
}

static void clock_inputs(void)
{
    struct b41_mvcd_bootstrap_inputs in = inputs();
    struct b41_mvcd_bootstrap_fields out;
    struct b41_mvcd_private_clock private;
    static const uint32_t raw[] = {0u, 1u, 2u, 3u, 4u, UINT32_MAX};
    static const uint32_t expected[] = {
        26000000u, 26000910u, 25999090u, 26000000u, 26000910u, 26000000u
    };

    in.context_mode_13 = 0xfe;
    missing_unchanged(&in, B41_MVCD_FIELDS_MISSING);
    in.private_clock = &private;
    record(private.frequency_1670, 19200000u);
    record(private.adjustment_1668, 1u);
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.effective_hz == 19200000u); /* Primary overrides adjustment. */
    private.adjustment_1668[0] ^= 1u;
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.effective_hz == 19200000u);
    record(private.frequency_1670, UINT32_MAX);
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.effective_hz == 26000000u); /* Helper sentinel preserves argument. */
    record(private.frequency_1670, 0u);
    missing_unchanged(&in, B41_MVCD_CLOCK_ARGUMENT);

    for (size_t i = 0; i < sizeof(raw) / sizeof(raw[0]); ++i) {
        record(private.frequency_1670, 19200000u);
        private.frequency_1670[0] ^= 1u;
        record(private.adjustment_1668, raw[i]);
        assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
        assert(out.effective_hz == expected[i]);
    }
    private.adjustment_1668[0] ^= 1u;
    in.context_hz_18 = 0;
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.effective_hz == 26000000u); /* Actual invalid records, not NULL. */
    in.context_hz_18 = 1;
    record(private.adjustment_1668, 1u);
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.effective_hz == 910u);
    record(private.adjustment_1668, 2u);
    missing_unchanged(&in, B41_MVCD_CLOCK_ARGUMENT); /* Saturates to zero. */
    in.context_hz_18 = UINT32_MAX - 1u;
    record(private.adjustment_1668, 1u);
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.effective_hz == UINT32_MAX - 1u); /* Saturated -1 then sentinel. */
    in.context_mode_13 = 0xff;
    in.context_hz_18 = 26000000u;
    in.private_clock = NULL;
    for (unsigned int selector = 0; selector <= 255u; ++selector) {
        for (unsigned int profile = 0; profile <= 255u; ++profile) {
            for (unsigned int configured = 0; configured < 3u; ++configured) {
                uint8_t expected_mode = (uint8_t)(selector <= 2u ? selector : 0u);

                in.clock_selector_717cb3 = (uint8_t)selector;
                in.profile_selector_717cb6 = (uint8_t)profile;
                in.context_profile_24 = (uint8_t)configured;
                if (profile == 1u || (profile >= 2u && configured == 1u))
                    expected_mode = (uint8_t)(expected_mode | 4u);
                assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
                assert(out.clock_mode == expected_mode);
                assert(out.synthesis_and_profile[8] == expected_mode);
                assert(out.synthesis_and_profile[9] == 0);
            }
        }
    }
}

static void board_fields(void)
{
    struct b41_mvcd_bootstrap_inputs in = inputs();
    struct b41_mvcd_bootstrap_fields out;
    static const uint32_t chips[] = {
        0xffff6570u, 0xffff6571u, 0xffff6572u, 0xffff6580u,
        0xffff6582u, 0xffff6592u, 0xfffe6735u,
        0xffff6771u, 0xffff6632u, 0xffff6725u, 0xffff6761u,
        0xffff6789u, 0xffff6724u, 0x6789u, UINT32_MAX
    };

    for (size_t index = 0; index < sizeof(chips) / sizeof(chips[0]); ++index) {
        for (unsigned int profile = 0; profile < 7u; ++profile) {
            for (unsigned int predicate = 0; predicate < 2u; ++predicate) {
                uint8_t first, second;

                in.context_chip_30 = chips[index];
                in.profile_selector_717cb6 = (uint8_t)profile;
                in.setting_717cb7 = 0xf5;
                in.feature_flags_717cb8 = 0x40;
                in.secondary_fd_6edeec = predicate != 0 ? 0 : -1;
                assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
                assert(out.synthesis_and_profile[28] ==
                       (index < 7u ? 5u : profile >= 5u || predicate != 0 ? 7u : 5u));
                assert(out.synthesis_and_profile[29] == 0);
                assert(out.effective_setting_717cb7 == (profile >= 5u ? 0x27u : 0xf5u));
                assert(out.board_tail[0] == 0x21 && out.board_tail[1] == 0x43);
                assert(out.board_tail[2] == (uint8_t)chips[index]);
                assert(out.board_tail[3] == (uint8_t)(chips[index] >> 8));
                if (index == 7u) {
                    first = 0xab;
                    second = profile < 4u ? 8u : 10u;
                } else if (index == 8u || profile < 4u) {
                    first = 0x48;
                    second = 0x49;
                } else {
                    first = 0xab;
                    second = 10;
                }
                assert(out.board_tail[4] == first && out.board_tail[5] == second);
                assert(out.board_tail[6] == (uint8_t)(profile == 4u && (index == 9u || index == 10u)));
                assert(out.board_tail[7] == 0 && out.board_tail[9] == 0);
                assert(out.board_tail[8] == (uint8_t)((predicate != 0 ? 3u : 1u) |
                       (index == 11u ? 4u : 0u)));
                assert(out.board_tail[10] == 0x4e && out.board_tail[11] == 0x4f);
                in.feature_flags_717cb8 = 0;
                assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
                assert(out.board_tail[8] == (predicate != 0 ? 3u : 1u));
            }
        }
    }
    in = inputs();
    for (unsigned int setting = 0; setting <= 255u; ++setting) {
        in.setting_717cb7 = (uint8_t)setting;
        assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
        assert(out.synthesis_and_profile[28] == ((setting & 15u) == 5u ? 7u : setting & 15u));
    }
    in.setting_717cb7 = 3;
    for (uint32_t shifted = 0; shifted <= 0x23u; ++shifted) {
        uint8_t expected = (uint8_t)(shifted <= 0x22u &&
            ((UINT64_C(0x400050007) >> shifted) & 1u) != 0 ? 5u : 3u);

        in.context_chip_30 = shifted - 0x9a90u;
        assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
        assert(out.synthesis_and_profile[28] == expected);
    }
}

static void bounds_and_offsets(void)
{
    struct b41_mvcd_bootstrap_inputs in = inputs();
    struct b41_mvcd_bootstrap_fields out;
    static const uint32_t bauds[] = {
        4800u, 9600u, 14400u, 19200u, 38400u, 57600u, 230400u, 460800u, 921600u,
        115200u, 0u, UINT32_MAX
    };
    static const uint8_t codes[] = {9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 0, 0};
    uint8_t payload[B41_MVCD_BOOTSTRAP_SIZE], before[B41_MVCD_BOOTSTRAP_SIZE];
    uint8_t feature[0x296];

    for (size_t i = 0; i < sizeof(bauds) / sizeof(bauds[0]); ++i) {
        in.context_baud_1c = bauds[i];
        assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
        assert(out.baud_and_parameters[0] == 0 && out.baud_and_parameters[1] == codes[i]);
    }
    in = inputs();
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.baud_and_parameters[2] == 0xc3 && out.baud_and_parameters[3] == 1);
    assert(out.baud_and_parameters[4] == 0xa5 && out.baud_and_parameters[5] == 2);
    memset(payload, 0xa5, sizeof(payload));
    assert(b41_mvcd_bootstrap_fields_apply(&in, payload, sizeof(payload)) == 0);
    assert(memcmp(payload + 4, out.baud_and_parameters, 6) == 0);
    assert(memcmp(payload + 30, out.synthesis_and_profile, 32) == 0);
    assert(memcmp(payload + 94, out.board_tail, 12) == 0);
    for (size_t i = 0; i < sizeof(payload); ++i)
        if (!((i >= 4u && i < 10u) || (i >= 30u && i < 62u) || i >= 94u))
            assert(payload[i] == 0xa5);
    memcpy(before, payload, sizeof(before));
    for (size_t size = 0; size < sizeof(payload); ++size)
        assert(b41_mvcd_bootstrap_fields_apply(&in, payload, size) == B41_MVCD_FIELDS_ARGUMENT);
    assert(b41_mvcd_bootstrap_fields_apply(&in, payload, 107) == B41_MVCD_FIELDS_ARGUMENT);
    assert(memcmp(before, payload, sizeof(payload)) == 0);
    assert(b41_mvcd_bootstrap_fields_apply(&in, NULL, 106) == B41_MVCD_FIELDS_ARGUMENT);
    assert(b41_mvcd_bootstrap_fields_build(NULL, &out) == B41_MVCD_FIELDS_ARGUMENT);
    assert(b41_mvcd_bootstrap_fields_build(&in, NULL) == B41_MVCD_FIELDS_ARGUMENT);
    in.feature_name = NULL;
    missing_unchanged(&in, B41_MVCD_FIELDS_MISSING);
    in.feature_name = feature;
    memset(feature, 'a', sizeof(feature));
    in.feature_name_size = 4;
    missing_unchanged(&in, B41_MVCD_FIELDS_MISSING);
    for (size_t length = 0; length < 6u; ++length) {
        feature[length] = 0;
        in.feature_name_size = length + 1u;
        assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
        assert(out.board_tail[8] == (length > 4u ? 3u : 1u));
        feature[length] = 'a';
    }
    in.feature_name_size = sizeof(feature);
    missing_unchanged(&in, B41_MVCD_FIELDS_FORMAT);
    feature[sizeof(feature) - 1u] = 0;
    assert(b41_mvcd_bootstrap_fields_build(&in, &out) == 0);
    assert(out.board_tail[8] == 3);
    in.context_hz_18 = 0;
    missing_unchanged(&in, B41_MVCD_CLOCK_ARGUMENT);
    in.context_hz_18 = 26000000u;
    assert(fesetround(FE_DOWNWARD) == 0);
    missing_unchanged(&in, B41_MVCD_CLOCK_ENVIRONMENT);
    assert(fesetround(FE_TONEAREST) == 0);
}

int main(void)
{
    assert(fesetround(FE_TONEAREST) == 0);
    clock_inputs();
    board_fields();
    bounds_and_offsets();
    return 0;
}
