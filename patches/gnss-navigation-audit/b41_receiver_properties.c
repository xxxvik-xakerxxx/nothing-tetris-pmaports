/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_receiver_policy.h"
#include <errno.h>
#include <string.h>
#if defined(__BIONIC__)
#include <sys/system_properties.h>
_Static_assert(PROP_VALUE_MAX == B41_RECEIVER_PROPERTY_MAX, "Bionic property value ABI");
#endif

int b41_receiver_property_read(const char *key, char *value)
{
    if (!key || !value) return -EINVAL;
    if (strcmp(key, "ro.build.type") && strcmp(key, "ro.debuggable")) return -EINVAL;
#if defined(__BIONIC__)
    int length = __system_property_get(key, value);
    if (length < 0) return -EIO;
    if (!length) return -ENODATA;
    if ((unsigned)length >= B41_RECEIVER_PROPERTY_MAX) return -EOVERFLOW;
    if (value[length] || memchr(value, 0, (size_t)length)) return -EBADMSG;
    return length;
#else
    return -EOPNOTSUPP;
#endif
}
