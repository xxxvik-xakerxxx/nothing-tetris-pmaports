/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef uint32_t u32;
#define BIT(n) (1U << (n))
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define dev_err(...) ((void)0)
#define MT6315_BUCK_MODE_LP 2
enum { REGULATOR_MODE_FAST = 1, REGULATOR_MODE_NORMAL = 2, REGULATOR_MODE_IDLE = 4 };
enum { MT6315_BUCK_TOP_4PHASE_ANA_CON42, MT6315_BUCK_TOP_CON1 };
struct regulator_desc { unsigned int id; };
struct mt6315_regulator_info { struct regulator_desc desc; u32 lp_mode_mask, lp_mode_shift; };
struct mt_regulator_init_data { u32 modeset_mask[4]; };
struct regmap { u32 value[2]; int fail_read, fail_write, reads, writes, sleeps; };
struct regulator_dev {
    struct regulator_desc *desc;
    struct mt_regulator_init_data *data;
    struct regmap *regmap;
};
static struct regmap *current;
static void *rdev_get_drvdata(struct regulator_dev *rdev) { return rdev->data; }
static unsigned int rdev_get_id(struct regulator_dev *rdev) { return rdev->desc->id; }
static int regmap_read(struct regmap *map, unsigned int reg, int *value)
{
    assert(reg < 2);
    if (++map->reads == map->fail_read)
        return -EIO;
    *value = map->value[reg];
    return 0;
}
static int regmap_update_bits(struct regmap *map, unsigned int reg, u32 mask, u32 value)
{
    assert(reg < 2 && !(value & ~mask));
    map->writes++;
    if (map->fail_write)
        return -EREMOTEIO;
    map->value[reg] = (map->value[reg] & ~mask) | value;
    return 0;
}
static void usleep_range(unsigned int low, unsigned int high)
{
    assert(low == 100 && high == 110);
    current->sleeps++;
}

#include "mode-transition-source.h"

int main(void)
{
    const u32 modes[] = { REGULATOR_MODE_FAST, REGULATOR_MODE_NORMAL,
                          REGULATOR_MODE_IDLE, 0x80 };
    unsigned int cases = 0;
    for (unsigned int id = 0; id < 4; id++) {
        struct mt6315_regulator_info info = { .desc.id = id,
            .lp_mode_mask = BIT(id), .lp_mode_shift = id };
        struct mt_regulator_init_data data = { .modeset_mask = {1, 2, 4, 8} };
        for (unsigned int phase = 0; phase < 16; phase++)
        for (unsigned int lp = 0; lp < 16; lp++)
        for (unsigned int m = 0; m < sizeof(modes) / sizeof(modes[0]); m++)
        for (int fail = 0; fail < 4; fail++) {
            struct regmap map = { .value = {phase, lp},
                .fail_read = fail < 3 ? fail : 0, .fail_write = fail == 3 };
            struct regulator_dev rdev = { .desc = &info.desc, .data = &data, .regmap = &map };
            current = &map;
            int fast = !!(phase & BIT(id));
            int idle = !fast && (lp & BIT(id));
            int read_error = fail == 1 || (fail == 2 && !fast);
            int write = modes[m] != 0x80 &&
                        !(modes[m] == REGULATOR_MODE_NORMAL && !fast && !idle);
            int expected = read_error ? -EIO : modes[m] == 0x80 ? -EINVAL :
                           write && fail == 3 ? -EREMOTEIO : 0;
            int ret = mt6315_regulator_set_mode(&rdev, modes[m]);
            assert(ret == expected);
            assert(map.writes == (!read_error && write));
            u32 p = phase, l = lp;
            if (expected == 0 && write) {
                if (modes[m] == REGULATOR_MODE_FAST) p |= BIT(id);
                else if (modes[m] == REGULATOR_MODE_IDLE) l |= BIT(id);
                else if (fast) p &= ~BIT(id);
                else l &= ~BIT(id);
            }
            assert(map.value[0] == p && map.value[1] == l);
            assert(map.sleeps == (!read_error && modes[m] == REGULATOR_MODE_NORMAL && idle));
            cases++;
        }
    }
    printf("PASS: %u GPU/camera mode transitions and failures; no hardware access\n", cases);
    return 0;
}
