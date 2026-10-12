/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_lna_query_plan.h"
#include "b41_native_arguments.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#if defined(__BIONIC__)
#error This fixture is for the CI host, never the native engine executor.
#endif

struct receipt_fixture {
    int result16;
    uint32_t write16;
    unsigned calls;
};

static int query(void *context, int fd, unsigned command, uint32_t *output)
{
    struct receipt_fixture *f = context;
    const unsigned commands[] = {11, 30, 16, 21};
    assert(fd == 37 && f->calls < 4 && command == commands[f->calls++]);
    switch (command) {
    case 11: assert(!output); return 81;
    case 30: assert(!output); return 1;
    case 16:
        assert(output && *output == 0);
        if (f->write16) *output = f->write16;
        return f->result16;
    case 21: assert(output); *output = 7; return 0;
    default: assert(0); return -EINVAL;
    }
}

static void same_except_lna(const struct b41_first_config *actual,
                            const struct b41_first_config *successful)
{
    assert(actual->missing_inputs == successful->missing_inputs);
    assert(actual->unresolved_bytes == successful->unresolved_bytes);
    assert(actual->xml_policy_missing == successful->xml_policy_missing);
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i) {
        assert(actual->bytes[i] == successful->bytes[i]);
        if (i >= 0x54 && i < 0x58) {
            assert(actual->bytes[i] == 0);
            assert(actual->provenance[i] == B41_FIRST_OEM_LNA_ZERO_PROVENANCE);
            assert(successful->provenance[i] == B41_FIRST_LNA_RESULT);
        } else
            assert(actual->provenance[i] == successful->provenance[i]);
    }
}

static void rejected_receipts(const struct b41_first_inputs *semantic)
{
    struct b41_lna_query_snapshot snapshot;
    struct b41_first_config first, before;
    const int errors[] = {-EBUSY, -ENODEV, -EIO, -EINVAL, 1};
    struct receipt_fixture f = {0};
    memset(&before, 0xa5, sizeof(before));
    first = before;
    assert(b41_queries_collect_with_lna_plan(37, B41_LNA_UNRESOLVED,
        query, &f, &snapshot) == -EOPNOTSUPP);
    assert(f.calls == 0);
    memset(&snapshot, 0, sizeof(snapshot));
    assert(b41_first_config_from_lna_plan(semantic, &snapshot, &first) == -EOPNOTSUPP);
    assert(!memcmp(&first, &before, sizeof(first)));
    for (unsigned profile = B41_LNA_PINNED_MCUDL_DISABLED;
         profile <= B41_LNA_PINNED_METADATA_ABSENT; ++profile) {
        int expected = profile == B41_LNA_PINNED_MCUDL_DISABLED ? -EFAULT : -ENODATA;
        f = (struct receipt_fixture){.result16 = expected, .write16 = 143};
        assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &snapshot) == expected);
        assert(f.calls == 3 && snapshot.lna_query_status == expected);
        assert(snapshot.queries.lna_pin == 143 && snapshot.queries.failed_command == 16);
        assert(b41_first_config_from_lna_plan(semantic, &snapshot, &first) == -ENODATA);
        assert(!memcmp(&first, &before, sizeof(first)));
        f = (struct receipt_fixture){.result16 = expected == -EFAULT ? -ENODATA : -EFAULT};
        assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &snapshot) == f.result16);
        assert(f.calls == 3 && snapshot.lna_query_status == f.result16);
        for (unsigned i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i) {
            f = (struct receipt_fixture){.result16 = errors[i]};
            int status = errors[i] > 0 ? -EPROTO : errors[i];
            assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &snapshot) == status);
            assert(f.calls == 3 && snapshot.lna_query_status == errors[i]);
        }
        f = (struct receipt_fixture){.result16 = expected};
        assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &snapshot) == 0);
        snapshot.queries.present |= B41_FIRST_LNA_QUERY;
        assert(b41_first_config_from_lna_plan(semantic, &snapshot, &first) == -EPROTO);
        assert(!memcmp(&first, &before, sizeof(first)));
    }
}

