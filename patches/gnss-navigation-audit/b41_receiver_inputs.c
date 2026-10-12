/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_receiver_inputs.h"
#include "b41_runtime_config.h"
#include <errno.h>
#include <string.h>

int b41_receiver_inputs_build(enum b41_receiver_native_mode mode,
    const struct b41_first_config *first, const struct b41_second_config *base,
    struct b41_receiver_inputs *out)
{
    struct b41_receiver_inputs result = {0};
    struct b41_startup_config fragment = {0};
    uint32_t primary = 0;
    int status;
    if (!first || !base || !out) return -EINVAL;
    if (mode != B41_RECEIVER_NATIVE_NMEA_QUIET) return -EOPNOTSUPP;
    if (first->missing_inputs & B41_FIRST_TRANSPORT) return -ENODATA;
    if (base->missing_inputs & B41_SECOND_RECEIVER_FDS) return -ENODATA;
    for (unsigned i = 0x68; i < 0x6c; ++i) {
        if (first->provenance[i] != B41_FIRST_TRANSPORT_MODE) return -ENODATA;
        if (first->bytes[i]) return -EOPNOTSUPP;
    }
    for (unsigned i = 0; i < 4; ++i) {
        if (base->provenance[0x10 + i] != B41_SECOND_RECEIVER_FD) return -ENODATA;
        primary |= (uint32_t)base->bytes[0x10 + i] << (8 * i);
    }
    if (primary > INT32_MAX) return -EBADF;
    for (unsigned i = 0x1cc; i < 0x1ea; ++i)
        if (base->provenance[i] == B41_SECOND_UNKNOWN) return -ENODATA;
    if (memcmp(base->bytes + 0x1cc, "UseCallback", 11) || base->bytes[0x1d7])
        return -EOPNOTSUPP;

    /* These literals select the existing pure word0 mapping. They are not
     * property values claimed to exist on pmOS; no property owner is populated.
     */
    status = b41_startup_set_build_policy(&fragment, "user", "0");
    if (status) return status;
    result.log.log_flags_88e40 = 0x10;
    result.log.secondary_policy_de3c0 = 0;
    result.log.ap_config_init_884c4 = 0;
    result.second = *base;
    result.second.bytes[4] = result.log.log_flags_88e40;
    result.second.provenance[4] = B41_RUNTIME_PROVENANCE;
    memcpy(result.second.bytes + 0xc8, fragment.second + 0xc8, 4);
    memset(result.second.provenance + 0xc8, B41_SECOND_BUILD_RESULT, 4);
    result.second.missing_inputs &= ~B41_SECOND_BUILD_POLICY;
    result.second.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        result.second.unresolved_bytes += result.second.provenance[i] == B41_SECOND_UNKNOWN;
    *out = result;
    return 1;
}
