/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_startup_bundle.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv)
{
    unsigned char xml[65536], calibration[16] = {0};
    assert(argc == 2);
    FILE *file = fopen(argv[1], "rb"); assert(file);
    size_t size = fread(xml, 1, sizeof(xml), file);
    assert(size && size < sizeof(xml) && !ferror(file) && fclose(file) == 0);
    struct b41_first_inputs inputs = {
        .present = 127, .default_platform_profile = 1,
        .clock_ioctl_result = 1, .clock_calibration = calibration,
        .clock_calibration_size = 16, .primary_fd = 9,
        .transport = B41_FIRST_HOST, .xml_bytes = xml, .xml_size = size,
        .xml_asset = B41_FIRST_XML_VENDOR,
    };
    struct b41_first_config first;
    assert(b41_first_config_build(&inputs, &first) == 1);
    struct b41_second_inputs second_inputs = {
        .present = B41_SECOND_BUILD_POLICY | B41_SECOND_RECEIVER_FDS,
        .build_type = "user", .debuggable = "0", .primary_fd = 9,
    };
    struct b41_second_config second;
    assert(b41_second_config_build(&second_inputs, &second) == 1);
    struct b41_runtime_sources runtime = {
        .present = B41_RUNTIME_ALL, .chip_id_de304 = 0x12345678,
        .nav_base_88c20 = 6, .nav_override_88e10 = UINT32_MAX,
        .nav_override_88e14 = UINT32_MAX,
    };
    struct b41_second_runtime_sources sources = {
        .present = B41_SECOND_RUNTIME_ALL, .global_88a5c = 0x12345678,
        .bits_88c58 = 0x87654321, .bits_88c68 = UINT64_C(0x1122334455667788),
        .buffer_base_de21c = UINT32_MAX, .global_88c18 = 0xab, .table_9a4eb = 255,
    };
    struct b41_startup_bundle bundle, before;
    assert(b41_startup_bundle_build(&first, &runtime, &second, &sources, xml, size, &bundle) == 1);
    assert(bundle.runtime.first.unresolved_bytes == 0);
    assert(bundle.second.unresolved_bytes + 26 == second.unresolved_bytes);
    assert(bundle.second.bytes[0x68] == 0xff && bundle.second.bytes[0x69] == 0xff &&
           bundle.second.bytes[0x6a] == 4 && bundle.second.bytes[0x6b] == 0);
    assert(bundle.second.bytes[0x0c] == 0xab && bundle.second.bytes[0xc4] == 255);
    assert(memcmp(bundle.abi.first, bundle.runtime.first.bytes, B41_FIRST_SIZE) == 0);
    assert(memcmp(bundle.abi.second, bundle.second.bytes, B41_SECOND_CONFIG_SIZE) == 0);
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        assert(bundle.abi.resolved_second[i] == (bundle.second.provenance[i] != B41_SECOND_UNKNOWN));
    assert(bundle.missing_contracts & B41_MISSING_STOP_CONTRACT);
    assert(bundle.missing_contracts & B41_MISSING_HOST_SERVICES);
    assert(bundle.missing_contracts & B41_MISSING_FIRST_CONFIG); /* Full XML tuning not applied. */
    before = bundle;
    for (unsigned bit = 0; bit < 3; ++bit) {
        sources.present = B41_SECOND_RUNTIME_ALL & ~(1u << bit);
        assert(b41_startup_bundle_build(&first, &runtime, &second, &sources, xml, size, &bundle) == -ENODATA);
        assert(memcmp(&bundle, &before, sizeof(bundle)) == 0);
    }
    return 0;
}