int main(int argc, char **argv)
{
    unsigned char xml[65536], calibration[16] = {0};
    assert(argc == 2);
    FILE *file = fopen(argv[1], "rb");
    assert(file);
    size_t size = fread(xml, 1, sizeof(xml), file);
    assert(size && size < sizeof(xml) && !ferror(file) && fclose(file) == 0);
    struct b41_first_inputs semantic = {
        .present = B41_FIRST_PLATFORM_PROFILE | B41_FIRST_CALIBRATION |
            B41_FIRST_TRANSPORT | B41_FIRST_XML_ASSET,
        .default_platform_profile = 1, .clock_calibration = calibration,
        .clock_calibration_size = sizeof(calibration), .primary_fd = 37,
        .transport = B41_FIRST_HOST, .xml_asset = B41_FIRST_XML_VENDOR,
        .xml_bytes = xml, .xml_size = size,
    };
    struct b41_runtime_sources runtime = {
        .present = B41_RUNTIME_ALL, .chip_id_de304 = 0xffff6878,
        .nav_base_88c20 = 6, .nav_override_88e10 = UINT32_MAX,
        .nav_override_88e14 = UINT32_MAX,
    };
    struct b41_second_runtime_sources second_runtime = {.present = B41_SECOND_RUNTIME_ALL};
    struct b41_second_inputs second_inputs = {
        .present = B41_SECOND_BUILD_POLICY | B41_SECOND_RECEIVER_FDS,
        .build_type = "user", .debuggable = "0", .primary_fd = 37,
    };
    struct b41_second_config second;
    struct b41_lna_query_snapshot successful_receipt;
    struct b41_first_config successful, raw;
    struct b41_runtime_config successful_runtime;
    struct b41_startup_bundle successful_bundle;
    struct receipt_fixture f = {0};
    assert(b41_second_config_build(&second_inputs, &second) == 1);
    assert(b41_queries_collect_with_lna_plan(37, B41_LNA_OWNED_METADATA_REQUIRED,
        query, &f, &successful_receipt) == 0 && f.calls == 4);
    assert(b41_first_config_from_lna_plan(&semantic, &successful_receipt, &successful) == 1);
    assert(b41_runtime_config_apply(&successful, &runtime, xml, size, &successful_runtime) == 1);
    assert(b41_startup_bundle_build(&successful, &runtime, &second, &second_runtime,
        xml, size, &successful_bundle) == 1);
    assert(b41_first_config_build(&semantic, &raw) == 1);
    assert(raw.missing_inputs & B41_FIRST_LNA_QUERY);
    for (unsigned i = 0x54; i < 0x58; ++i)
        assert(raw.provenance[i] == B41_FIRST_UNKNOWN);

    for (unsigned profile = B41_LNA_PINNED_MCUDL_DISABLED;
         profile <= B41_LNA_PINNED_METADATA_ABSENT; ++profile) {
        int error = profile == B41_LNA_PINNED_MCUDL_DISABLED ? -EFAULT : -ENODATA;
        struct b41_lna_query_snapshot receipt, receipt_before;
        struct b41_first_config first;
        struct b41_runtime_config applied;
        struct b41_startup_bundle bundle;
        f = (struct receipt_fixture){.result16 = error};
        assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &receipt) == 0);
        assert(f.calls == 4 && receipt.profile == (enum b41_lna_query_profile)profile);
        assert(receipt.lna_query_status == error && receipt.queries.lna_pin == 0);
        assert(receipt.lna_origin == B41_LNA_VALUE_OEM_RETAINED_ZERO);
        assert(!(receipt.queries.present & B41_FIRST_LNA_QUERY));
        receipt_before = receipt;
        assert(b41_first_config_from_lna_plan(&semantic, &receipt, &first) == 1);
        same_except_lna(&first, &successful);
        assert(b41_runtime_config_apply(&first, &runtime, xml, size, &applied) == 1);
        same_except_lna(&applied.first, &successful_runtime.first);
        assert(applied.engine_contract_missing && applied.first.xml_policy_missing);
        assert(b41_startup_bundle_build(&first, &runtime, &second, &second_runtime,
            xml, size, &bundle) == 1);
        same_except_lna(&bundle.runtime.first, &successful_bundle.runtime.first);
        assert(!memcmp(bundle.abi.first, bundle.runtime.first.bytes, B41_FIRST_SIZE));
        assert(!memcmp(&bundle.second, &successful_bundle.second, sizeof(bundle.second)));
        assert(bundle.missing_contracts == successful_bundle.missing_contracts);
        assert(b41_native_arguments_config_missing(&bundle) ==
            b41_native_arguments_config_missing(&successful_bundle));
        assert(bundle.missing_contracts & B41_MISSING_FIRST_CONFIG);
        assert(bundle.missing_contracts & B41_MISSING_SECOND_POLICY);
        assert(bundle.missing_contracts & B41_MISSING_AGPS_RECEIVER);
        assert(bundle.missing_contracts & B41_MISSING_TRANSPORT_OWNER);
        assert(bundle.missing_contracts & B41_MISSING_STOP_CONTRACT);
        assert(bundle.missing_contracts & B41_MISSING_HOST_SERVICES);
        assert(!memcmp(&receipt, &receipt_before, sizeof(receipt)));
    }
    rejected_receipts(&semantic);
    puts("PASS: existing LNA receipt propagation; errno/profile retained; startup gates remain");
    return 0;
}
