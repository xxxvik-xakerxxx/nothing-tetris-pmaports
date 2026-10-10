/* SPDX-License-Identifier: GPL-2.0-only */
#define _XOPEN_SOURCE 700
#include "b41_second_numeric.h"
#include "b41_runtime_config.h"
#include <errno.h>
#include <float.h>
#include <locale.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24,
    "pinned binary32 producer");
static void word(struct b41_second_config *out, unsigned offset, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) out->bytes[offset+i] = (uint8_t)(value >> (8*i));
    memset(out->provenance + offset, B41_RUNTIME_PROVENANCE, 4);
}
int b41_second_numeric_apply(const struct b41_second_config *base,
    const struct b41_second_numeric_sources *s, struct b41_second_config *out)
{
    struct b41_second_config result;
    char text[30] = {0};
    float value;
    uint32_t primary, secondary, floor;
    locale_t local, old;
    int count, saved;
    if (!base || !s || !out) return -EINVAL;
    memcpy(&value, &s->float_bits_de4bc, sizeof(value));
    if (!isfinite(value)) return -ERANGE;
    primary = s->requested_dfff4 < 0x3000000u ? s->requested_dfff4 : 0x3000000u;
    floor = primary * 12u;
    if (s->requested_dfff4 < 0x100000u) { primary = 0x1900000u; floor = 0x12c00000u; }
    secondary = s->requested_dfff8 > floor ? s->requested_dfff8 : floor;
    if (secondary > 0x20000000u) secondary = 0x20000000u;
    /* Source service starts in C locale. Use a private thread locale instead
     * of mutating pmOS/global locale or accepting decimal comma in this ABI.
     */
    local = newlocale(LC_NUMERIC_MASK, "C", (locale_t)0);
    if (!local) return -errno;
    old = uselocale(local);
    if (!old) { saved = errno; freelocale(local); return -saved; }
    count = snprintf(text, sizeof(text), "%.1f", (double)value);
    saved = count < 0 ? errno : 0;
    if (!uselocale(old)) {
        /* Do not free the still-active locale after failed restoration. */
        return -errno;
    }
    freelocale(local);
    if (count < 0) return saved ? -saved : -EIO;
    if ((size_t)count >= sizeof(text)) return -ENOSPC;
    result = *base;
    word(&result, 0x1c, primary); word(&result, 0x20, secondary);
    memcpy(result.bytes + 0x28, text, sizeof(text));
    memset(result.provenance + 0x28, B41_RUNTIME_PROVENANCE, sizeof(text));
    result.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        result.unresolved_bytes += result.provenance[i] == B41_SECOND_UNKNOWN;
    *out = result;
    return 1;
}
