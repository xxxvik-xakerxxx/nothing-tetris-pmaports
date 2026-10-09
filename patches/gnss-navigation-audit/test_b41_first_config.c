/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "b41_first_config.h"

static uint32_t value(const struct b41_first_config *config, unsigned offset)
{
    return config->bytes[offset] | (uint32_t)config->bytes[offset + 1] << 8 |
        (uint32_t)config->bytes[offset + 2] << 16 |
        (uint32_t)config->bytes[offset + 3] << 24;
}

int main(void)
{
    uint8_t calibration[16];
    for (unsigned i = 0; i < 16; ++i)
        calibration[i] = (uint8_t)i;
    struct b41_first_inputs inputs = {0};
    struct b41_first_config config, before;
    assert(b41_first_config_build(&inputs, &config) == 1);
    assert(config.missing_inputs == 0x7f && config.xml_policy_missing);
    assert(config.provenance[0] == B41_FIRST_CONSTANT);
    assert(!config.provenance[0x13] && !config.provenance[0x3c]);
    inputs.present = 0x7f;
    inputs.default_platform_profile = 1;
    inputs.clock_ioctl_result = 0;
    inputs.lna_pin = 23;
    inputs.modem_status = 0x12345678;
    inputs.clock_calibration = calibration;
    inputs.clock_calibration_size = 16;
    inputs.primary_fd = 0; /* fd0 is valid; no copied vendor cleanup bug. */
    inputs.transport = B41_FIRST_HOST;
    inputs.xml_asset = B41_FIRST_XML_VENDOR;
    inputs.xml_bytes = "<unparsed/>";
    inputs.xml_size = sizeof("<unparsed/>") - 1;
    assert(b41_first_config_build(&inputs, &config) == 1);
    assert(!config.missing_inputs && config.unresolved_bytes && config.xml_policy_missing);
    assert(config.unresolved_bytes == 27);
    assert(value(&config, 0x18) == 26000000 && value(&config, 0x1c) == 115200);
    assert(config.bytes[0x13] == 255 && config.bytes[0x14] == 0xd0);
    assert(value(&config, 0x54) == 23 && value(&config, 0x64) == 0x12345678);
    assert(!memcmp(config.bytes + 0x3c, calibration, 16));
    assert(value(&config, 0x68) == 0 && config.provenance[0x68] == B41_FIRST_TRANSPORT_MODE);
    assert(!config.provenance[0x20] && !config.provenance[0x28] &&
           !config.provenance[0x38] && !config.provenance[0x6c]);
    for (unsigned flag = 0; flag <= 255; ++flag) {
        inputs.clock_ioctl_result = (int)flag;
        assert(b41_first_config_build(&inputs, &config) == 1);
        int ff = flag == 0 || flag == 2 || flag == 3 || flag == 16 ||
                 flag == 32 || flag == 48 || flag == 64;
        assert(config.bytes[0x13] == (ff ? 255 : 254));
        assert(value(&config, 0x18) == (flag == 81 ? 52000000u : 26000000u));
    }
    before = config;
    inputs.clock_ioctl_result = -1;
    assert(b41_first_config_build(&inputs, &config) == -EIO);
    assert(!memcmp(&config, &before, sizeof(config)));
    inputs.clock_ioctl_result = 0;
    inputs.clock_calibration_size = 7;
    assert(b41_first_config_build(&inputs, &config) == -EMSGSIZE);
    assert(!memcmp(&config, &before, sizeof(config)));
    inputs.clock_calibration_size = 16;
    inputs.modem_ioctl_result = -1;
    assert(b41_first_config_build(&inputs, &config) == -EIO);
    inputs.modem_ioctl_result = 0;
    inputs.lna_ioctl_result = -1;
    assert(b41_first_config_build(&inputs, &config) == -EIO);
    inputs.lna_ioctl_result = 1;
    assert(b41_first_config_build(&inputs, &config) == -EPROTO);
    inputs.lna_ioctl_result = 0;
    inputs.modem_ioctl_result = 1;
    assert(b41_first_config_build(&inputs, &config) == -EPROTO);
    inputs.modem_ioctl_result = 0;
    inputs.primary_fd = -1;
    assert(b41_first_config_build(&inputs, &config) == -EINVAL);
    inputs.primary_fd = 41;
    inputs.transport = B41_FIRST_OFFLOAD;
    assert(b41_first_config_build(&inputs, &config) == 1);
    assert(value(&config, 0x68) == 1);
    inputs.present &= ~B41_FIRST_PLATFORM_PROFILE;
    assert(b41_first_config_build(&inputs, &config) == 1);
    assert(!config.provenance[0x3c] && !config.provenance[0x14]);
    assert(b41_first_config_build(NULL, &config) == -EINVAL);
    assert(b41_first_config_build(&inputs, NULL) == -EINVAL);
    puts("PASS: typed first-config builder,256 clock flags, provenance and immutable rejection; startup remains gated");
    return 0;
}
