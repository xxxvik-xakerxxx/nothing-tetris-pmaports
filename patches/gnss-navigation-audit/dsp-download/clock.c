/* SPDX-License-Identifier: GPL-2.0-only */
#include "clock.h"

#include <fenv.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#ifdef __FAST_MATH__
#error "B4.1 clock synthesis requires strict floating point"
#endif

_Static_assert(CHAR_BIT == 8, "eight-bit wire bytes");
_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24 &&
               FLT_MAX_EXP == 128 && FLT_MIN_EXP == -125,
               "binary32 arithmetic");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 &&
               DBL_MAX_EXP == 1024 && DBL_MIN_EXP == -1021,
               "binary64 arithmetic");
_Static_assert(FLT_EVAL_METHOD == 0, "no excess evaluation precision");

static float binary32(uint32_t bits)
{
    float value;

    memcpy(&value, &bits, sizeof(value));
    return value;
}

static double binary64(uint64_t bits)
{
    double value;

    memcpy(&value, &bits, sizeof(value));
    return value;
}

int b41_mvcd_clock_round(double value, int64_t *out)
{
    int64_t lower;
    int64_t upper;
    volatile double midpoint;

    if (out == NULL)
        return B41_MVCD_CLOCK_ARGUMENT;
    if (fegetround() != FE_TONEAREST)
        return B41_MVCD_CLOCK_ENVIRONMENT;
    if (!isfinite(value) || fabs(value) >= 0x1p62)
        return B41_MVCD_CLOCK_RANGE;
    lower = (int64_t)floor(value);
    upper = (int64_t)ceil(value);
    midpoint = (double)(lower + upper);
    midpoint = midpoint * 0.5;
    *out = midpoint > value ? lower : upper;
    return B41_MVCD_CLOCK_OK;
}

static void store16(uint8_t *bytes, uint16_t value)
{
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
}

int b41_mvcd_clock_synthesize(uint32_t effective_hz, uint8_t mode,
                              struct b41_mvcd_clock_fields *out)
{
    static const uint16_t primary[5] = {138, 220, 307, 97, 151};
    static const uint16_t companion[5] = {121, 193, 265, 84, 131};
    struct b41_mvcd_clock_fields result = {0};
    uint16_t words[14] = {0};
    uint32_t coefficient = 0;
    uint32_t divider;
    uint32_t remainder;
    uint32_t packed_divider;
    unsigned int table = 0;
    int64_t fractional;
    int64_t primary_timer;
    int64_t companion_timer;
    int64_t generated;
    volatile float frequency32;
    volatile float scaled32;
    volatile double rate;
    volatile double fraction;
    volatile double timer;
    int error;

    if (out == NULL || effective_hz == 0 || mode > 7)
        return B41_MVCD_CLOCK_ARGUMENT;
    if (fegetround() != FE_TONEAREST)
        return B41_MVCD_CLOCK_ENVIRONMENT;
    frequency32 = (float)effective_hz;
    result.parameter_a = (uint16_t)(((uint64_t)effective_hz * UINT64_C(0x91a2b3c5)) >> 47);
    result.parameter_b = (uint16_t)(((uint64_t)effective_hz * UINT64_C(0x1b4e81b5)) >> 44);
    if (effective_hz == 16368000u) {
        table = 1;
        coefficient = 84;
        result.parameter_a = 288;
        result.parameter_b = 426;
    } else {
        if (frequency32 == binary32(UINT32_C(0x4bc65d40)))
            table = 2;
        else if (frequency32 == binary32(UINT32_C(0x4c189680)))
            table = 3;
        else if (effective_hz == 12000000u)
            table = 4;
        else if (frequency32 == binary32(UINT32_C(0x4b927c00)))
            table = 5;

        if (effective_hz == 26000000u)
            coefficient = 157;
        else if (effective_hz - 12000000u < 7000000u)
            coefficient = 100;
        else if (effective_hz - 19000000u < 7000000u)
            coefficient = 150;
        else if (effective_hz - 26000001u < 6999999u)
            coefficient = 200;
        else if (effective_hz - 33000000u <= 7000000u)
            coefficient = 250;
    }

    divider = 1571328000u / effective_hz;
    remainder = 1571328000u - divider * effective_hz;
    fraction = (double)remainder * 16777216.0;
    fraction = fraction / (double)effective_hz;
    error = b41_mvcd_clock_round(fraction, &fractional);
    if (error != B41_MVCD_CLOCK_OK)
        return error;
    packed_divider = (divider << 8) | (((uint32_t)fractional >> 16) & 255u);

    if (table != 0) {
        words[5] = primary[table - 1u];
        words[6] = companion[table - 1u];
    } else {
        scaled32 = binary32(UINT32_C(0x48b6e000)) * frequency32;
        scaled32 = scaled32 + scaled32;
        timer = (double)scaled32 / 100000000000.0;
        error = b41_mvcd_clock_round(timer, &generated);
        if (error != B41_MVCD_CLOCK_OK)
            return error;
        words[5] = (uint16_t)((uint32_t)generated + 15u);
        scaled32 = binary32(UINT32_C(0x489d8000)) * frequency32;
        scaled32 = scaled32 + scaled32;
        timer = (double)scaled32 / 100000000000.0;
        error = b41_mvcd_clock_round(timer, &generated);
        if (error != B41_MVCD_CLOCK_OK)
            return error;
        words[6] = (uint16_t)((uint32_t)generated + 15u);
    }
    rate = (double)effective_hz / 1000000.0;
    timer = binary64(UINT64_C(0x41905e353f7ced91)) / rate;
    error = b41_mvcd_clock_round(timer, &primary_timer);
    if (error != B41_MVCD_CLOCK_OK)
        return error;
    timer = binary64(UINT64_C(0x41888d4fdf3b645a)) / rate;
    error = b41_mvcd_clock_round(timer, &companion_timer);
    if (error != B41_MVCD_CLOCK_OK)
        return error;

    words[0] = (uint16_t)coefficient;
    words[1] = (uint16_t)packed_divider;
    words[2] = (uint16_t)fractional;
    words[4] = mode;
    words[7] = (uint16_t)((uint64_t)primary_timer >> 16);
    words[8] = (uint16_t)primary_timer;
    words[9] = (uint16_t)((uint64_t)companion_timer >> 16);
    words[10] = (uint16_t)companion_timer;
    words[11] = words[7];
    words[12] = words[8];
    words[13] = (uint16_t)((uint32_t)(((uint64_t)effective_hz * UINT64_C(0x10624dd3)) >> 38) - 1u);
    for (size_t index = 0; index < 14; ++index)
        store16(result.synthesis + 2u * index, words[index]);
    *out = result;
    return B41_MVCD_CLOCK_OK;
}
