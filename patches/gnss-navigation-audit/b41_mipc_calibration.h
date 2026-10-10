/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MIPC_CALIBRATION_H
#define B41_MIPC_CALIBRATION_H
#include "b41_capability_branch.h"
#include "b41_first_config.h"

struct b41_mipc_calibration {
    uint32_t c0, c1, temperature;
};

/* Calls the linked OEM MIPC API, not an invented tty wire protocol.
 * branch must come from b41_capability_branch_read using actual identity.
 * Dedicated process must be sole MIPC owner (SETCOM/init/deinit are global).
 * Link only the matching, independently pinned OEM libmipc.so. The selected
 * stock-assets bundle does not yet contain it; its tag storage/size guarantees
 * and raw wire format still require library audit before live use. This code
 * preserves the OEM NULL third argument; it does not invent a length API.
 * The parent's bounded worker/reap lifecycle must contain a stuck OEM call.
 * Never invokes libMNL, publishes properties, or marks engine readiness.
 * All four response tags are required; out is unchanged on any failure.
 */
int b41_mipc_calibration_collect(const struct b41_capability_branch *branch,
    struct b41_mipc_calibration *out);

/* Copies ONLY the proven two calibration words into a default-profile first
 * packet. Tail bytes 0x44..0x4b remain untouched and CALIBRATION stays missing
 * even if independent provenance exists (this bridge never clears gates).
 * Temperature lives
 * at mnld de4a0, not in that16-byte block. Returns1 (partial), never readiness.
 */
int b41_mipc_calibration_first(const struct b41_mipc_calibration *record,
    const struct b41_first_config *partial, struct b41_first_config *out);
#endif
