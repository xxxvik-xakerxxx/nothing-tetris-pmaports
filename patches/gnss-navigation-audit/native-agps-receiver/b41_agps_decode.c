/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_agps_receiver.h"
#include <errno.h>
#include <string.h>

static unsigned word(const unsigned char *p)
{
    return (unsigned)p[0] | (unsigned)p[1] << 8 |
        (unsigned)p[2] << 16 | (unsigned)p[3] << 24;
}

int b41_agps_receiver_decode(const void *packet, size_t length,
                            struct b41_agps_request *out)
{
    const unsigned char *p = packet;
    struct b41_agps_request result;
    size_t prefix = 12;
    if (!p || !out) return -EINVAL;
    if (length > B41_AGPS_RX_MAX) return -EMSGSIZE;
    if (length < 8 || word(p) != 1) return -EBADMSG;
    result.type = word(p + 4);
    if (result.type == 250) {
        if (length < 9 || p[8] > 1) return -EBADMSG;
        if (!p[8]) return length == 9 ? -ENODATA : -EBADMSG;
        prefix = 13;
        if (length < prefix + 1) return -EBADMSG;
        result.parameter = 35;
        result.length = word(p + 9);
        if (!result.length || result.length != length - prefix) return -EBADMSG;
        if (result.length > B41_AGPS_PMTK_MAX) return -EMSGSIZE;
        if (p[length - 1] || memchr(p + prefix, 0, result.length - 1)) return -EBADMSG;
    } else if ((result.type >= 256 && result.type <= 262) || result.type == 264) {
        if (length < prefix) return -EBADMSG;
        result.parameter = result.type == 264 ? 118 : result.type - 256 + 62;
        result.length = word(p + 8);
        if (!result.length || result.length != length - prefix) return -EBADMSG;
        if (result.type == 262 && result.length > 8192) return -EMSGSIZE;
    } else return -EOPNOTSUPP;
    result.payload = p + prefix;
    *out = result;
    return 0;
}
