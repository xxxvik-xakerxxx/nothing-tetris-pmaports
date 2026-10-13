/* SPDX-License-Identifier: GPL-2.0-only */
#include "bootstrap.h"

#include <string.h>

_Static_assert(sizeof(struct b41_bootstrap_boot_info) == 20u, "ioctl boot info ABI");
_Static_assert(offsetof(struct b41_bootstrap_boot_info, cipher_key) == 12u,
               "private key offset in ioctl output");
_Static_assert(offsetof(struct b41_bootstrap_boot_info, frag_num) == 16u,
               "fragment count offset in ioctl output");

static void forget(uint8_t *bytes, size_t length)
{
    volatile uint8_t *private_bytes = bytes;

    while (length != 0) {
        *private_bytes++ = 0;
        --length;
    }
}

static void write16(uint8_t *bytes, uint32_t word)
{
    bytes[0] = (uint8_t)word;
    bytes[1] = (uint8_t)(word >> 8);
}

static int overlaps(const void *first, size_t first_size,
                     const void *second, size_t second_size)
{
    uintptr_t a = (uintptr_t)first;
    uintptr_t b = (uintptr_t)second;

    if (first == NULL || second == NULL || first_size == 0 || second_size == 0)
        return 0;
    return a <= b ? b - a < first_size : a - b < second_size;
}

int b41_bootstrap_route_select(const struct b41_bootstrap_selectors *selectors,
                               struct b41_bootstrap_route *out)
{
    struct b41_bootstrap_route route;

    if (selectors == NULL || out == NULL)
        return B41_BOOTSTRAP_ARGUMENT;
    if (overlaps(selectors, sizeof(*selectors), out, sizeof(*out)))
        return B41_BOOTSTRAP_OVERLAP;
    if (selectors->secure_download_7178b8_33e == 0)
        return B41_BOOTSTRAP_EMBEDDED_IMAGE;
    /* 4f2268..4f227c /4f32a8..4f32c4: unsigned low-byte decrement. */
    route.metadata_ioctl = (uint8_t)((uint8_t)(selectors->dsp_selector_717cb0 - 1u) <
                                    0x3fu ? 24u : 23u);
    route.fragment_ioctl = (uint8_t)(route.metadata_ioctl + 2u);
    *out = route;
    return B41_BOOTSTRAP_OK;
}

static int validate(const struct b41_bootstrap_session *session,
                     const struct b41_bootstrap_query *query)
{
    struct b41_bootstrap_route route;
    const struct b41_bootstrap_boot_info *info;
    int status;

    if (session == NULL || query == NULL || session->fields == NULL)
        return B41_BOOTSTRAP_MISSING;
    status = b41_bootstrap_route_select(&session->selectors, &route);
    if (status != 0)
        return status;
    if (session->gps0_fd < 0 || query->session != session ||
        query->gps0_fd != session->gps0_fd ||
        query->selectors.secure_download_7178b8_33e !=
            session->selectors.secure_download_7178b8_33e ||
        query->selectors.dsp_selector_717cb0 != session->selectors.dsp_selector_717cb0)
        return B41_BOOTSTRAP_SESSION;
    if (query->command != route.metadata_ioctl)
        return B41_BOOTSTRAP_QUERY;
    if (query->status < 0)
        return query->status;
    if (query->status != 0)
        return B41_BOOTSTRAP_QUERY;
    if (query->info == NULL || query->bytes_returned != sizeof(*query->info))
        return B41_BOOTSTRAP_MISSING;
    info = query->info;
    /* ATF unpacks five unsigned16 fields into this u32 ABI. Enforce its shape;
     * don't silently truncate an unrelated or stale descriptor. Positive size
     * and count are host preflight: stock lacks that check. The last submitted
     * argument is count-1, bounded by the pinned kernel's inclusive256 limit.
     */
    if (info->code_size == 0 || info->code_size > UINT16_MAX ||
        info->start_addr > UINT16_MAX || info->exec_addr > UINT16_MAX ||
        info->cipher_key > UINT16_MAX || info->frag_num == 0 || info->frag_num - 1u > 256u)
        return B41_BOOTSTRAP_METADATA;
    return B41_BOOTSTRAP_OK;
}

static int overlaps_inputs(const void *output, size_t length,
                            const struct b41_bootstrap_session *session,
                            const struct b41_bootstrap_query *query)
{
    const struct b41_mvcd_bootstrap_inputs *fields = session->fields;
    size_t name_size = fields->feature_name_size < 0x296u ?
                       fields->feature_name_size : 0x296u;

    return overlaps(output, length, session, sizeof(*session)) ||
           overlaps(output, length, query, sizeof(*query)) ||
           overlaps(output, length, query->info, sizeof(*query->info)) ||
           overlaps(output, length, fields, sizeof(*fields)) ||
           overlaps(output, length, fields->feature_name, name_size) ||
           overlaps(output, length, fields->private_clock, sizeof(*fields->private_clock));
}

