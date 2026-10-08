/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U << (l)) & (~0U >> (31 - (h))))
enum { MT6315_VBUCK1, MT6315_VBUCK2, MT6315_VBUCK3,
       MT6315_VBUCK4, MT6315_VBUCK_MAX };
enum { MT6315_RP = 3, MT6315_PP = 6, MT6315_SP = 7 };
struct device_node { bool present; u32 mask; int error; };
struct device { struct device_node *of_node; };
struct mt_regulator_init_data { u32 modeset_mask[MT6315_VBUCK_MAX]; };

static const void *of_find_property(struct device_node *node, const char *name,
                                    int *length)
{
    assert(!strcmp(name, "mediatek,buck1-mode-mask"));
    assert(length == NULL);
    return node && node->present ? node : NULL;
}

static int of_property_read_u32(struct device_node *node, const char *name,
                                u32 *mask)
{
    assert(!strcmp(name, "mediatek,buck1-mode-mask"));
    if (node->error)
        return node->error;
    *mask = node->mask;
    return 0;
}

#include "mode-mask-source.h"

int main(void)
{
    struct device_node node = {0};
    struct device dev = { .of_node = &node };
    struct mt_regulator_init_data data, before;
    unsigned int cases = 0;
    const u32 masks[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
                         14, 15, 16, 17, 0x80000001, UINT32_MAX};

    for (unsigned int usid = 0; usid < 16; usid++) {
        memset(&data, 0xa5, sizeof(data));
        node = (struct device_node){0};
        assert(mt6315_init_mode_masks(&dev, usid, &data) == 0);
        assert(data.modeset_mask[0] == (usid == 6 ? 11 :
                                       usid == 3 || usid == 7 ? 3 : 1));
        for (int i = 1; i < 4; i++)
            assert(data.modeset_mask[i] == BIT(i));
        cases++;
        for (unsigned int m = 0; m < sizeof(masks) / sizeof(masks[0]); m++) {
            memset(&data, 0xa5, sizeof(data));
            before = data;
            node = (struct device_node){ .present = true, .mask = masks[m] };
            int ret = mt6315_init_mode_masks(&dev, usid, &data);
            if (masks[m] < 16 && (masks[m] & 1)) {
                assert(ret == 0);
                assert(data.modeset_mask[0] == masks[m]);
                for (int i = 1; i < 4; i++)
                    assert(data.modeset_mask[i] == BIT(i));
            } else {
                assert(ret == -EINVAL);
                assert(!memcmp(&data, &before, sizeof(data)));
            }
            cases++;
        }
        for (int error = -1; error >= -133; error--) {
            memset(&data, 0xa5, sizeof(data));
            before = data;
            node = (struct device_node){ .present = true, .mask = 1, .error = error };
            assert(mt6315_init_mode_masks(&dev, usid, &data) == error);
            assert(!memcmp(&data, &before, sizeof(data)));
            cases++;
        }
    }
    printf("PASS: %u mode-mask cases; no PMIC access\n", cases);
    return 0;
}
