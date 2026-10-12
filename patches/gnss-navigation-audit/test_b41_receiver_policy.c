/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_receiver_policy.h"
#include "b41_runtime_config.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

static const char *values[2] = {"user", "0"};
static unsigned calls, failed_index = 2, malformed;
static int injected_error;

int __wrap_b41_receiver_property_read(const char *key, char *value)
{
    unsigned index = calls++;
    assert(index < 2);
    assert(!strcmp(key, index ? "ro.debuggable" : "ro.build.type"));
    if (index == failed_index) return injected_error;
    size_t length = strlen(values[index]);
    assert(length < B41_RECEIVER_PROPERTY_MAX);
    memcpy(value, values[index], length + 1);
    if (malformed == 1) value[length] = 'x';
    if (malformed == 2 && length > 1) value[1] = 0;
    return malformed == 3 ? (int)B41_RECEIVER_PROPERTY_MAX : (int)length;
}
int __real_b41_receiver_property_read(const char *key, char *value);
#if defined(__BIONIC__)
int __wrap___system_property_get(const char *key, char *value)
{
    const char *text = !strcmp(key, "ro.build.type") ? values[0] : values[1];
    memcpy(value, text, strlen(text) + 1);
    return (int)strlen(text);
}
#endif

static void reset(const char *type, const char *debug)
{
    values[0] = type; values[1] = debug;
    calls = 0; failed_index = 2; malformed = 0; injected_error = 0;
}

static void owner_failures(void)
{
    struct b41_receiver_property_owner p;
    assert(b41_receiver_properties_collect(NULL) == -EINVAL);
    for (unsigned index = 0; index < 2; ++index) {
        for (unsigned error = 0; error < 3; ++error) {
            memset(&p, 0, sizeof(p)); reset("user", "0");
            failed_index = index;
            injected_error = error == 0 ? -EAGAIN : error == 1 ? -EACCES : -ENODATA;
            assert(b41_receiver_properties_collect(&p) == injected_error);
            assert(p.collected == index && p.first_error == injected_error);
            if (index) assert(!strcmp(p.build_type, "user") && p.lengths[0] == 4);
            assert(b41_receiver_properties_collect(&p) == injected_error);
            assert(calls == index + 1);
        }
    }
    for (unsigned mode = 0; mode < 4; ++mode) {
        memset(&p, 0, sizeof(p)); reset(mode ? "user" : "", "0"); malformed = mode;
        int expected = mode == 0 ? -ENODATA : mode == 3 ? -EOVERFLOW : -EBADMSG;
        assert(b41_receiver_properties_collect(&p) == expected);
        assert(p.collected == 0 && calls == 1);
        assert(b41_receiver_properties_collect(&p) == expected && calls == 1);
    }
    char longest[B41_RECEIVER_PROPERTY_MAX];
    memset(longest, 'x', sizeof(longest) - 1); longest[sizeof(longest) - 1] = 0;
    memset(&p, 0, sizeof(p)); reset(longest, "0");
    assert(b41_receiver_properties_collect(&p) == 0);
    assert(p.lengths[0] == sizeof(longest) - 1 && calls == 2);
    assert(b41_receiver_properties_collect(&p) == -EALREADY && calls == 2);
}

static struct b41_second_config base_config(void)
{
    struct b41_second_config base;
    memset(&base, 0, sizeof(base));
    memset(base.bytes, 0xa5, sizeof(base.bytes));
    base.bytes[0x10] = 37;
    base.provenance[0x10] = B41_SECOND_RECEIVER_FD;
    base.missing_inputs = B41_SECOND_BUILD_POLICY | B41_SECOND_RECEIVER_FDS |
        B41_SECOND_MPE_STATE_COPY | 0x80000000u;
    base.unresolved_bytes = 0; /* Deliberately stale; builder must count bytes. */
    base.receiver_owner_missing = 3; base.stop_contract_missing = 5; base.mpe_schema_missing = 7;
    return base;
}

static void matrix(void)
{
    static const char *const types[] = {"user", "eng", "userdebug"};
    static const uint8_t secondary[] = {0, 1, 2, 255};
    static const uint32_t ap_config[] = {0, 1, 2, UINT32_MAX};
    struct b41_second_config base = base_config(), out;
    for (unsigned build = 0; build < 3; ++build) {
        struct b41_receiver_property_owner p = {0};
        reset(types[build], build ? "1" : "0");
        assert(b41_receiver_properties_collect(&p) == 0 && calls == 2);
        for (unsigned flags = 0; flags < 256; ++flags)
            for (unsigned second = 0; second < 4; ++second)
                for (unsigned restart = 0; restart < 4; ++restart) {
                    struct b41_receiver_log_sources s = {(uint8_t)flags, secondary[second], ap_config[restart]};
                    uint8_t expected = !s.secondary_policy_de3c0 && s.ap_config_init_884c4 == 1 ?
                        (uint8_t)(flags & 0xfeu) : (uint8_t)flags;
                    assert(b41_receiver_policy_apply(&base, &p, &s, &out) == 1);
                    assert(out.bytes[4] == expected && out.provenance[4] == B41_RUNTIME_PROVENANCE);
                    assert(out.bytes[0xc8] == build);
                    for (unsigned i = 0xc9; i < 0xcc; ++i) assert(out.bytes[i] == 0);
                    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i) {
                        if (i == 4 || (i >= 0xc8 && i < 0xcc)) continue;
                        assert(out.bytes[i] == base.bytes[i] && out.provenance[i] == base.provenance[i]);
                    }
                    assert(out.missing_inputs == (base.missing_inputs & ~B41_SECOND_BUILD_POLICY));
                    assert(out.unresolved_bytes == B41_SECOND_CONFIG_SIZE - 6);
                    assert(out.receiver_owner_missing == 3 && out.stop_contract_missing == 5 && out.mpe_schema_missing == 7);
                    struct b41_second_config again = out;
                    assert(b41_receiver_policy_apply(&again, &p, &s, &again) == 1);
                    assert(!memcmp(&again, &out, sizeof(out)));
                }
        assert(calls == 2); /* Config construction never rereads properties. */
    }
}

