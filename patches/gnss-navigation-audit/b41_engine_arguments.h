/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_ENGINE_ARGUMENTS_H
#define B41_ENGINE_ARGUMENTS_H
#include "b41_startup_bundle.h"
/* Actual192-byte registration region read at52f9d0. Unlike known_callbacks,
 * this has the vendor's24 slots. Unknown optional slots are NULL words only;
 * no guessed prototypes or successful stub functions are installed there.
 */
struct b41_engine_callback_table {
    b41_slot0_notify_fn notify;
    b41_slot2_output_fn app_output;
    b41_slot2_output_fn output;
    b41_slot3_frame_sync_sleep_fn frame_sleep;
    b41_slot4_frame_sync_network_fn frame_network;
    b41_slot5_frame_measurement_fn frame_measurement;
    b41_slot6_agps_fn agps;
    b41_slot7_passthrough_fn passthrough;
    b41_slot8_encode_fn encode;
    b41_slot9_decode_fn decode;
    uint64_t optional_null[14];
};
struct b41_engine_arguments {
    struct b41_engine_callback_table callbacks;
    uint8_t first[B41_FIRST_CONFIG_SIZE], second[B41_SECOND_CONFIG_SIZE];
    unsigned missing_contracts;
};
/* Pure mandatory-mask preflight + actual typed layout. Slot2 is optional in
 * pinned registration; slots0,1,3..9 are required. No function is called.
 * Zero means table constructed, never registration/engine success.
 */
int b41_engine_callback_table_build(const struct b41_known_callbacks *callbacks,
                                   struct b41_engine_callback_table *out);
/* Copies stable argument storage for registration followed by init, but NEVER
 * invokes either. Returns1 partial startup. Owned process-lifetime storage and
 * expose-before-register are still mandatory: registration writes globals even
 * on failure. Shape validity does not prove active callback host services.
 */
int b41_engine_arguments_build(const struct b41_startup_bundle *bundle,
    const struct b41_known_callbacks *callbacks, struct b41_engine_arguments *out);
#endif
