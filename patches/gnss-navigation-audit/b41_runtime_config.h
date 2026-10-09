/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_RUNTIME_CONFIG_H
#define B41_RUNTIME_CONFIG_H
#include "b41_first_config.h"

enum b41_runtime_source {
    B41_RUNTIME_HOST_POLICY = 1u << 0,
    B41_RUNTIME_CHIP_POLICY = 1u << 1,
    B41_RUNTIME_NAV_POLICY = 1u << 2,
    B41_RUNTIME_TRACKING_POLICY = 1u << 3,
    B41_RUNTIME_MPE_POLICY = 1u << 4,
    B41_RUNTIME_FEATURE_POLICY = 1u << 5,
};
#define B41_RUNTIME_ALL 63u
#define B41_RUNTIME_PROVENANCE 0x90u
struct b41_runtime_sources {
    unsigned present;
    /* Snapshot from the legitimate producer owner, not user-selected defaults.
     * Names carry pinned source addresses; this helper never reads vendor globals.
     * Acquiring these sources remains the supervisor's explicit responsibility.
     */
    uint32_t host_mode_88794;
    uint32_t chip_id_de304, capabilities_de308, receiver_mode_88c1c;
    uint8_t secondary_de2fe; /*56ce0 is boolean(nonzero). */
    uint32_t nav_base_88c20, nav_override_88e10, nav_override_88e14;
    uint32_t tracking_de9d8;
    uint32_t mpe_requested_de228, mpe_probe_4eee0;
    uint8_t mpe_flag_88c4c;
    uint8_t feature_present_ddd84, feature_88c80;
};
struct b41_runtime_config {
    struct b41_first_config first;
    unsigned xml_get_verified;
    unsigned engine_contract_missing; /* Never cleared by field completeness. */
};
/* Applies all27 remaining first-config producer bytes. Mandatory source groups
 * must be explicitly present; zero-initializing a snapshot does not authorize it.
 * XML bytes must be the verified B4.1 asset. Returns1 partial STARTUP even if all
 * first bytes now have provenance; failure leaves out untouched. Frozen base's
 * global XML-apply/engine/transport/stop gates are not silently promoted.
 */
int b41_runtime_config_apply(const struct b41_first_config *base,
    const struct b41_runtime_sources *sources, const void *xml, size_t xml_size,
    struct b41_runtime_config *out);
#endif
