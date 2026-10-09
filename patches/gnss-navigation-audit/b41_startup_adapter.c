/* SPDX-License-Identifier: GPL-2.0-only */
#include <errno.h>
#include <string.h>
#include "b41_startup_adapter.h"
#include "b41_byte_codec.h"

static _Atomic(struct b41_host_adapter *) bound_adapter;

_Static_assert(sizeof(((struct b41_startup_config *)0)->first) == 0x70,
               "B4.1 first config copy extent");
_Static_assert(sizeof(((struct b41_startup_config *)0)->second) == 0x444,
               "B4.1 second config copy extent");

void b41_startup_config_init(struct b41_startup_config *config)
{
    if (config)
        memset(config, 0, sizeof(*config));
}

static size_t path_capacity(unsigned offset)
{
    switch (offset) {
    case 0xd4: case 0xf2: case 0x190: case 0x1ae: case 0x1ea:
    case 0x208: case 0x406: case 0x424:
        return 30;
    case 0x110:
        return 128;
    case 0x226: case 0x256: case 0x286: case 0x2b6: case 0x2e6:
    case 0x316: case 0x346: case 0x376: case 0x3a6: case 0x3d6:
        return 48;
    default:
        return 0;
    }
}

int b41_startup_set_path(struct b41_startup_config *config, unsigned offset,
                         const char *path)
{
    size_t capacity = path_capacity(offset), length = 0;
    if (!config || !path || !capacity || path[0] != '/')
        return -EINVAL;
    while (length < capacity && path[length])
        ++length;
    /* Never silently truncate two distinct files to the same vendor path. */
    if (length == capacity)
        return -ENAMETOOLONG;
    memset(config->second + offset, 0, capacity);
    memcpy(config->second + offset, path, length);
    memset(config->resolved_second + offset, 1, capacity);
    return 0;
}

int b41_startup_set_callback_output(struct b41_startup_config *config)
{
    if (!config)
        return -EINVAL;
    memset(config->second + 0x1cc, 0, 30);
    memcpy(config->second + 0x1cc, "UseCallback", 11);
    memset(config->resolved_second + 0x1cc, 1, 30);
    return 0;
}

int b41_startup_set_b41_identity(struct b41_startup_config *config)
{
    static const uint16_t magic[] = {0xce, 6, 0xaa55, 0x102};
    if (!config)
        return -EINVAL;
    memset(config->second + 0x46, 0, 30);
    memcpy(config->second + 0x46, "MTK_MNLD_14_1.00",
           sizeof("MTK_MNLD_14_1.00") - 1);
    memset(config->resolved_second + 0x46, 1, 30);
    for (unsigned i = 0; i < 4; ++i) {
        config->second[0xcc + 2 * i] = (uint8_t)magic[i];
        config->second[0xcd + 2 * i] = (uint8_t)(magic[i] >> 8);
    }
    memset(config->resolved_second + 0xcc, 1, 8);
    return 0;
}

int b41_startup_set_build_policy(struct b41_startup_config *config,
                                const char *build_type, const char *debuggable)
{
    uint32_t value;
    if (!config || !build_type || !debuggable)
        return -EINVAL;
    if (!strcmp(build_type, "user"))
        value = 0;
    else if (!strcmp(build_type, "eng") && !strcmp(debuggable, "1"))
        value = 1;
    else if (!strcmp(build_type, "userdebug") && !strcmp(debuggable, "1"))
        value = 2;
    else
        return -EINVAL;
    for (unsigned i = 0; i < 4; ++i)
        config->second[0xc8 + i] = (uint8_t)(value >> (i * 8));
    memset(config->resolved_second + 0xc8, 1, 4);
    return 0;
}

unsigned b41_startup_missing_contracts(void)
{
    /* These are code-audit gates, not caller-set permission bits. Do not
     * expose mnl_run until every mandatory ABI and owner has been recovered.
     */
    return B41_MISSING_FIRST_CONFIG | B41_MISSING_SECOND_POLICY |
           B41_MISSING_TRANSPORT_OWNER | B41_MISSING_HOST_SERVICES |
           B41_MISSING_AGPS_RECEIVER | B41_MISSING_STOP_CONTRACT;
}

int b41_host_adapter_init(struct b41_host_adapter *adapter)
{
    if (!adapter)
        return -EINVAL;
    if (atomic_load(&bound_adapter) == adapter)
        return -EALREADY;
    adapter->head = adapter->count = 0;
    adapter->lock = (atomic_flag)ATOMIC_FLAG_INIT;
    atomic_init(&adapter->first_error, 0);
    return 0;
}

static int fail(struct b41_host_adapter *adapter, int error)
{
    int expected = 0;
    if (adapter && !atomic_compare_exchange_strong(&adapter->first_error,
                                                   &expected, error))
        return expected;
    return error;
}

