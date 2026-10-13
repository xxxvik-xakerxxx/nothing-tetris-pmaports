/* SPDX-License-Identifier: GPL-2.0-only */
#include "platform_profile.h"
#include <assert.h>
#include <errno.h>
#include <string.h>

static uint32_t word(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
        (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int main(void)
{
    uint8_t record[52] = {0}, calibration[16];
    struct b41_first_inputs inputs = {0};
    struct b41_platform_profile profile, saved;
    struct b41_first_config config, before;
    assert(!b41_platform_profile_decode(record, 52, NULL, 0, &profile));
    assert(!profile.selected_nv && profile.context_hz == 26000000);
    assert(profile.interval == 2000 && profile.context_mode == 255);
    saved = profile;
    for (size_t size = 0; size < 56; size++) {
        if (size == 52)
            continue;
        assert(b41_platform_profile_decode(record, size, NULL, 0, &profile) == -EMSGSIZE);
        assert(!memcmp(&profile, &saved, sizeof(profile)));
    }
    memset(record, 'x', 19);
    record[19] = 'x'; /* Stock forces this byte to NUL, not an input failure. */
    record[24] = 0x78; record[25] = 0x56; record[26] = 0x34; record[27] = 0x12;
    record[28] = 0; record[29] = 0;
    record[32] = 77; record[33] = 91;
    for (unsigned i = 0; i < 16; i++) {
        record[36 + i] = (uint8_t)(i + 1);
        calibration[i] = (uint8_t)(i + 31);
    }
    assert(!b41_platform_profile_decode(record, 52, "0x6878", 7, &profile));
    assert(profile.selected_nv && profile.context_hz == 0x12345678);
    assert(profile.interval == 2000 && profile.context_mode == 77);
    assert(profile.context_profile == 91 && !profile.calibration_override);
    for (unsigned i = 0; i < 2; i++) {
        const char *chip = i ? "0x6570" : "0x6580";
        assert(!b41_platform_profile_decode(record, 52, chip, 7, &profile));
        assert(profile.calibration_override && !memcmp(profile.calibration, record + 36, 16));
    }
    assert(!b41_platform_profile_decode(record, 52, "0x6572", 7, &profile));
    assert(!profile.calibration_override);
    saved = profile;
    assert(b41_platform_profile_decode(record, 52, NULL, 0, &profile) == -ENODATA);
    assert(b41_platform_profile_decode(record, 52, "0x6878", 6, &profile) == -EMSGSIZE);
    assert(b41_platform_profile_decode(record, 52, "", 1, &profile) == -ENODATA);
    assert(!memcmp(&profile, &saved, sizeof(profile)));
    record[28] = 0x34; record[29] = 0x12;
    inputs.present = B41_FIRST_CLOCK_QUERY | B41_FIRST_CALIBRATION;
    inputs.clock_ioctl_result = 0x21;
    inputs.clock_calibration = calibration;
    inputs.clock_calibration_size = 16;
    assert(b41_first_config_build_nv(&inputs, record, 52, "0x6878", 7, &config) == 1);
    assert(config.bytes[0x13] == 254 && word(config.bytes + 0x18) == 0x12345678);
    assert(config.bytes[0x14] == 0x34 && config.bytes[0x15] == 0x12);
    assert(config.bytes[0x24] == 91 && word(config.bytes + 0x1c) == 115200);
    assert(!memcmp(config.bytes + 0x3c, calibration, 16));
    assert(config.provenance[0x18] == B41_FIRST_NVRAM_PROFILE);
    assert(!(config.missing_inputs & B41_FIRST_PLATFORM_PROFILE));
    assert(config.xml_policy_missing && config.unresolved_bytes > 0);
    inputs.clock_ioctl_result = 0x51;
    assert(b41_first_config_build_nv(&inputs, record, 52, "0x6878", 7, &config) == 1);
    assert(word(config.bytes + 0x18) == 52000000);
    assert(config.provenance[0x18] == B41_FIRST_CLOCK_RESULT);
    assert(b41_first_config_build_nv(&inputs, record, 52, "0x6580", 7, &config) == 1);
    assert(!memcmp(config.bytes + 0x3c, record + 36, 16));
    before = config;
    inputs.clock_calibration_size = 15;
    assert(b41_first_config_build_nv(&inputs, record, 52, "0x6878", 7, &config) == -EMSGSIZE);
    assert(!memcmp(&config, &before, sizeof(config)));
    return 0;
}