static void rejection(void)
{
    static const char *const types[] = {"eng", "userdebug", "unknown", "user-debug", "userdebugx", "engx", "userx"};
    struct b41_receiver_log_sources s = {0xff, 0, 1};
    struct b41_receiver_property_owner p;
    struct b41_second_config base = base_config(), out, before;
    memset(&out, 0x5a, sizeof(out)); before = out;
    for (unsigned i = 0; i < sizeof(types) / sizeof(types[0]); ++i) {
        memset(&p, 0, sizeof(p)); reset(types[i], "0");
        assert(b41_receiver_properties_collect(&p) == 0);
        assert(b41_receiver_policy_apply(&base, &p, &s, &out) == -EINVAL);
        assert(!memcmp(&out, &before, sizeof(out)));
    }
    memset(&p, 0, sizeof(p)); reset("eng", "01");
    assert(b41_receiver_properties_collect(&p) == 0);
    assert(b41_receiver_policy_apply(&base, &p, &s, &out) == -EINVAL);
    memset(&p, 0, sizeof(p)); reset("user", "1");
    assert(b41_receiver_properties_collect(&p) == 0); /* user ignores debug contents. */
    for (unsigned index = 0; index < 5; ++index) {
        unsigned offset = index ? 0xc7 + index : 4;
        struct b41_second_config conflict = base;
        conflict.provenance[offset] = B41_SECOND_BUILD_RESULT;
        conflict.bytes[offset] = 0x55;
        assert(b41_receiver_policy_apply(&conflict, &p, &s, &out) == -ESTALE);
        assert(!memcmp(&out, &before, sizeof(out)));
    }
    for (unsigned mode = 0; mode < 6; ++mode) {
        struct b41_receiver_property_owner invalid = p;
        if (mode == 0) invalid.entered = 0;
        if (mode == 1) invalid.collected = 1;
        if (mode == 2) invalid.lengths[0] = SIZE_MAX;
        if (mode == 3) invalid.build_type[invalid.lengths[0]] = 'x';
        if (mode == 4) invalid.first_error = -EIO;
        if (mode == 5) invalid.first_error = 1;
        int expected = mode == 4 ? -EIO : mode == 5 ? -EPROTO : -ENODATA;
        assert(b41_receiver_policy_apply(&base, &invalid, &s, &out) == expected);
        assert(!memcmp(&out, &before, sizeof(out)));
    }
    assert(b41_receiver_policy_apply(NULL, &p, &s, &out) == -EINVAL);
    assert(b41_receiver_policy_apply(&base, NULL, &s, &out) == -EINVAL);
    assert(b41_receiver_policy_apply(&base, &p, NULL, &out) == -EINVAL);
    assert(b41_receiver_policy_apply(&base, &p, &s, NULL) == -EINVAL);
    assert(!memcmp(&out, &before, sizeof(out)));
}

static void native_boundary(void)
{
    char value[B41_RECEIVER_PROPERTY_MAX] = {0};
    assert(__real_b41_receiver_property_read(NULL, value) == -EINVAL);
    assert(__real_b41_receiver_property_read("ro.build.type", NULL) == -EINVAL);
    assert(__real_b41_receiver_property_read("not.a.pinned.key", value) == -EINVAL);
#if defined(__BIONIC__)
    reset("userdebug", "1");
    assert(__real_b41_receiver_property_read("ro.build.type", value) == 9);
    assert(!strcmp(value, "userdebug"));
    assert(__real_b41_receiver_property_read("ro.debuggable", value) == 1);
    reset("", "0");
    assert(__real_b41_receiver_property_read("ro.build.type", value) == -ENODATA);
#else
    assert(__real_b41_receiver_property_read("ro.build.type", value) == -EOPNOTSUPP);
#endif
}

int main(void)
{
    owner_failures(); matrix(); rejection(); native_boundary();
    puts("PASS: receiver property ownership, 12288 policy vectors, immutable rejection; INIT remains gated");
    return 0;
}
