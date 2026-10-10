/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_NV_CALIBRATION_H
#define B41_NV_CALIBRATION_H
#include "b41_first_config.h"
#include <sys/stat.h>
struct b41_nv_calibration {
    uint8_t bytes[16];
    struct stat identity;
};
struct b41_nv_producer {
    /* Actual producer snapshots, not readiness booleans. Nonzero de3bc takes
     * Android properties; nonzero de22c takes the selected platform profile.
     */
    uint8_t property_branch_de3bc;
    uint32_t platform_profile_de22c;
};
/* Exact pinned MT6878 ML4A record:16 bytes at160. CALIBRAT directory fd comes
 * from the legitimate SAME UNIT read-only NV mount/export; not public firmware
 * or another handset. Provider owns root fd, no shared mutable file aliases.
 * No device/partition access, writes, fallback, retries or Android properties.
 * Reads only relative ML4A_000 with O_NOFOLLOW; requires a stable regular file.
 * chip_id must be the actual hardware query result, not a selected profile.
 * Output unchanged on all failures, including short read or close failure.
 */
int b41_nv_calibration_read(int calibrat_dir, uint32_t chip_id,
    struct b41_nv_calibration *out);
/* Real file reader -> frozen typed first constructor. Adds CALIBRATION only
 * after a complete stable read. Other semantic inputs are NOT supplied or
 * inferred here. Explicit default platform profile remains required to copy
 * the record; alternate/modern-property profiles remain refused/unresolved.
 * Returns frozen partial status, never complete engine readiness. Synchronous
 * byte copy only; no reference to stack record survives this call.
 */
int b41_first_config_from_nv(int calibrat_dir, uint32_t chip_id,
    const struct b41_nv_producer *producer,
    const struct b41_first_inputs *inputs, struct b41_first_config *out);
#endif
