/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_slot6_service.h"
#include <errno.h>
#include <string.h>
static _Atomic(struct b41_host_adapter *) bound;

static uint32_t word(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
        (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static int fail(struct b41_host_adapter *a, int error)
{
    int expected = 0;
    if (!atomic_compare_exchange_strong(&a->first_error, &expected, error))
        return expected;
    return error;
}
static int32_t callback(uint32_t selector, uint32_t parameter, const void *pointer)
{
    struct b41_host_adapter *a = atomic_load(&bound);
    uint8_t packet[B41_HOST_OUTPUT_MAX];
    size_t length = 0, written;
    int status;
    if (!a) return -ENODEV;
    status = atomic_load(&a->first_error);
    if (status) return status;
    selector &= 0xffffu;
    if (selector == 0) {
        if (!(parameter & 0xffffu)) return 0; /* No pointer access or send. */
        if (pointer) {
            const uint8_t *s = pointer;
            /* Engine supplies a valid terminated string. No guessed length,
             * truncated packet or asynchronous retained vendor pointer.
             */
            while (length <= B41_HOST_OUTPUT_MAX - 14u && s[length]) ++length;
            if (length > B41_HOST_OUTPUT_MAX - 14u) return fail(a, -EMSGSIZE);
        }
        status = b41_agps_data_packet(pointer, length, packet, sizeof(packet), &written);
    } else if (selector == 1) {
        status = b41_agps_selector1_packet(packet, sizeof(packet), &written);
    } else return fail(a, -EOPNOTSUPP);
    if (status) return fail(a, status);
    if (atomic_flag_test_and_set_explicit(&a->lock, memory_order_acquire))
        return fail(a, -EBUSY);
    if (a->count == B41_HOST_QUEUE_SIZE) {
        atomic_flag_clear_explicit(&a->lock, memory_order_release);
        return fail(a, -ENOBUFS);
    }
    struct b41_host_event *event = &a->events[(a->head + a->count) % B41_HOST_QUEUE_SIZE];
    event->kind = B41_HOST_AGPS_DATA;
    event->length = (uint32_t)written;
    memcpy(event->bytes, packet, written);
    ++a->count;
    atomic_flag_clear_explicit(&a->lock, memory_order_release);
    return 0;
}
int b41_slot6_service_bind(struct b41_host_adapter *a, struct b41_known_callbacks *c)
{
    if (!a || !c || !c->agps) return -EINVAL;
    int status = b41_host_adapter_error(a);
    if (status) return status;
    struct b41_host_adapter *expected = NULL;
    if (!atomic_compare_exchange_strong(&bound, &expected, a)) return -EALREADY;
    c->agps = callback;
    return 0;
}
int b41_slot6_service_dispatch(struct b41_agps_owner *ipc, const struct b41_host_event *event)
{
    if (!event) return -EINVAL;
    if (event->kind != B41_HOST_AGPS_DATA) return b41_navigation_dispatch_event(ipc, event);
    if (event->length < 8 || event->length > B41_HOST_OUTPUT_MAX || word(event->bytes) != 1)
        return -EBADMSG;
    uint32_t type = word(event->bytes + 4);
    if (type == 152) {
        if (event->length != 8) return -EBADMSG;
        return b41_agps_owner_send_selector1(ipc);
    }
    if (type != 150 || event->length < 9) return -EBADMSG;
    if (!event->bytes[8]) {
        if (event->length != 9) return -EBADMSG;
        return b41_agps_owner_send_data(ipc, NULL, 0);
    }
    if (event->bytes[8] != 1 || event->length < 14) return -EBADMSG;
    uint32_t size = word(event->bytes + 9);
    if (!size || size != event->length - 13u || event->bytes[event->length - 1] ||
        memchr(event->bytes + 13, 0, size - 1u)) return -EBADMSG;
    return b41_agps_owner_send_data(ipc, event->bytes + 13, size - 1u);
}
