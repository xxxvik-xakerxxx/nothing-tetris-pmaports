/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_mipc_checked_tag.h"
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

static void *value;
static uint16_t extent;
static unsigned calls;
static int response;

void *mipc_msg_get_val_ptr(void *message, unsigned tag, uint16_t *length)
{
    assert(message == &response && length);
    assert(tag == 0 || tag == 0x101 || tag == 0x102 || tag == 0x103);
    assert(*length == 0);
    *length = extent;
    ++calls;
    return value;
}

int main(void)
{
    uint32_t out = 0xa5a5a5a5, expected = 0x12345678;
    for (unsigned tag = 0; tag < 4; ++tag) {
        unsigned id = tag ? 0x100 + tag : 0;
        for (extent = 0; extent <= 8; ++extent) {
            /* Exact allocation makes an accidental short-tag read visible to
             * ASAN, unlike a full word with only a mocked smaller length. */
            value = malloc(extent ? extent : 1);
            assert(value);
            memset(value, 0x78, extent ? extent : 1);
            if (extent >= 4)
                memcpy(value, &expected, 4);
            out = 0xa5a5a5a5;
            int rc = b41_mipc_checked_tag_word(&response, id, &out);
            if (extent < 4)
                assert(rc == -EMSGSIZE && out == 0xa5a5a5a5);
            else
                assert(rc == 0 && out == expected);
            free(value);
        }
    }
    value = NULL;
    extent = 4;
    out = 0xa5a5a5a5;
    assert(b41_mipc_checked_tag_word(&response, 0, &out) == -ENODATA);
    assert(out == 0xa5a5a5a5);
    unsigned before = calls;
    assert(b41_mipc_checked_tag_word(NULL, 0, &out) == -EINVAL);
    assert(b41_mipc_checked_tag_word(&response, 0, NULL) == -EINVAL);
    assert(b41_mipc_checked_tag_word(&response, 0x104, &out) == -EINVAL);
    assert(calls == before);
    return 0;
}
