/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_native_satellite_config.h"
#include <errno.h>

int b41_native_satellite_config_apply(const struct b41_first_config *base,
    const struct b41_native_satellite_settings *settings,
    struct b41_first_config *out)
{
    static const uint8_t bits[B41_SAT_COUNT] = {
        0, 1, 2, 3, 4, 5, 6, 7, 9, 8, 11, 10
    };
    struct b41_first_config result;
    uint16_t mask = 0;
    if (!base || !settings || !out) return -EINVAL;
    for (unsigned i = 0; i < B41_SAT_COUNT; ++i) {
        if (settings->enabled[i] > 1) return -EINVAL;
        mask |= (uint16_t)((unsigned)settings->enabled[i] << bits[i]);
    }
    /* The inherited constructor tags58..5a CONSTANT after its initial zero.
     * Only the two proven overwritten mask bytes are repaired here.
     */
    for (unsigned i = 0; i < 2; ++i) {
        unsigned offset = 0x58 + i;
        uint8_t value = (uint8_t)(mask >> (8 * i));
        if (base->provenance[offset] == B41_FIRST_CONSTANT) {
            if (base->bytes[offset]) return -ESTALE;
        } else if (base->provenance[offset] && base->bytes[offset] != value) {
            return -ESTALE;
        }
    }
    result = *base;
    for (unsigned i = 0; i < 2; ++i) {
        result.bytes[0x58 + i] = (uint8_t)(mask >> (8 * i));
        result.provenance[0x58 + i] = B41_NATIVE_SATELLITE_PROVENANCE;
    }
    /* The same startup also overwrites5a from an independent selector.
     * Revoke the inherited zero receipt; do not guess that policy's value.
     */
    if (result.provenance[0x5a] == B41_FIRST_CONSTANT) {
        if (result.bytes[0x5a]) return -ESTALE;
        result.provenance[0x5a] = B41_FIRST_UNKNOWN;
    }
    result.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i)
        result.unresolved_bytes += result.provenance[i] == B41_FIRST_UNKNOWN;
    *out = result;
    return 1;
}

int b41_native_start_config_apply(const struct b41_first_config *base,
    enum b41_native_start_policy policy, struct b41_first_config *out)
{
    struct b41_first_config result;
    if (!base || !out) return -EINVAL;
    if (policy == B41_NATIVE_FACTORY_START) return -EOPNOTSUPP;
    if (policy != B41_NATIVE_NORMAL_START) return -EINVAL;
    if (base->provenance[0x5a] == B41_FIRST_CONSTANT) {
        if (base->bytes[0x5a]) return -ESTALE;
    } else if (base->provenance[0x5a] && base->bytes[0x5a] != 1) {
        return -ESTALE;
    }
    result = *base;
    result.bytes[0x5a] = 1; /* mnld63544/6354c: factory selector != 1. */
    result.provenance[0x5a] = B41_NATIVE_SATELLITE_PROVENANCE;
    result.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i)
        result.unresolved_bytes += result.provenance[i] == B41_FIRST_UNKNOWN;
    *out = result;
    return 1;
}
