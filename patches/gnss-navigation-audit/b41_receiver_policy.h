/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_RECEIVER_POLICY_H
#define B41_RECEIVER_POLICY_H
#include "b41_second_config.h"

#define B41_RECEIVER_PROPERTY_MAX 92u
struct b41_receiver_property_owner {
    unsigned entered, collected;
    int first_error;
    char build_type[B41_RECEIVER_PROPERTY_MAX];
    char debuggable[B41_RECEIVER_PROPERTY_MAX];
    size_t lengths[2];
};
struct b41_receiver_log_sources {
    uint8_t log_flags_88e40, secondary_policy_de3c0;
    uint32_t ap_config_init_884c4;
};
/* Actual Bionic property service; unsupported on other libc implementations.
 * Only the two pinned keys are accepted. Returns length or negative errno.
 * Missing properties are errors; no file/env/default replacement is used.
 * Buffer must have B41_RECEIVER_PROPERTY_MAX bytes. CI wraps this boundary.
 */
int b41_receiver_property_read(const char *key, char *value);
/* Fresh ZEROED storage, sole setup controller before worker exposure. Exactly
 * two ordered property reads, no retry, allocation, worker or engine call.
 * Reentry never reads again; first failure and earlier evidence are retained.
 * Property IPC itself requires the dedicated child's external deadline.
 * Zero means properties collected only, not receiver initialization.
 */
int b41_receiver_properties_collect(struct b41_receiver_property_owner *owner);
/* mnld628e0 ->636c4: second+c8 from real build properties. Reuses the existing
 * conservative constructor, refusing stock's -1 for unsupported combinations.
 * mnld63698..636d8: second+4 is log_flags, with bit0 cleared ONLY when
 * secondary_policy==0 && ap_config_init==1. The remaining bits are never guessed.
 * sources must be the legitimate policy owner's snapshot; this helper does
 * not acquire mnld globals or establish their earlier producers.
 * Updates exactly five bytes. Already-resolved conflicting bytes are refused.
 * Only B41_SECOND_BUILD_POLICY is fulfilled. Unrelated masks/flags survive;
 * byte completeness is recounted, never used as INIT/AGPS admission evidence.
 * Returns1 partial; all failures leave out untouched. Input/out may alias.
 */
int b41_receiver_policy_apply(const struct b41_second_config *base,
    const struct b41_receiver_property_owner *properties,
    const struct b41_receiver_log_sources *sources, struct b41_second_config *out);
#endif
