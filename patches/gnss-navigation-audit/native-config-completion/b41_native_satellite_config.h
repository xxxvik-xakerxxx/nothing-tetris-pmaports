/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_NATIVE_SATELLITE_CONFIG_H
#define B41_NATIVE_SATELLITE_CONFIG_H
#include "../b41_first_config.h"

/* Order follows the B4.1 request, not numerical mask-bit order. The four
 * extension meanings have not been recovered; callers must opt in explicitly.
 */
enum b41_satellite_option {
    B41_SAT_GPS, B41_SAT_GLONASS, B41_SAT_BEIDOU, B41_SAT_GALILEO,
    B41_SAT_ASSISTED_GLONASS, B41_SAT_ASSISTED_GPS,
    B41_SAT_ASSISTED_BEIDOU, B41_SAT_ASSISTED_GALILEO,
    B41_SAT_EXTENSION_10, B41_SAT_EXTENSION_11,
    B41_SAT_EXTENSION_12, B41_SAT_EXTENSION_13, B41_SAT_COUNT
};
struct b41_native_satellite_settings {
    /* Every member must be explicitly chosen as 0 or 1. No property lookup,
     * capability inference, AGPS connection, or assistance availability claim.
     */
    uint8_t enabled[B41_SAT_COUNT];
};
#define B41_NATIVE_SATELLITE_PROVENANCE 0x81u

/* Pure, pre-registration copy. Corrects the old CONSTANT zero tag at58..59.
 * Other already-resolved conflicting values fail closed. In-place supported.
 * Return1 remains partial. No missing-input or lifecycle gate is cleared.
 */
int b41_native_satellite_config_apply(const struct b41_first_config *base,
    const struct b41_native_satellite_settings *settings,
    struct b41_first_config *out);

enum b41_native_start_policy {
    B41_NATIVE_NORMAL_START,
    B41_NATIVE_FACTORY_START
};
/* Explicit normal-start choice maps the factory selector0 to first+5a=1.
 * Factory side effects are unsupported. This does not select hot/cold restart.
 */
int b41_native_start_config_apply(const struct b41_first_config *base,
    enum b41_native_start_policy policy, struct b41_first_config *out);
#endif
