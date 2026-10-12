/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_agps_receiver.h"
#include "../b41_native_receiver_host.h"
#include <errno.h>
#include <string.h>

#if defined(__aarch64__) && defined(__BIONIC__)
static int live_primary(const struct b41_library_association *image)
{
    struct b41_native_thread_record record;
    uintptr_t flag;
    unsigned offload;
    if (!image || !image->base || image->extent != B41_LIBRARY_IMAGE_END ||
        image->base > UINTPTR_MAX - B41_LIBRARY_IMAGE_END) return -EINVAL;
    memcpy(&flag, (const void *)(image->base + 0x6e6d00u), sizeof(flag));
    if (flag != image->base + 0x6fa3d8u) return -ESTALE;
    memcpy(&offload, (const void *)flag, sizeof(offload));
    if (offload) return -EOPNOTSUPP;
    memcpy(&record, (const void *)(image->base + 0x6edef0u), sizeof(record));
    if (record.index || record.stop != image->base + 0x529f18u ||
        record.wake != image->base + 0x529418u) return -ESTALE;
    if (record.marker < 0 || record.handle == UINT64_MAX) return -ENODATA;
    return 0;
}
#endif

int b41_agps_native_associate(const void *elf, size_t size,
    const struct b41_library_view *view, struct b41_library_association *out)
{
#if !defined(__aarch64__) || !defined(__BIONIC__)
    (void)elf; (void)size; (void)view; (void)out;
    return -EOPNOTSUPP;
#else
    struct b41_library_association image;
    if (!out) return -EINVAL;
    int status = b41_library_associate(elf, size, view, &image);
    if (!status) *out = image;
    return status;
#endif
}

int b41_agps_native_admit(const struct b41_library_association *image)
{
#if !defined(__aarch64__) || !defined(__BIONIC__)
    (void)image;
    return -EOPNOTSUPP;
#else
    return live_primary(image);
#endif
}

int b41_agps_native_deliver(const struct b41_library_association *image,
                          const struct b41_agps_request *request)
{
#if !defined(__aarch64__) || !defined(__BIONIC__)
    (void)image; (void)request;
    return -EOPNOTSUPP;
#else
    unsigned status;
    int error;
    if (!request || !request->payload || !request->length) return -EINVAL;
    /* Validate again: this public boundary cannot admit unparsed request types. */
    if (request->type == 250) {
        if (request->parameter != 35 || request->length > B41_AGPS_PMTK_MAX ||
            request->payload[request->length - 1] ||
            memchr(request->payload, 0, request->length - 1)) return -EBADMSG;
    } else if ((request->type >= 256 && request->type <= 262) || request->type == 264) {
        if (request->parameter != (request->type == 264 ? 118 : request->type - 256 + 62) ||
            request->length > B41_AGPS_RX_MAX - 12u ||
            (request->type == 262 && request->length > 8192)) return -EBADMSG;
    } else return -EOPNOTSUPP;
    error = live_primary(image);
    if (error) return error;
    if (request->type == 250) {
        unsigned (*set)(unsigned, const void *, unsigned, unsigned) =
            (unsigned (*)(unsigned, const void *, unsigned, unsigned))(image->base + 0x6b17b0u);
        status = set(35, request->payload, 6, 4);
    } else {
        unsigned (*set)(unsigned, const void *, unsigned, unsigned, unsigned) =
            (unsigned (*)(unsigned, const void *, unsigned, unsigned, unsigned))
            (image->base + 0x6b14c4u);
        status = set(request->parameter, request->payload, 6, 4, request->length);
    }
    /* Actual native input copies into owned allocation before enqueue. Zero
     * means library acceptance only; nonzero OEM status is preserved as EIO.
     * Queue signalling can block. Child supervisor bounds that failure.
     */
    return status ? -EIO : 0;
#endif
}
