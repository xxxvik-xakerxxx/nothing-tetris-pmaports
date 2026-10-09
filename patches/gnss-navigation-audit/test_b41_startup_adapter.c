/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "b41_startup_adapter.h"

static struct b41_host_adapter adapter;

static void configuration(void)
{
    struct b41_startup_config config, before;
    char long_path[129];
    b41_startup_config_init(&config);
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        assert(!config.resolved_second[i]);
    assert(b41_startup_set_build_policy(&config, "user", "0") == 0);
    assert(config.second[0xc8] == 0);
    assert(b41_startup_set_build_policy(&config, "eng", "1") == 0);
    assert(config.second[0xc8] == 1);
    assert(b41_startup_set_build_policy(&config, "userdebug", "1") == 0);
    assert(config.second[0xc8] == 2);
    before = config;
    assert(b41_startup_set_build_policy(&config, "eng", "0") == -EINVAL);
    assert(b41_startup_set_build_policy(&config, "userdebug", "01") == -EINVAL);
    assert(b41_startup_set_build_policy(&config, "unknown", "1") == -EINVAL);
    assert(!memcmp(&config, &before, sizeof(config)));
    assert(b41_startup_set_callback_output(&config) == 0);
    assert(!memcmp(config.second + 0x1cc, "UseCallback\0", 12));
    assert(!config.resolved_second[0x1cb] && !config.resolved_second[0x1ea]);
    assert(b41_startup_set_b41_identity(&config) == 0);
    assert(!strcmp((char *)config.second + 0x46, "MTK_MNLD_14_1.00"));
    const uint8_t magic[] = {0xce, 0, 6, 0, 0x55, 0xaa, 2, 1};
    assert(!memcmp(config.second + 0xcc, magic, sizeof(magic)));
    const unsigned offsets[] = {0xd4, 0xf2, 0x110, 0x190, 0x1ae, 0x1ea,
        0x208, 0x226, 0x256, 0x286, 0x2b6, 0x2e6, 0x316, 0x346,
        0x376, 0x3a6, 0x3d6, 0x406, 0x424};
    for (unsigned i = 0; i < sizeof(offsets) / sizeof(offsets[0]); ++i) {
        assert(b41_startup_set_path(&config, offsets[i], "/tmp/gps") == 0);
        assert(!strcmp((char *)config.second + offsets[i], "/tmp/gps"));
    }
    before = config;
    memset(long_path, 'x', sizeof(long_path));
    long_path[0] = '/';
    long_path[128] = 0;
    assert(b41_startup_set_path(&config, 0x110, long_path) == -ENAMETOOLONG);
    assert(b41_startup_set_path(&config, 0x1cc, "/tmp") == -EINVAL);
    assert(b41_startup_set_path(&config, 0xd4, "relative") == -EINVAL);
    assert(!memcmp(&config, &before, sizeof(config)));
    assert(b41_startup_missing_contracts() == 0x7b);
    assert(!(b41_startup_missing_contracts() & B41_MISSING_CALLBACK_ABI));
    /* A populated path/marker fragment cannot claim a complete configuration. */
    assert(!config.resolved_second[0x0] && !config.resolved_second[0x70]);
}

