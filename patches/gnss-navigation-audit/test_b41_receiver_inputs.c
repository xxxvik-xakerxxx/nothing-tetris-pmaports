/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_receiver_inputs.h"
#include "b41_runtime_config.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

static struct b41_first_config first_config(void)
{
    struct b41_first_config first = {0};
    memset(first.provenance + 0x68, B41_FIRST_TRANSPORT_MODE, 4);
    first.missing_inputs = B41_FIRST_CALIBRATION | 0x80000000u;
    first.unresolved_bytes = 108;
    first.xml_policy_missing = 7;
    return first;
}

static struct b41_second_config second_config(void)
{
    struct b41_second_config base = {0};
    memset(base.bytes, 0xa5, sizeof(base.bytes));
    memset(base.bytes + 0x10, 0, 8); /* Actual fd0 is valid; inactive slot is0. */
    memset(base.provenance + 0x10, B41_SECOND_RECEIVER_FD, 4);
    memset(base.provenance + 0x14, B41_SECOND_INACTIVE_SECONDARY, 4);
    memset(base.bytes + 0x1cc, 0, 30);
    memcpy(base.bytes + 0x1cc, "UseCallback", 11);
    memset(base.provenance + 0x1cc, B41_SECOND_LITERAL, 30);
    base.missing_inputs = B41_SECOND_BUILD_POLICY | B41_SECOND_MPE_STATE_COPY | 0x80000000u;
    base.receiver_owner_missing = 3; base.stop_contract_missing = 5; base.mpe_schema_missing = 7;
    return base;
}

static void policy_vectors(void)
{
    static const uint32_t prior_debug[] = {0, 1, 2, UINT32_MAX};
    struct b41_first_config first = first_config(), before_first = first;
    struct b41_second_config base = second_config();
    struct b41_receiver_inputs out;
    for (unsigned flags = 0; flags < 256; ++flags)
        for (unsigned debug = 0; debug < 4; ++debug) {
            base.bytes[4] = (uint8_t)flags;
            base.provenance[4] = B41_RUNTIME_PROVENANCE;
            for (unsigned i = 0; i < 4; ++i) {
                base.bytes[0xc8 + i] = (uint8_t)(prior_debug[debug] >> (8 * i));
                base.provenance[0xc8 + i] = B41_SECOND_BUILD_RESULT;
            }
            assert(b41_receiver_inputs_build(B41_RECEIVER_NATIVE_NMEA_QUIET, &first, &base, &out) == 1);
            assert(out.log.log_flags_88e40 == 0x10);
            assert(out.log.secondary_policy_de3c0 == 0 && out.log.ap_config_init_884c4 == 0);
            assert(out.second.bytes[4] == 0x10 && out.second.provenance[4] == B41_RUNTIME_PROVENANCE);
            for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i) {
                if (i == 4) continue;
                if (i >= 0xc8 && i < 0xcc) {
                    assert(out.second.bytes[i] == 0 && out.second.provenance[i] == B41_SECOND_BUILD_RESULT);
                } else {
                    assert(out.second.bytes[i] == base.bytes[i]);
                    assert(out.second.provenance[i] == base.provenance[i]);
                }
            }
            assert(out.second.missing_inputs == (base.missing_inputs & ~B41_SECOND_BUILD_POLICY));
            assert(out.second.unresolved_bytes == B41_SECOND_CONFIG_SIZE - 43);
            assert(out.second.receiver_owner_missing == 3 && out.second.stop_contract_missing == 5);
            assert(out.second.mpe_schema_missing == 7);
            assert(!memcmp(&first, &before_first, sizeof(first)));
            struct b41_receiver_inputs again = out;
            assert(b41_receiver_inputs_build(B41_RECEIVER_NATIVE_NMEA_QUIET, &first, &again.second, &again) == 1);
            assert(!memcmp(&again.second, &out.second, sizeof(out.second)));
            assert(again.log.log_flags_88e40 == out.log.log_flags_88e40);
            assert(again.log.secondary_policy_de3c0 == out.log.secondary_policy_de3c0);
            assert(again.log.ap_config_init_884c4 == out.log.ap_config_init_884c4);
        }
    /* MPVT's old secondary field must never erase a real gpsdl1 snapshot. */
    base.bytes[0x14] = 42;
    memset(base.provenance + 0x14, B41_SECOND_RECEIVER_FD, 4);
    assert(b41_receiver_inputs_build(B41_RECEIVER_NATIVE_NMEA_QUIET, &first, &base, &out) == 1);
    assert(out.second.bytes[0x14] == 42 && out.second.provenance[0x14] == B41_SECOND_RECEIVER_FD);
    base.bytes[0x10] = 0xff; base.bytes[0x11] = 0xff;
    base.bytes[0x12] = 0xff; base.bytes[0x13] = 0x7f;
    assert(b41_receiver_inputs_build(B41_RECEIVER_NATIVE_NMEA_QUIET, &first, &base, &out) == 1);
}

