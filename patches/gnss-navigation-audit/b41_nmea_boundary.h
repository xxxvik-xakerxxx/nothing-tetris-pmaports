/* Offline prerequisite, not a complete libmnl ABI or a library loader. */
#ifndef B41_NMEA_BOUNDARY_H
#define B41_NMEA_BOUNDARY_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Only the null checks of this pinned registration routine, not sufficiency. */
static inline int b41_registration_preflight(const uintptr_t *slots, size_t count)
{
    const unsigned required = 0x3fb; /* slots 0,1,3,4,5,6,7,8,9 */
    if (!slots || count != 24)
        return -1;
    for (unsigned i = 0; i < 10; ++i)
        if ((required & (1u << i)) && !slots[i])
            return -1;
    return 0;
}

/* Copy borrowed callback bytes before return; never strlen/free the input.
 * cap is the caller's policy bound, not a recovered vendor sentence limit.
 * No terminator is added and no fix validity or NMEA classification is implied.
 */
static inline int b41_capture_output(void *dst, size_t cap, const void *src,
                                    uint32_t length, size_t *used)
{
    if (!used)
        return -1;
    *used = 0;
    if (!dst || !src || !length || (size_t)length > cap)
        return -1;
    memmove(dst, src, length);
    *used = length;
    return 0;
}
#endif
