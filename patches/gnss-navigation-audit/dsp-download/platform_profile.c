/* SPDX-License-Identifier: GPL-2.0-only */
#include "platform_profile.h"

#include <errno.h>
#include <string.h>

static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
        (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int b41_platform_profile_decode(const uint8_t *record, size_t record_size,
                                const char *configured_chip, size_t chip_size,
                                struct b41_platform_profile *out)
{
    struct b41_platform_profile result = {0};
    const char *end;

    if (!record || !out)
        return -EINVAL;
    if (record_size != B41_PLATFORM_PROFILE_SIZE)
        return -EMSGSIZE;
    /* 7b168 forces record[19] to NUL before strnlen(record,52). Only byte0
     * determines nonempty selection; the remaining name is not serialized.
     */
    result.selected_nv = record[0] != 0;
    if (!result.selected_nv) {
        result.context_hz = 26000000;
        result.interval = 2000;
        result.context_mode = 255;
        *out = result;
        return 0;
    }
    if (!configured_chip || !chip_size)
        return -ENODATA;
    if (chip_size > 32)
        return -EMSGSIZE;
    end = memchr(configured_chip, 0, chip_size);
    if (!end)
        return -EMSGSIZE;
    if (end == configured_chip)
        return -ENODATA;
    result.context_hz = le32(record + 24);
    result.interval = (uint16_t)((uint16_t)record[28] | (uint16_t)record[29] << 8);
    if (!result.interval)
        result.interval = 2000;
    result.context_mode = record[32];
    result.context_profile = record[33];
    /* 62c18..62c70 compares the seven bytes for 0x6580 / 0x6570.
     * Only those selected NV profiles replace the existing calibration copy.
     */
    if ((size_t)(end - configured_chip) == 6 &&
        (!memcmp(configured_chip, "0x6580", 6) ||
         !memcmp(configured_chip, "0x6570", 6))) {
        result.calibration_override = 1;
        memcpy(result.calibration, record + 36, sizeof(result.calibration));
    }
    *out = result;
    return 0;
}

static void field(struct b41_first_config *out, unsigned offset, uint32_t value,
                   unsigned width, uint8_t provenance)
{
    for (unsigned i = 0; i < width; i++) {
        out->bytes[offset + i] = (uint8_t)(value >> (8 * i));
        out->provenance[offset + i] = provenance;
    }
}

int b41_first_config_build_nv(const struct b41_first_inputs *inputs,
                              const uint8_t *record, size_t record_size,
                              const char *configured_chip, size_t chip_size,
                              struct b41_first_config *out)
{
    struct b41_platform_profile profile;
    struct b41_first_inputs base;
    struct b41_first_config result;
    uint8_t provenance;
    int ret;

    if (!inputs || !out)
        return -EINVAL;
    ret = b41_platform_profile_decode(record, record_size, configured_chip,
                                      chip_size, &profile);
    if (ret)
        return ret;
    base = *inputs;
    /* The frozen builder's flag admits only its explicit default branch.
     * Derive this group's provenance from the real record instead.
     */
    base.present &= ~(unsigned)B41_FIRST_PLATFORM_PROFILE;
    ret = b41_first_config_build(&base, &result);
    if (ret < 0)
        return ret;
    provenance = (uint8_t)(profile.selected_nv ? B41_FIRST_NVRAM_PROFILE :
        B41_FIRST_DEFAULT_PROFILE);
    field(&result, 0x14, profile.interval, 2, provenance);
    field(&result, 0x24, profile.context_profile, 1, provenance);
    if (result.provenance[0x13] != B41_FIRST_CLOCK_RESULT)
        field(&result, 0x13, profile.context_mode, 1, provenance);
    if (result.provenance[0x18] != B41_FIRST_CLOCK_RESULT)
        field(&result, 0x18, profile.context_hz, 4, provenance);
    if (inputs->present & B41_FIRST_CALIBRATION) {
        memcpy(result.bytes + 0x3c, inputs->clock_calibration, 16);
        memset(result.provenance + 0x3c, B41_FIRST_CLOCK_CALIBRATION, 16);
    }
    if (profile.calibration_override) {
        memcpy(result.bytes + 0x3c, profile.calibration, 16);
        memset(result.provenance + 0x3c, B41_FIRST_NVRAM_PROFILE, 16);
        result.missing_inputs &= ~(unsigned)B41_FIRST_CALIBRATION;
    }
    result.missing_inputs &= ~(unsigned)B41_FIRST_PLATFORM_PROFILE;
    result.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_FIRST_SIZE; i++)
        result.unresolved_bytes += result.provenance[i] == B41_FIRST_UNKNOWN;
    *out = result;
    return 1;
}
