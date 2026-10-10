/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_mipc_checked_tag.h"
#include <errno.h>
#include <string.h>

/* f214 retains x2; f24c ldrh length; f260 strh to retained x2. */
extern void *mipc_msg_get_val_ptr(void *, unsigned, uint16_t *);

int b41_mipc_checked_tag_word(void *response, unsigned tag, uint32_t *out)
{
    uint16_t length = 0;
    uint32_t result;
    const void *value;
    if (!response || !out || (tag != 0 && tag != 0x101 && tag != 0x102 && tag != 0x103))
        return -EINVAL;
    value = mipc_msg_get_val_ptr(response, tag, &length);
    if (!value)
        return -ENODATA;
    if (length < sizeof(result))
        return -EMSGSIZE;
    memcpy(&result, value, sizeof(result));
    *out = result;
    return 0;
}
