/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_PLATFORM_PROFILE_H
#define B41_PLATFORM_PROFILE_H

#include "../b41_first_config.h"

#define B41_PLATFORM_PROFILE_SIZE 52u

/* Logical NVM_GetFileDesc/read record, not the physical file's trailer.
 * Copy from the actual device's GPS record before constructing a session.
 * These fields do not provide chipset identity or private clock overrides.
 */
struct b41_platform_profile {
    uint32_t context_hz;
    uint16_t interval;
    uint8_t context_mode;
    uint8_t context_profile;
    unsigned selected_nv;
    unsigned calibration_override;
    uint8_t calibration[16];
};

/* configured_chip is the actual retained mnld chip-name producer, with its
 * terminating NUL in the supplied range. Never replace it with an ADIE name.
 * An empty logical record selects the proved default branch; absent/short
 * acquisition is an error, not an empty record. Outputs are atomic on error.
 */
int b41_platform_profile_decode(const uint8_t *record, size_t record_size,
                                const char *configured_chip, size_t chip_size,
                                struct b41_platform_profile *out);

/* Compose the real NV branch with the existing first-block builder. Preserve
 * live clock overrides and every unresolved XML/runtime/calibration gate.
 * Returns the existing partial-config status1, never engine readiness.
 */
int b41_first_config_build_nv(const struct b41_first_inputs *inputs,
                              const uint8_t *record, size_t record_size,
                              const char *configured_chip, size_t chip_size,
                              struct b41_first_config *out);
#endif