static int enqueue(enum b41_host_event_kind kind, const void *bytes, uint32_t length)
{
    struct b41_host_adapter *adapter = atomic_load(&bound_adapter);
    struct b41_host_event *event;
    if (!adapter)
        return -ENODEV;
    int previous = atomic_load(&adapter->first_error);
    if (previous)
        return previous;
    if (!bytes || !length || length > B41_HOST_OUTPUT_MAX)
        return fail(adapter, -EMSGSIZE);
    if (atomic_flag_test_and_set_explicit(&adapter->lock, memory_order_acquire))
        return fail(adapter, -EBUSY);
    if (adapter->count == B41_HOST_QUEUE_SIZE) {
        atomic_flag_clear_explicit(&adapter->lock, memory_order_release);
        return fail(adapter, -ENOBUFS);
    }
    event = &adapter->events[(adapter->head + adapter->count) % B41_HOST_QUEUE_SIZE];
    event->kind = kind;
    event->length = length;
    memcpy(event->bytes, bytes, length);
    ++adapter->count;
    atomic_flag_clear_explicit(&adapter->lock, memory_order_release);
    return 0;
}

static int32_t output(const void *bytes, uint32_t length)
{
    return enqueue(B41_HOST_OUTPUT, bytes, length);
}

static int32_t app_output(const void *bytes, uint32_t length)
{
    return enqueue(B41_HOST_APP_OUTPUT, bytes, length);
}

static int32_t notify(uint32_t event)
{
    /* Pinned14-entry producer table: only0/3/7/13 have active handlers.
     * Those handlers obtain engine information, persist NV and send IPC;
     * merely recording a notification is not successful implementation.
     */
    if (event == 0 || event == 3 || event == 7 || event == 13)
        return fail(atomic_load(&bound_adapter), -EOPNOTSUPP);
    return 0;
}

static int32_t agps(uint32_t selector, uint32_t parameter, const void *bytes)
{
    /* Only the type0 borrowed-data contract is implemented. For other types,
     * parameter may be a control value rather than a payload byte count.
     * Do not dereference their pointers using a guessed length convention.
     */
    if (selector != 0)
        return fail(atomic_load(&bound_adapter), -EOPNOTSUPP);
    return enqueue(B41_HOST_AGPS_DATA, bytes, parameter);
}

static uint32_t passthrough(uint32_t value)
{
    /* mnld5d910 is exactly RET; libmnl caller542008 supplies w0. */
    return value;
}

static uint32_t codec(const void *src, void *dst, uint32_t count, int decode)
{
    if (count > B41_HOST_OUTPUT_MAX ||
        b41_byte_codec(src, count, dst, count, count, decode)) {
        fail(atomic_load(&bound_adapter), -EMSGSIZE);
        return UINT32_MAX;
    }
    return count;
}

static uint32_t encode(const void *src, void *dst, uint32_t count)
{
    return codec(src, dst, count, 0);
}

static uint32_t decode(void *dst, const void *src, uint32_t count)
{
    return codec(src, dst, count, 1);
}

static int32_t frame(unsigned slot, uint32_t value)
{
    char bytes[32];
    size_t length;
    if (b41_frame_sync_encode(slot, value, bytes, sizeof(bytes), &length))
        return fail(atomic_load(&bound_adapter), -EINVAL);
    return enqueue(slot == 3 ? B41_HOST_FRAME_SLEEP :
                   slot == 4 ? B41_HOST_FRAME_NETWORK : B41_HOST_FRAME_MEASUREMENT,
                   bytes, (uint32_t)length);
}

static int32_t frame_sleep(uint32_t value) { return frame(3, value); }
static int32_t frame_network(void) { return frame(4, 0); }
static int32_t frame_measurement(uint32_t value) { return frame(5, value); }

int b41_host_adapter_bind(struct b41_host_adapter *adapter,
                          struct b41_known_callbacks *callbacks)
{
    struct b41_host_adapter *expected = NULL;
    if (!adapter || !callbacks)
        return -EINVAL;
    if (!atomic_compare_exchange_strong(&bound_adapter, &expected, adapter))
        return -EALREADY;
    callbacks->output = output;
    callbacks->notify = notify;
    callbacks->app_output = app_output;
    callbacks->frame_sleep = frame_sleep;
    callbacks->frame_network = frame_network;
    callbacks->frame_measurement = frame_measurement;
    callbacks->agps = agps;
    callbacks->passthrough = passthrough;
    callbacks->encode = encode;
    callbacks->decode = decode;
    return 0;
}

int b41_host_adapter_take(struct b41_host_adapter *adapter,
                          struct b41_host_event *event)
{
    if (!adapter || !event)
        return -EINVAL;
    if (atomic_flag_test_and_set_explicit(&adapter->lock, memory_order_acquire))
        return -EBUSY;
    if (!adapter->count) {
        atomic_flag_clear_explicit(&adapter->lock, memory_order_release);
        return -EAGAIN;
    }
    memset(event, 0, sizeof(*event));
    event->kind = adapter->events[adapter->head].kind;
    event->length = adapter->events[adapter->head].length;
    memcpy(event->bytes, adapter->events[adapter->head].bytes, event->length);
    adapter->head = (adapter->head + 1) % B41_HOST_QUEUE_SIZE;
    --adapter->count;
    atomic_flag_clear_explicit(&adapter->lock, memory_order_release);
    return 0;
}

int b41_host_adapter_error(const struct b41_host_adapter *adapter)
{
    return adapter ? atomic_load(&adapter->first_error) : -EINVAL;
}
