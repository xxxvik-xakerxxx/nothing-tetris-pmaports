/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_capability_branch.h"
#include <errno.h>
#include <string.h>
int b41_capability_branch_read(const struct b41_library_association *image,
    const char *chip, const char *adie, uint32_t hw, uint32_t sw,
    struct b41_capability_branch *out)
{
    static const struct { const char *adie; uintptr_t key, value; } profiles[] = {
        {"0x6631", 0x6ed710u, 0x6ed7d0u},
        {"0x6637", 0x6ed8a0u, 0x6ed960u},
        {"0x6686", 0x6eda30u, 0x6edaf0u},
    };
    struct b41_capability_branch result = {0};
    uintptr_t table, key, value;
    uint32_t key_hw, key_sw;
    unsigned selected;
    if (!image || !chip || !adie || !out) return -EINVAL;
    if (!image->base || image->extent != B41_LIBRARY_IMAGE_END ||
        image->base > UINTPTR_MAX - image->extent) return -ERANGE;
    if (strcmp(chip, "0x6878")) return -EOPNOTSUPP;
    for (selected = 0; selected < 3; ++selected)
        if (!strcmp(adie, profiles[selected].adie)) break;
    if (selected == 3) return -ENODATA;
    memcpy(&table, (const void *)(image->base + 0x6e6ff8u), sizeof(table));
    if (table != image->base + 0x6edd50u) return -ESTALE;
    memcpy(&key, (const void *)(table + 16u*(21u+selected)), sizeof(key));
    memcpy(&value, (const void *)(table + 16u*(21u+selected) + 8u), sizeof(value));
    if (key != image->base + profiles[selected].key ||
        value != image->base + profiles[selected].value) return -ESTALE;
    if (memcmp((const void *)key, chip, 7) ||
        memcmp((const void *)(key + 0x5cu), adie, 7)) return -EPROTO;
    memcpy(&key_hw, (const void *)(key + 0xb8u), 4);
    memcpy(&key_sw, (const void *)(key + 0xbcu), 4);
    /* Exact matcher: queried0/0 does not filter revision; otherwise both
     * revision fields must match. No new wildcard is introduced.
     */
    if ((hw || sw) && (hw != key_hw || sw != key_sw)) return -ENODEV;
    memcpy(result.capability, (const void *)value, sizeof(result.capability));
    if (result.capability[0xcc] != 1) return -EPROTO;
    result.index = 21u + selected; result.source = value;
    *out = result;
    return 0;
}
