/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_native_satellite_config.h"
#include <assert.h>
#include <errno.h>
#include <string.h>

int main(void)
{
    struct b41_first_config base = {0}, out, before, expected;
    struct b41_native_satellite_settings s = {{0}};
    base.missing_inputs = 0x8000007fu;
    base.xml_policy_missing = 1;
    base.provenance[0x58] = base.provenance[0x59] =
        base.provenance[0x5a] = B41_FIRST_CONSTANT;
    for (unsigned vector = 0; vector < 4096; ++vector) {
        for (unsigned i = 0; i < B41_SAT_COUNT; ++i)
            s.enabled[i] = (vector >> i) & 1;
        unsigned mask = (vector & 255) | ((vector & 0x100) << 1) |
            ((vector & 0x200) >> 1) | ((vector & 0x400) << 1) |
            ((vector & 0x800) >> 1);
        assert(b41_native_satellite_config_apply(&base, &s, &out) == 1);
        expected = base;
        expected.bytes[0x58] = mask;
        expected.bytes[0x59] = mask >> 8;
        expected.provenance[0x58] = expected.provenance[0x59] =
            B41_NATIVE_SATELLITE_PROVENANCE;
        expected.provenance[0x5a] = B41_FIRST_UNKNOWN;
        expected.unresolved_bytes = B41_FIRST_SIZE - 2;
        assert(!memcmp(&out, &expected, sizeof(out)));
        before = out;
        assert(b41_native_satellite_config_apply(&out, &s, &out) == 1);
        assert(!memcmp(&out, &before, sizeof(out)));
    }
    before = out;
    for (unsigned i = 0; i < B41_SAT_COUNT; ++i) {
        for (unsigned invalid = 2; invalid < 256; ++invalid) {
            s.enabled[i] = invalid;
            assert(b41_native_satellite_config_apply(&base, &s, &out) == -EINVAL);
            assert(!memcmp(&out, &before, sizeof(out)));
        }
        s.enabled[i] = 1;
    }
    assert(b41_native_satellite_config_apply(NULL, &s, &out) == -EINVAL);
    assert(b41_native_satellite_config_apply(&base, NULL, &out) == -EINVAL);
    assert(b41_native_satellite_config_apply(&base, &s, NULL) == -EINVAL);
    base.bytes[0x58] = 1;
    assert(b41_native_satellite_config_apply(&base, &s, &out) == -ESTALE);
    base.bytes[0x58] = 0;
    base.provenance[0x58] = B41_FIRST_CLOCK_RESULT;
    assert(b41_native_satellite_config_apply(&base, &s, &out) == -ESTALE);
    assert(!memcmp(&out, &before, sizeof(out)));
    base.provenance[0x58] = B41_FIRST_CONSTANT;
    base.bytes[0x5a] = 1;
    assert(b41_native_satellite_config_apply(&base, &s, &out) == -ESTALE);
    assert(!memcmp(&out, &before, sizeof(out)));
    base.provenance[0x5a] = 0x80;
    assert(b41_native_satellite_config_apply(&base, &s, &out) == 1);
    assert(out.bytes[0x5a] == 1 && out.provenance[0x5a] == 0x80);
    base = out;
    before = out;
    assert(b41_native_start_config_apply(&base, B41_NATIVE_FACTORY_START, &out) == -EOPNOTSUPP);
    assert(b41_native_start_config_apply(&base, 99, &out) == -EINVAL);
    assert(!memcmp(&out, &before, sizeof(out)));
    base.provenance[0x5a] = B41_FIRST_CONSTANT;
    base.bytes[0x5a] = 0;
    assert(b41_native_start_config_apply(&base, B41_NATIVE_NORMAL_START, &out) == 1);
    assert(out.bytes[0x5a] == 1);
    assert(out.provenance[0x5a] == B41_NATIVE_SATELLITE_PROVENANCE);
    assert(out.unresolved_bytes == B41_FIRST_SIZE - 3);
    before = out;
    assert(b41_native_start_config_apply(&out, B41_NATIVE_NORMAL_START, &out) == 1);
    assert(!memcmp(&out, &before, sizeof(out)));
    assert(b41_native_satellite_config_apply(&out, &s, &out) == 1);
    assert(!memcmp(&out, &before, sizeof(out)));
    base = out;
    base.bytes[0x5a] = 0;
    assert(b41_native_start_config_apply(&base, B41_NATIVE_NORMAL_START, &out) == -ESTALE);
    assert(!memcmp(&out, &before, sizeof(out)));
    struct b41_first_inputs inputs = {0};
    assert(b41_first_config_build(&inputs, &base) == 1);
    for (unsigned i = 0x58; i <= 0x5a; ++i)
        assert(base.provenance[i] == B41_FIRST_UNKNOWN);
    before = base;
    assert(b41_native_satellite_config_apply(&base, &s, &out) == 1);
    assert(b41_native_start_config_apply(&out, B41_NATIVE_NORMAL_START, &out) == 1);
    assert(out.unresolved_bytes + 3 == before.unresolved_bytes);
    assert(out.missing_inputs == before.missing_inputs);
    assert(out.xml_policy_missing == before.xml_policy_missing);
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i) {
        if (i >= 0x58 && i <= 0x5a) continue;
        assert(out.bytes[i] == before.bytes[i]);
        assert(out.provenance[i] == before.provenance[i]);
    }
    return 0;
}
