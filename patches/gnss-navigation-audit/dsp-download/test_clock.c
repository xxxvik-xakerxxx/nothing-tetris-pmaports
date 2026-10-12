#include "clock.h"

#include <assert.h>
#include <fenv.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

struct vector {
    uint32_t hz;
    uint16_t a;
    uint16_t b;
    uint16_t words[14];
};

/* Public arithmetic vectors, not device measurements or calibration. */
static const struct vector vectors[] = {
    {1u, 0, 0, {0, 0, 0, 0, 0, 15, 15, 24576, 0, 18432, 0, 24576, 0, 65535}},
    {12000000u, 208, 312, {100, 33521, 43516, 0, 0, 97, 84, 87, 19399, 65, 30933, 87, 19399, 11999}},
    {16368000u, 288, 426, {84, 24576, 0, 0, 0, 138, 121, 64, 0, 48, 0, 64, 0, 16367}},
    {19200000u, 333, 500, {150, 20951, 2621, 0, 0, 151, 131, 54, 36700, 40, 60293, 54, 36700, 19199}},
    {20000000u, 347, 520, {150, 20112, 65431, 0, 0, 165, 144, 52, 24746, 39, 18560, 52, 24746, 19999}},
    {26000000u, 451, 677, {157, 15471, 35208, 0, 0, 220, 193, 40, 19036, 30, 14277, 40, 19036, 25999}},
    {26000001u, 451, 677, {200, 15471, 35169, 0, 0, 220, 193, 40, 19036, 30, 14277, 40, 19036, 25999}},
    {33000000u, 572, 859, {250, 12189, 45613, 0, 0, 262, 228, 31, 48759, 23, 52953, 31, 48759, 32999}},
    {35999999u, 624, 937, {250, 11173, 58216, 0, 0, 285, 247, 29, 6466, 21, 54002, 29, 6466, 35998}},
    {40000000u, 694, 1041, {250, 10056, 32716, 0, 0, 307, 265, 26, 12373, 19, 42048, 26, 12373, 39999}},
    {40000001u, 694, 1041, {0, 10056, 32699, 0, 0, 307, 265, 26, 12373, 19, 42048, 26, 12373, 39999}},
    {52000000u, 902, 1354, {0, 7735, 50372, 0, 0, 405, 350, 20, 9518, 15, 7138, 20, 9518, 51999}},
    {UINT32_MAX, 9029, 46312, {0, 93, 43152, 0, 0, 32187, 27723, 0, 15984, 0, 11988, 0, 15984, 35126}},
};

static uint16_t read16(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8));
}

int main(void)
{
    struct b41_mvcd_clock_fields output;
    struct b41_mvcd_clock_fields before;
    int64_t rounded;
    static const double halves[] = {-2.5, -1.5, -0.5, 0.5, 1.5, 2.5};

    assert(fesetround(FE_TONEAREST) == 0);
    for (size_t index = 0; index < sizeof(halves) / sizeof(halves[0]); ++index) {
        assert(b41_mvcd_clock_round(halves[index], &rounded) == 0);
        assert(rounded == (int64_t)index - 2);
    }
    assert(b41_mvcd_clock_round(nextafter(0.5, 0.0), &rounded) == 0 && rounded == 0);
    assert(b41_mvcd_clock_round(nextafter(0.5, 1.0), &rounded) == 0 && rounded == 1);
    rounded = 99;
    assert(b41_mvcd_clock_round(NAN, &rounded) == B41_MVCD_CLOCK_RANGE && rounded == 99);
    assert(b41_mvcd_clock_round(INFINITY, &rounded) == B41_MVCD_CLOCK_RANGE && rounded == 99);
    assert(b41_mvcd_clock_round(0x1p62, &rounded) == B41_MVCD_CLOCK_RANGE && rounded == 99);
    assert(b41_mvcd_clock_round(-0x1p62, &rounded) == B41_MVCD_CLOCK_RANGE && rounded == 99);

    for (size_t index = 0; index < sizeof(vectors) / sizeof(vectors[0]); ++index) {
        for (uint8_t mode = 0; mode <= 7; ++mode) {
            assert(b41_mvcd_clock_synthesize(vectors[index].hz, mode, &output) == 0);
            assert(output.parameter_a == vectors[index].a);
            assert(output.parameter_b == vectors[index].b);
            for (size_t word = 0; word < 14; ++word)
                assert(read16(output.synthesis + 2u * word) ==
                       (word == 4 ? mode : vectors[index].words[word]));
        }
    }
    memset(&output, 0x5a, sizeof(output));
    memcpy(&before, &output, sizeof(before));
    assert(b41_mvcd_clock_synthesize(0, 0, &output) == B41_MVCD_CLOCK_ARGUMENT);
    assert(b41_mvcd_clock_synthesize(26000000u, 8, &output) == B41_MVCD_CLOCK_ARGUMENT);
    assert(memcmp(&before, &output, sizeof(output)) == 0);
    assert(b41_mvcd_clock_synthesize(26000000u, 0, NULL) == B41_MVCD_CLOCK_ARGUMENT);
    assert(b41_mvcd_clock_round(0.5, NULL) == B41_MVCD_CLOCK_ARGUMENT);
    assert(fesetround(FE_DOWNWARD) == 0);
    assert(b41_mvcd_clock_synthesize(26000000u, 0, &output) == B41_MVCD_CLOCK_ENVIRONMENT);
    rounded = 99;
    assert(b41_mvcd_clock_round(0.5, &rounded) == B41_MVCD_CLOCK_ENVIRONMENT && rounded == 99);
    assert(memcmp(&before, &output, sizeof(output)) == 0);
    assert(fesetround(FE_TONEAREST) == 0);
    return 0;
}
