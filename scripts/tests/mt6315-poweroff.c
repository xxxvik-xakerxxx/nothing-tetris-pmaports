/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>

enum { MT6315_TOP_TMA_KEY_H, MT6315_TOP_TMA_KEY, MT6315_TOP2_ELR7 };
enum { PROTECTION_KEY_H = 0x55, PROTECTION_KEY = 0xaa };
struct regmap { unsigned int failures; int events[5], count; };

static int step(struct regmap *map, int event)
{
    assert(map->count < 5);
    map->events[map->count++] = event;
    return (map->failures & (1U << event)) ? -10 - event : 0;
}
static int regmap_write(struct regmap *map, unsigned int reg, unsigned int value)
{
    if (reg == MT6315_TOP_TMA_KEY_H) {
        assert(!value || value == PROTECTION_KEY_H);
        return step(map, value ? 0 : 4);
    }
    assert(reg == MT6315_TOP_TMA_KEY);
    assert(!value || value == PROTECTION_KEY);
    return step(map, value ? 1 : 3);
}
static int regmap_update_bits(struct regmap *map, unsigned int reg,
                              unsigned int mask, unsigned int value)
{
    assert(reg == MT6315_TOP2_ELR7 && mask == 1 && value == 1);
    return step(map, 2);
}

#include "poweroff-source.h"

int main(void)
{
    for (unsigned int failures = 0; failures < 32; failures++) {
        struct regmap map = { .failures = failures };
        int expected[5], count = 0, error = 0;
        for (int event = 0; event < 5; event++) {
            if (event < 3 && error)
                continue;
            expected[count++] = event;
            if (!error && (failures & (1U << event)))
                error = -10 - event;
        }
        assert(mt6315_prepare_poweroff(&map) == error);
        assert(map.count == count);
        for (int i = 0; i < count; i++)
            assert(map.events[i] == expected[i]);
        assert(map.events[count - 2] == 3 && map.events[count - 1] == 4);
    }
    puts("PASS: 32 GPU/camera shutdown fault combinations; protected-write guard and both key clears");
    return 0;
}
