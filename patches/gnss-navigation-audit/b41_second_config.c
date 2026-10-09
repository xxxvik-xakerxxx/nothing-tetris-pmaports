/* SPDX-License-Identifier: GPL-2.0-only */
#include <errno.h>
#include <string.h>
#include "b41_second_config.h"

static void word(struct b41_second_config *out, unsigned offset, uint32_t value,
                 enum b41_second_provenance source)
{
    for (unsigned i = 0; i < 4; ++i) {
        out->bytes[offset + i] = (uint8_t)(value >> (8 * i));
        out->provenance[offset + i] = source;
    }
}

static void adopt(struct b41_second_config *out, const struct b41_startup_config *fragment,
                  enum b41_second_provenance source)
{
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i) {
        if (fragment->resolved_second[i]) {
            out->bytes[i] = fragment->second[i];
            out->provenance[i] = source;
        }
    }
}

int b41_second_config_build(const struct b41_second_inputs *inputs,
                            struct b41_second_config *out)
{
    const unsigned all = B41_SECOND_BUILD_POLICY | B41_SECOND_RECEIVER_FDS | B41_SECOND_MPE_STATE_COPY;
    static const unsigned offsets[B41_SECOND_PATH_COUNT] = {
        0xd4, 0xf2, 0x110, 0x190, 0x1ae, 0x1ea, 0x208, 0x226, 0x256,
        0x286, 0x2b6, 0x2e6, 0x316, 0x346, 0x376, 0x3a6, 0x3d6, 0x406, 0x424,
    };
    struct b41_second_config result = {0};
    struct b41_startup_config fragment;
    int status;
    if (!inputs || !out || (inputs->present & ~all))
        return -EINVAL;
    if ((inputs->present & B41_SECOND_RECEIVER_FDS) &&
        (inputs->primary_fd < 0 || inputs->secondary_enabled > 1 ||
         (inputs->secondary_enabled && (inputs->secondary_fd < 0 || inputs->primary_fd == inputs->secondary_fd))))
        return -EINVAL;
    if ((inputs->present & B41_SECOND_MPE_STATE_COPY) &&
        (!inputs->mpe_state || inputs->mpe_state_size != 68 || inputs->mpe_requested > 1))
        return -EINVAL;
    result.missing_inputs = all & ~inputs->present;
    result.receiver_owner_missing = result.stop_contract_missing = result.mpe_schema_missing = 1;
    b41_startup_config_init(&fragment);
    status = b41_startup_set_b41_identity(&fragment);
    if (!status)
        status = b41_startup_set_callback_output(&fragment);
    if (status)
        return status;
    adopt(&result, &fragment, B41_SECOND_LITERAL);
    if (inputs->present & B41_SECOND_BUILD_POLICY) {
        b41_startup_config_init(&fragment);
        status = b41_startup_set_build_policy(&fragment, inputs->build_type, inputs->debuggable);
        if (status)
            return status;
        adopt(&result, &fragment, B41_SECOND_BUILD_RESULT);
    }
    if (inputs->present & B41_SECOND_RECEIVER_FDS) {
        word(&result, 0x10, (uint32_t)inputs->primary_fd, B41_SECOND_RECEIVER_FD);
        /* mnld skips the secondary write when56ce0 bit0 is clear. The block
         * was zeroed, so the final inactive field is0, not a guessed -1 fd.
         */
        word(&result, 0x14, inputs->secondary_enabled ? (uint32_t)inputs->secondary_fd : 0,
            inputs->secondary_enabled ? B41_SECOND_RECEIVER_FD : B41_SECOND_INACTIVE_SECONDARY);
    }
    if (inputs->present & B41_SECOND_MPE_STATE_COPY) {
        result.bytes[0x6c] = (uint8_t)(inputs->mpe_requested & inputs->mpe_backend_result);
        result.provenance[0x6c] = B41_SECOND_MPE_INPUT_COPY;
        memcpy(result.bytes + 0x70, inputs->mpe_state, 68);
        memset(result.provenance + 0x70, B41_SECOND_MPE_INPUT_COPY, 68);
    }
    for (unsigned i = 0; i < B41_SECOND_PATH_COUNT; ++i) {
        if (!inputs->paths[i])
            continue;
        b41_startup_config_init(&fragment);
        status = b41_startup_set_path(&fragment, offsets[i], inputs->paths[i]);
        if (status)
            return status;
        adopt(&result, &fragment, B41_SECOND_PATH_INPUT);
    }
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        result.unresolved_bytes += result.provenance[i] == B41_SECOND_UNKNOWN;
    *out = result;
    return 1;
}
