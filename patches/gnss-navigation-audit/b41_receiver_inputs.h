/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_RECEIVER_INPUTS_H
#define B41_RECEIVER_INPUTS_H
#include "b41_receiver_policy.h"
#include "b41_first_config.h"

enum b41_receiver_native_mode {
    B41_RECEIVER_NATIVE_NMEA_QUIET = 1,
};
struct b41_receiver_inputs {
    struct b41_receiver_log_sources log;
    struct b41_second_config second;
};
/* Pure native configuration producer, before engine exposure. This is an
 * intentional host/NMEA/no-diagnostics policy, NOT a read of mnld globals or
 * a fabricated Android property receipt. No property-service dependency.
 * Requires source-tagged HOST first+68, receiver-fd second+10, and a resolved
 * UseCallback path at second+1cc. Actual fd/image ownership is still established
 * by native_arguments_prepare; configuration provenance does not replace it.
 *
 * Native quiet policy produces log88e40=0x10 (keep file-control bit4),
 * MPVT_LOG_ENABLE/de3c0=0, HOST AP-config selector=0 and release debug word=0.
 * The legacy log.secondary_policy_de3c0 field actually denotes MPVT logging,
 * not gpsdl1 availability. Do not use it to select a secondary receiver.
 * On stock's offload path x25 remains de000, so [x25+4c4] is de4c4 instead;
 * the old 884c4 interpretation applies only to the supported HOST path.
 *
 * Explicit quiet mode replaces prior diagnostic bytes at second+4/+c8 only.
 * It never rewrites paths, fds, calibration, MPE or other config. BUILD_POLICY
 * alone is fulfilled. Every other missing-input bit and semantic gate survives.
 * Rejects unsupported mode/offload/unresolved transport/path/fd snapshots.
 * Returns1 partial, never full INIT admission. Failure leaves output untouched.
 * base may alias out->second; storage is copied, no resource is adopted.
 */
int b41_receiver_inputs_build(enum b41_receiver_native_mode mode,
    const struct b41_first_config *first, const struct b41_second_config *base,
    struct b41_receiver_inputs *out);
#endif