static void profile_block(uint32_t context_hz, uint8_t bytes[32])
{
    static const struct { uint32_t low, count; } windows[] = {
        {11999976u, 49u}, {15999968u, 65u}, {19199962u, 77u},
        {19999960u, 81u}, {23999952u, 97u}, {25999948u, 105u},
        {31999936u, 129u}, {38399924u, 153u}, {39999920u, 161u},
        {51999896u, 209u}
    };
    /* 27934: all ten records have identical first16 decoded halfwords.
     * 4f35e8..4f362c uses byte1 of words5..8, low16 of the other words.
     * The remaining two table words never enter payload62..93.
     */
    static const uint16_t common[16] = {
        40, 255, 128, 71, 100, 80, 216, 80, 187, 3, 60, 111, 137, 136, 2, 251
    };

    for (size_t row = 0; row < sizeof(windows) / sizeof(windows[0]); ++row) {
        if (context_hz - windows[row].low < windows[row].count) {
            for (size_t word = 0; word < sizeof(common) / sizeof(common[0]); ++word)
                write16(bytes + 2u * word, common[word]);
            return;
        }
    }
    /* 4f20c0/4f20c4 zeros survive only the no-matching-frequency path. */
    memset(bytes, 0, 32);
}

static int assemble(const struct b41_bootstrap_session *session,
                     const struct b41_bootstrap_query *query,
                     uint8_t payload[B41_MVCD_BOOTSTRAP_SIZE])
{
    int status;

    /* The only zero ranges retained after fields_apply are source stores:
     * sequence2..3, c4/c0 ->10..11, dc/d8 ->12..13, f4/f0 ->24..25.
     * 62..93 is filled separately from the immutable frequency table.
     */
    memset(payload, 0, B41_MVCD_BOOTSTRAP_SIZE);
    status = b41_mvcd_bootstrap_fields_apply(session->fields, payload,
                                            B41_MVCD_BOOTSTRAP_SIZE);
    if (status != 0)
        return status;
    write16(payload, 0x1au);
    write16(payload + 14, query->info->code_size);
    write16(payload + 16, query->info->start_addr);
    write16(payload + 18, query->info->exec_addr);
    write16(payload + 20, query->info->cipher_key);
    write16(payload + 22, query->info->frag_num);
    /* 4f2734/4f273c: LE32(00050000), not a native pointer. */
    payload[28] = 5;
    /* 4f213c loads the ORIGINAL context frequency, not the helper override. */
    profile_block(session->fields->context_hz_18, payload + 62);
    return B41_BOOTSTRAP_OK;
}

int b41_bootstrap_payload_build(const struct b41_bootstrap_session *session,
                                const struct b41_bootstrap_query *query,
                                uint8_t *payload, size_t capacity)
{
    uint8_t private_payload[B41_MVCD_BOOTSTRAP_SIZE];
    int status;

    if (payload == NULL)
        return B41_BOOTSTRAP_ARGUMENT;
    if (capacity < sizeof(private_payload))
        return B41_BOOTSTRAP_CAPACITY;
    status = validate(session, query);
    if (status != 0)
        return status;
    if (overlaps_inputs(payload, sizeof(private_payload), session, query))
        return B41_BOOTSTRAP_OVERLAP;
    status = assemble(session, query, private_payload);
    if (status == 0)
        memcpy(payload, private_payload, sizeof(private_payload));
    forget(private_payload, sizeof(private_payload));
    return status;
}

int b41_bootstrap_frame_build(const struct b41_bootstrap_session *session,
                              const struct b41_bootstrap_query *query,
                              uint8_t *frame, size_t capacity, size_t *written)
{
    uint8_t private_payload[B41_MVCD_BOOTSTRAP_SIZE];
    int status;

    if (frame == NULL || written == NULL)
        return B41_BOOTSTRAP_ARGUMENT;
    if (capacity < B41_MVCD_BOOTSTRAP_FRAME_SIZE)
        return B41_BOOTSTRAP_CAPACITY;
    status = validate(session, query);
    if (status != 0)
        return status;
    if (overlaps(frame, B41_MVCD_BOOTSTRAP_FRAME_SIZE, written, sizeof(*written)) ||
        overlaps_inputs(frame, B41_MVCD_BOOTSTRAP_FRAME_SIZE, session, query) ||
        overlaps_inputs(written, sizeof(*written), session, query))
        return B41_BOOTSTRAP_OVERLAP;
    status = assemble(session, query, private_payload);
    if (status == 0)
        status = b41_mvcd_encode_bootstrap(private_payload, sizeof(private_payload),
                                          frame, capacity, written);
    forget(private_payload, sizeof(private_payload));
    return status;
}
