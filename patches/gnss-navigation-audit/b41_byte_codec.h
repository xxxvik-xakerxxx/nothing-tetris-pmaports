/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_BYTE_CODEC_H
#define B41_BYTE_CODEC_H
#include <stddef.h>
#include <stdint.h>

/* mnld84c6c/84d7c. This is reversible log obfuscation, not cryptography.
 * The scalar forward loop also matches the vendor's overlapping-buffer path.
 * Capacity is supplied by the owner, not inferred from a vendor pointer.
 */
static inline int b41_byte_codec(const void *src, size_t src_capacity,
                                void *dst, size_t dst_capacity,
                                uint32_t count, int decode)
{
    const uint8_t *input = src;
    uint8_t *output = dst;
    if (count > src_capacity || count > dst_capacity ||
        (count && (!input || !output)) || (decode != 0 && decode != 1))
        return -1;
    for (uint32_t i = 0; i < count; ++i) {
        uint8_t value = input[i];
        output[i] = decode ? (uint8_t)(((value ^ 0x63u) << 2) |
                                      ((value ^ 0x63u) >> 6))
                           : (uint8_t)(((value >> 2) | (value << 6)) ^ 0x63u);
    }
    return 0;
}
#endif