static void rejection(void)
{
    struct b41_first_config first = first_config();
    struct b41_second_config base = second_config();
    struct b41_receiver_inputs out, before;
    memset(&out, 0x5a, sizeof(out)); before = out;
    assert(b41_receiver_inputs_build(0, &first, &base, &out) == -EOPNOTSUPP);
    assert(b41_receiver_inputs_build(2, &first, &base, &out) == -EOPNOTSUPP);
    assert(b41_receiver_inputs_build((enum b41_receiver_native_mode)-1, &first, &base, &out) == -EOPNOTSUPP);
    for (unsigned i = 0; i < 4; ++i) {
        struct b41_first_config bad = first;
        bad.provenance[0x68 + i] = B41_FIRST_UNKNOWN;
        assert(b41_receiver_inputs_build(1, &bad, &base, &out) == -ENODATA);
        bad = first; bad.bytes[0x68 + i] = 1;
        assert(b41_receiver_inputs_build(1, &bad, &base, &out) == -EOPNOTSUPP);
        struct b41_second_config stale = base;
        stale.provenance[0x10 + i] = B41_SECOND_LITERAL;
        assert(b41_receiver_inputs_build(1, &first, &stale, &out) == -ENODATA);
    }
    first.missing_inputs |= B41_FIRST_TRANSPORT;
    assert(b41_receiver_inputs_build(1, &first, &base, &out) == -ENODATA);
    first = first_config();
    base.missing_inputs |= B41_SECOND_RECEIVER_FDS;
    assert(b41_receiver_inputs_build(1, &first, &base, &out) == -ENODATA);
    base = second_config(); base.bytes[0x13] = 0x80;
    assert(b41_receiver_inputs_build(1, &first, &base, &out) == -EBADF);
    base = second_config(); base.bytes[0x1d7] = 'x';
    assert(b41_receiver_inputs_build(1, &first, &base, &out) == -EOPNOTSUPP);
    base = second_config(); base.bytes[0x1cc] = 'X';
    assert(b41_receiver_inputs_build(1, &first, &base, &out) == -EOPNOTSUPP);
    for (unsigned i = 0x1cc; i < 0x1ea; ++i) {
        base = second_config(); base.provenance[i] = B41_SECOND_UNKNOWN;
        assert(b41_receiver_inputs_build(1, &first, &base, &out) == -ENODATA);
    }
    base = second_config();
    assert(b41_receiver_inputs_build(1, NULL, &base, &out) == -EINVAL);
    assert(b41_receiver_inputs_build(1, &first, NULL, &out) == -EINVAL);
    assert(b41_receiver_inputs_build(1, &first, &base, NULL) == -EINVAL);
    assert(!memcmp(&out, &before, sizeof(out)));
}

int main(void)
{
    policy_vectors(); rejection();
    puts("PASS: 1024 native quiet overrides, path/transport/fd rejection, gate preservation; no INIT");
    return 0;
}