int main(int argc, char **argv)
{
    struct b41_known_callbacks callbacks = {0}, rejected = {0};
    struct b41_host_event event;
    char bytes[] = {'$', 'G', 'N', 0, 'x'};
    configuration();
    assert(argc == 2);
    assert(b41_host_adapter_init(NULL) == -EINVAL);
    assert(b41_host_adapter_init(&adapter) == 0);
    assert(b41_host_adapter_bind(NULL, &callbacks) == -EINVAL);
    assert(b41_host_adapter_bind(&adapter, &callbacks) == 0);
    assert(b41_host_adapter_init(&adapter) == -EALREADY);
    assert(b41_host_adapter_bind(&adapter, &rejected) == -EALREADY);
    assert(!rejected.output && !rejected.frame_sleep && !rejected.frame_network);
    assert(b41_host_adapter_take(&adapter, &event) == -EAGAIN);
    if (!strcmp(argv[1], "busy")) {
        assert(!atomic_flag_test_and_set(&adapter.lock));
        assert(callbacks.output(bytes, sizeof(bytes)) == -EBUSY);
        atomic_flag_clear(&adapter.lock);
        assert(callbacks.frame_network() == -EBUSY);
        assert(b41_host_adapter_error(&adapter) == -EBUSY);
    } else if (!strcmp(argv[1], "oversize")) {
        assert(callbacks.output(bytes, B41_HOST_OUTPUT_MAX + 1) == -EMSGSIZE);
        assert(callbacks.frame_sleep(1) == -EMSGSIZE);
        assert(!adapter.count);
    } else if (!strcmp(argv[1], "invalid")) {
        assert(callbacks.output(NULL, 1) == -EMSGSIZE);
        assert(callbacks.output(bytes, 0) == -EMSGSIZE);
        assert(!adapter.count);
    } else if (!strcmp(argv[1], "unsupported")) {
        assert(callbacks.notify(3) == -EOPNOTSUPP);
        assert(callbacks.agps(15, 1, NULL) == -EOPNOTSUPP);
        assert(b41_host_adapter_error(&adapter) == -EOPNOTSUPP);
        assert(!adapter.count);
    } else if (!strcmp(argv[1], "full")) {
        for (unsigned i = 0; i < B41_HOST_QUEUE_SIZE; ++i)
            assert(callbacks.output(bytes, sizeof(bytes)) == 0);
        assert(callbacks.frame_network() == -ENOBUFS);
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(callbacks.output(bytes, sizeof(bytes)) == -ENOBUFS);
        assert(b41_host_adapter_error(&adapter) == -ENOBUFS);
    } else {
        assert(!strcmp(argv[1], "normal"));
        assert(callbacks.output(bytes, sizeof(bytes)) == 0);
        memset(bytes, 'z', sizeof(bytes));
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(event.kind == B41_HOST_OUTPUT && event.length == 5);
        assert(!memcmp(event.bytes, "$GN\0x", 5));
        assert(event.bytes[5] == 0);
        const unsigned noop_events[] = {1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 14, UINT32_MAX};
        for (unsigned i = 0; i < sizeof(noop_events) / sizeof(noop_events[0]); ++i)
            assert(callbacks.notify(noop_events[i]) == 0);
        assert(callbacks.passthrough(UINT32_MAX) == UINT32_MAX);
        uint8_t plain[256], encoded[256], decoded[256];
        for (unsigned i = 0; i < sizeof(plain); ++i)
            plain[i] = (uint8_t)i;
        assert(callbacks.encode(plain, encoded, sizeof(plain)) == sizeof(plain));
        for (unsigned i = 0; i < sizeof(plain); ++i)
            assert(encoded[i] == (uint8_t)(((i >> 2) | (i << 6)) ^ 0x63));
        assert(callbacks.decode(decoded, encoded, sizeof(encoded)) == sizeof(encoded));
        assert(!memcmp(plain, decoded, sizeof(plain)));
        assert(callbacks.encode(NULL, NULL, 0) == 0);
        assert(callbacks.app_output(bytes, sizeof(bytes)) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(event.kind == B41_HOST_APP_OUTPUT);
        assert(callbacks.agps(0, sizeof(bytes), bytes) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(event.kind == B41_HOST_AGPS_DATA);
        assert(callbacks.frame_measurement(UINT32_MAX) == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(event.kind == B41_HOST_FRAME_MEASUREMENT);
        assert(!memcmp(event.bytes, "$PMTK736,1,-1*", 14));
        assert(event.bytes[event.length - 2] == '\r' && event.bytes[event.length - 1] == '\n');
        uint8_t maximum[B41_HOST_OUTPUT_MAX];
        memset(maximum, 0xa5, sizeof(maximum));
        assert(callbacks.output(maximum, sizeof(maximum)) == 0);
        memset(maximum, 0, sizeof(maximum));
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(event.length == B41_HOST_OUTPUT_MAX);
        for (unsigned i = 0; i < sizeof(maximum); ++i)
            assert(event.bytes[i] == 0xa5);
        for (unsigned i = 0; i < 259; ++i) {
            char expected[32];
            size_t length;
            uint32_t value = i == 258 ? UINT32_MAX : i;
            assert(callbacks.frame_sleep(value) == 0);
            assert(b41_host_adapter_take(&adapter, &event) == 0);
            assert(b41_frame_sync_encode(3, value, expected, sizeof(expected), &length) == 0);
            assert(event.kind == B41_HOST_FRAME_SLEEP && event.length == length);
            assert(!memcmp(event.bytes, expected, length));
        }
        assert(callbacks.frame_network() == 0);
        assert(b41_host_adapter_take(&adapter, &event) == 0);
        assert(event.kind == B41_HOST_FRAME_NETWORK);
        assert(event.bytes[event.length - 1] == '\r');
        assert(!adapter.count && !b41_host_adapter_error(&adapter));
        for (unsigned i = 0; i < 40; ++i) {
            assert(callbacks.output(bytes, sizeof(bytes)) == 0);
            assert(b41_host_adapter_take(&adapter, &event) == 0);
        }
    }
    printf("PASS: B4.1 startup adapter %s (host-only, no vendor API)\n", argv[1]);
    return 0;
}
