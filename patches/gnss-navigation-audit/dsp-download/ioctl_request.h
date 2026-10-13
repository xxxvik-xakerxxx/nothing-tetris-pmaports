/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_LINUX_IOCTL_REQUEST_H
#define B41_LINUX_IOCTL_REQUEST_H

#include <limits.h>
#include <stdint.h>

_Static_assert(UINT_MAX == UINT32_MAX && INT_MAX == INT32_MAX,
               "Linux ioctl command ABI requires 32-bit int");

/* Linux consumes the low32 request bits. glibc declares unsigned long,
 * whereas musl declares int, including requests with direction bit31 set.
 */
#ifdef __GLIBC__
typedef unsigned long b41_ioctl_request_t;
#else
typedef int b41_ioctl_request_t;
#endif

static inline b41_ioctl_request_t b41_ioctl_request(uint32_t command)
{
    return (b41_ioctl_request_t)command;
}

#endif
