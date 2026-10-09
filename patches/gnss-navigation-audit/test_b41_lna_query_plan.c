#include <assert.h>
#include <errno.h>
#include <string.h>
#include "b41_lna_query_plan.h"

struct fixture { int status16; uint32_t output16; unsigned calls, fail; };
static int query(void *context, int fd, unsigned command, uint32_t *out)
{
    struct fixture *f = context;
    const unsigned commands[] = {11, 30, 16, 21};
    assert(fd == 37 && f->calls < 4 && command == commands[f->calls++]);
    if (f->fail == command)
        return -EBUSY;
    switch (command) {
    case 11: assert(!out); return 81;
    case 30: assert(!out); return 1;
    case 16: assert(out && *out == 0); *out = f->output16; return f->status16;
    case 21: assert(out); *out = 7; return 0;
    default: assert(0); return -EINVAL;
    }
}

int main(void)
{
    struct b41_lna_query_snapshot s;
    struct b41_first_config out, before;
    struct b41_first_inputs semantic = {0};
    struct fixture f;
    unsigned profile, i;
    const int failures[] = {-EBUSY, -ENODEV, -EIO, -EINVAL, 1};
    for (profile = B41_LNA_PINNED_MCUDL_DISABLED; profile <= B41_LNA_PINNED_METADATA_ABSENT; ++profile) {
        f = (struct fixture){.status16 = profile == B41_LNA_PINNED_MCUDL_DISABLED ? -EFAULT : -ENODATA};
        assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &s) == 0);
        assert(f.calls == 4 && s.lna_origin == B41_LNA_VALUE_OEM_RETAINED_ZERO);
        assert(!(s.queries.present & B41_FIRST_LNA_QUERY));
        assert(b41_first_config_from_lna_plan(&semantic, &s, &out) == 1);
        assert(!(out.missing_inputs & B41_FIRST_LNA_QUERY));
        assert(out.xml_policy_missing && out.unresolved_bytes);
        for (i = 0x54; i < 0x58; ++i)
            assert(out.bytes[i] == 0 && out.provenance[i] == B41_FIRST_OEM_LNA_ZERO_PROVENANCE);
        for (i = 0; i < sizeof(failures) / sizeof(failures[0]); ++i) {
            f = (struct fixture){.status16 = failures[i]};
            assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &s) < 0);
            assert(f.calls == 3 && s.queries.failed_command == 16);
        }
        f = (struct fixture){.status16 = profile == B41_LNA_PINNED_MCUDL_DISABLED ? -ENODATA : -EFAULT};
        assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &s) < 0);
        assert(f.calls == 3); /* Never substitute the other driver profile. */
        f = (struct fixture){.status16 = profile == B41_LNA_PINNED_MCUDL_DISABLED ? -EFAULT : -ENODATA,
                             .output16 = 143};
        assert(b41_queries_collect_with_lna_plan(37, profile, query, &f, &s) < 0);
        assert(f.calls == 3); /* Error with modified output is NOT a default. */
    }
    f = (struct fixture){.status16 = -EFAULT};
    assert(b41_queries_collect_with_lna_plan(37, B41_LNA_OWNED_METADATA_REQUIRED, query, &f, &s) == -EFAULT);
    f = (struct fixture){.output16 = 23};
    assert(b41_queries_collect_with_lna_plan(37, B41_LNA_OWNED_METADATA_REQUIRED, query, &f, &s) == 0);
    assert(b41_first_config_from_lna_plan(&semantic, &s, &out) == 1);
    assert(out.bytes[0x54] == 23 && out.provenance[0x54] == B41_FIRST_LNA_RESULT);
    memset(&before, 0xa5, sizeof(before)); out = before;
    s.first_config_lna_word++;
    assert(b41_first_config_from_lna_plan(&semantic, &s, &out) == -EPROTO);
    assert(memcmp(&before, &out, sizeof(out)) == 0);
    for (i = 0; i < 3; ++i) {
        const unsigned fail[] = {11, 30, 21};
        f = (struct fixture){.status16 = -EFAULT, .fail = fail[i]};
        assert(b41_queries_collect_with_lna_plan(37, B41_LNA_PINNED_MCUDL_DISABLED, query, &f, &s) == -EBUSY);
        assert(s.queries.failed_command == fail[i]);
    }
    f = (struct fixture){0};
    assert(b41_queries_collect_with_lna_plan(37, B41_LNA_UNRESOLVED, query, &f, &s) == -EOPNOTSUPP);
    assert(f.calls == 0);
    /* Every currently supported semantic input present still yields partial1.
     * The frozen builder's27 policy bytes/XML decoder remain unresolved.
     */
    {
        uint8_t calibration[16] = {0};
        struct b41_first_inputs full = {
            .present = B41_FIRST_PLATFORM_PROFILE | B41_FIRST_CALIBRATION |
                B41_FIRST_TRANSPORT | B41_FIRST_XML_ASSET,
            .default_platform_profile = 1, .clock_calibration = calibration,
            .clock_calibration_size = sizeof(calibration), .primary_fd = 37,
            .transport = B41_FIRST_HOST, .xml_asset = B41_FIRST_XML_VENDOR,
            .xml_bytes = "fixture, not parsed XML", .xml_size = 23,
        };
        struct b41_first_config expected;
        f = (struct fixture){.status16 = -EFAULT};
        assert(b41_queries_collect_with_lna_plan(37, B41_LNA_PINNED_MCUDL_DISABLED, query, &f, &s) == 0);
        assert(b41_first_config_from_lna_plan(&full, &s, &out) == 1);
        assert(out.unresolved_bytes == 27 && out.xml_policy_missing && !out.missing_inputs);
        full.present |= B41_FIRST_CLOCK_QUERY | B41_FIRST_MODEM_QUERY;
        full.clock_ioctl_result = 81; full.modem_status = 7;
        assert(b41_first_config_build(&full, &expected) == 1);
        assert(expected.unresolved_bytes == 31);
        for (i = 0; i < B41_FIRST_SIZE; ++i) {
            if (i >= 0x54 && i < 0x58) {
                assert(out.bytes[i] == 0 && out.provenance[i] == B41_FIRST_OEM_LNA_ZERO_PROVENANCE);
            } else {
                assert(out.bytes[i] == expected.bytes[i]);
                assert(out.provenance[i] == expected.provenance[i]);
            }
        }
    }
    f = (struct fixture){0};
    assert(b41_queries_collect_with_lna_plan(-1, B41_LNA_PINNED_MCUDL_DISABLED, query, &f, &s) == -EINVAL);
    assert(b41_queries_collect_with_lna_plan(37, (enum b41_lna_query_profile)-1, query, &f, &s) == -EINVAL);
    assert(b41_queries_collect_with_lna_plan(37, B41_LNA_PINNED_MCUDL_DISABLED, NULL, &f, &s) == -EINVAL);
    assert(f.calls == 0);
    return 0;
}
