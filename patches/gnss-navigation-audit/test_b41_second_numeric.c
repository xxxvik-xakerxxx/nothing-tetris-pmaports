/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_second_numeric.h"
#include "b41_capability_branch.h"
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
static uint32_t word(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
int main(void)
{
    /* Pure relocated-record parser fixture, NOT a legitimate loader association
     * or hardware capability success. The pinned oracle checks real records.
     */
    uint8_t *mapped = calloc(1, B41_LIBRARY_IMAGE_END);
    assert(mapped);
    struct b41_library_association image = {(uintptr_t)mapped, 0, 0, B41_LIBRARY_IMAGE_END};
    uintptr_t table = image.base + 0x6edd50u;
    memcpy(mapped + 0x6e6ff8u, &table, sizeof(table));
    const uintptr_t keys[] = {0x6ed710u, 0x6ed8a0u, 0x6eda30u};
    const uintptr_t values[] = {0x6ed7d0u, 0x6ed960u, 0x6edaf0u};
    const char *adies[] = {"0x6631", "0x6637", "0x6686"};
    struct b41_capability_branch branch, retained;
    for (unsigned i = 0; i < 3; ++i) {
        uintptr_t key = image.base + keys[i], value = image.base + values[i];
        memcpy(mapped + 0x6edd50u + 16u*(21u+i), &key, sizeof(key));
        memcpy(mapped + 0x6edd50u + 16u*(21u+i) + 8u, &value, sizeof(value));
        memcpy(mapped + keys[i], "0x6878", 7);
        memcpy(mapped + keys[i] + 0x5cu, adies[i], 7);
        mapped[values[i]+0xcc] = 1;
        assert(b41_capability_branch_read(&image, "0x6878", adies[i], 0, 0, &branch) == 0);
        assert(branch.index == 21u+i && branch.capability[0xcc] == 1);
    }
    retained = branch;
    assert(b41_capability_branch_read(&image, "0x6878", "", 0, 0, &branch) == -ENODATA);
    assert(!memcmp(&branch, &retained, sizeof(branch)));
    assert(b41_capability_branch_read(&image, "0x6878", "0x6686", 1, 0, &branch) == -ENODEV);
    mapped[values[2]+0xcc] = 0;
    assert(b41_capability_branch_read(&image, "0x6878", "0x6686", 0, 0, &branch) == -EPROTO);
    assert(!memcmp(&branch, &retained, sizeof(branch)));
    free(mapped);
    struct b41_second_config base = {0}, out, before;
    struct b41_second_numeric_sources sources = {0, 0, 0x3fc00000u};
    base.bytes[0x46] = 'M'; base.provenance[0x46] = B41_SECOND_LITERAL;
    assert(b41_second_numeric_apply(&base, &sources, &out) == 1);
    assert(word(out.bytes+0x1c) == 0x1900000u && word(out.bytes+0x20) == 0x12c00000u);
    assert(!strcmp((const char *)out.bytes+0x28, "1.5"));
    assert(out.bytes[0x46] == 'M' && out.provenance[0x46] == B41_SECOND_LITERAL);
    assert(out.unresolved_bytes == B41_SECOND_CONFIG_SIZE - 39u);
    sources.requested_dfff4 = 0x100000u; sources.requested_dfff8 = 1;
    assert(b41_second_numeric_apply(&base, &sources, &out) == 1);
    assert(word(out.bytes+0x1c) == 0x100000u && word(out.bytes+0x20) == 0xc00000u);
    sources.requested_dfff4 = UINT32_MAX; sources.requested_dfff8 = UINT32_MAX;
    assert(b41_second_numeric_apply(&base, &sources, &out) == 1);
    assert(word(out.bytes+0x1c) == 0x3000000u && word(out.bytes+0x20) == 0x20000000u);
    before = out; sources.float_bits_de4bc = 0x7f800000u;
    assert(b41_second_numeric_apply(&base, &sources, &out) == -ERANGE);
    assert(!memcmp(&out, &before, sizeof(out)));
    sources.float_bits_de4bc = 0x7f7fffffu;
    assert(b41_second_numeric_apply(&base, &sources, &out) == -ENOSPC);
    assert(!memcmp(&out, &before, sizeof(out)));
    return 0;
}
