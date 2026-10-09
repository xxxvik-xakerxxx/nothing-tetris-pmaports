/* Pinned B4.1 machine-ABI boundary, not an installed callback or IPC service. */
#ifndef B41_FRAME_SYNC_H
#define B41_FRAME_SYNC_H
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Slot3 consumes low 8 bits of w0; slot4 consumes no input registers;
 * slot5 consumes signed32 w0. All return zero even if AGPS dispatch fails.
 * These types describe the observed AArch64 ABI, not recovered vendor headers.
 */
typedef int32_t (*b41_slot3_frame_sync_sleep_fn)(uint32_t value);
typedef int32_t (*b41_slot4_frame_sync_network_fn)(void);

/* Internal AGPS payload: slots3/4 include CR without LF, slot5 retains CRLF.
 * All exclude the trailing NUL.
 * No DSP transport or navigation-start semantics are implied.
 */
static inline int b41_frame_sync_encode(unsigned slot, uint32_t value,
                                       void *dst, size_t cap, size_t *used)
{
    char body[24], message[32];
    unsigned checksum = 0;
    int n, length;
    if (!used)
        return -1;
    *used = 0;
    if (!dst || (slot != 3 && slot != 4 && slot != 5))
        return -1;
    if (slot == 3)
        n = snprintf(body, sizeof(body), "PMTK738,%u", value & 255u);
    else if (slot == 4)
        n = snprintf(body, sizeof(body), "PMTK736,0,0");
    else {
        long long signed_value = value <= INT32_MAX ? (long long)value
                                 : (long long)value - (1LL << 32);
        n = snprintf(body, sizeof(body), "PMTK736,1,%lld", signed_value);
    }
    if (n < 0 || (size_t)n >= sizeof(body))
        return -1;
    for (int i = 0; i < n; ++i)
        checksum ^= (unsigned char)body[i];
    length = snprintf(message, sizeof(message), slot == 5 ? "$%s*%02X\r\n"
                                                        : "$%s*%02X\r", body, checksum);
    if (length < 0 || (size_t)length >= sizeof(message) || (size_t)length > cap)
        return -1;
    memcpy(dst, message, (size_t)length);
    *used = (size_t)length;
    return 0;
}
#endif
