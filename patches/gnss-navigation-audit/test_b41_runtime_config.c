/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_runtime_config.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv)
{
    struct b41_first_config base;
    struct b41_runtime_config result, before;
    unsigned char calibration[16] = {0}; /* Synthetic ABI fixture, not provisioning. */
    unsigned char xml[65536];
    assert(argc == 2);
    FILE *file = fopen(argv[1], "rb"); assert(file);
    size_t size = fread(xml, 1, sizeof(xml), file);
    assert(size && size < sizeof(xml) && !ferror(file) && fclose(file) == 0);
    struct b41_first_inputs input = {
        .present = 127, .default_platform_profile = 1,
        .clock_ioctl_result = 1, .lna_ioctl_result = 0, .lna_pin = 0,
        .modem_ioctl_result = 0, .modem_status = 42,
        .clock_calibration = calibration, .clock_calibration_size = 16,
        .transport = B41_FIRST_HOST, .primary_fd = 9,
        .xml_asset = B41_FIRST_XML_VENDOR, .xml_bytes = xml, .xml_size = size,
    };
    assert(b41_first_config_build(&input, &base) == 1 && base.unresolved_bytes == 27);
    struct b41_runtime_sources source = {
        .present = B41_RUNTIME_ALL, .host_mode_88794 = 1,
        .chip_id_de304 = 0x12345678, .capabilities_de308 = 0x10203040,
        .receiver_mode_88c1c = 2, .secondary_de2fe = 255,
        .nav_base_88c20 = 6, .nav_override_88e10 = UINT32_MAX,
        .nav_override_88e14 = UINT32_MAX, .tracking_de9d8 = 1,
        .mpe_requested_de228 = 2, .mpe_probe_4eee0 = 3, .mpe_flag_88c4c = 0x9a,
        .feature_present_ddd84 = 255, .feature_88c80 = 0x9b,
    };
    assert(b41_runtime_config_apply(&base, &source, xml, size, &result) == 1);
    assert(result.first.unresolved_bytes == 0 && result.engine_contract_missing == 1);
    assert(result.xml_get_verified == 1 && result.first.xml_policy_missing == base.xml_policy_missing);
    assert(result.first.missing_inputs == base.missing_inputs);
    unsigned changed = 0;
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i) {
        if (base.provenance[i] == B41_FIRST_UNKNOWN) {
            ++changed; assert(result.first.provenance[i] == B41_RUNTIME_PROVENANCE);
        } else {
            assert(result.first.bytes[i] == base.bytes[i]);
            assert(result.first.provenance[i] == base.provenance[i]);
        }
    }
    assert(changed == 27 && result.first.bytes[0x38] == 6);
    assert(result.first.bytes[0x5b] == 0x9a && result.first.bytes[0x6c] == 0x9b);
    before = result;
    for (unsigned bit = 0; bit < 6; ++bit) {
        source.present = B41_RUNTIME_ALL & ~(1u << bit);
        assert(b41_runtime_config_apply(&base, &source, xml, size, &result) == -ENODATA);
        assert(memcmp(&result, &before, sizeof(result)) == 0);
    }
    source.present = B41_RUNTIME_ALL;
    xml[0] ^= 1;
    assert(b41_runtime_config_apply(&base, &source, xml, size, &result) == -EBADMSG);
    assert(memcmp(&result, &before, sizeof(result)) == 0);
    xml[0] ^= 1;
    source.tracking_de9d8 = 2; source.mpe_requested_de228 = 8;
    source.feature_present_ddd84 = 0; source.secondary_de2fe = 0;
    source.nav_override_88e14 = 8;
    assert(b41_runtime_config_apply(&base, &source, xml, size, &result) == 1);
    assert(result.first.bytes[0x38] == 8 && result.first.bytes[0x50] == 0);
    assert(result.first.bytes[0x5b] == 0 && result.first.bytes[0x6c] == 0);
    for (unsigned i = 0; i < 4; ++i) assert(result.first.bytes[0x2c+i] == 0 && result.first.bytes[0x34+i] == 0);
    return 0;
}
