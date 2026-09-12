/* SPDX-License-Identifier: GPL-2.0-only */
/* Execute the source callbacks with read-only fake regmap access. */
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

#define container_of(ptr, type, member) \
	((type *)((char *)(ptr) - offsetof(type, member)))
#define dev_notice(...) ((void)0)
#define dev_err(...) ((void)0)
#define ffs(value) __builtin_ffs(value)

struct regulator_desc { unsigned int vsel_reg, vsel_mask; };
struct mt6315_regulator_info {
	struct regulator_desc desc;
	unsigned int da_vsel_reg, da_reg, qi;
};
struct regmap {
	unsigned int elr, actual, enabled, trace[2], reads, fail_at;
};
struct regulator_dev {
	const struct regulator_desc *desc;
	struct regmap *regmap;
};

static int regmap_read(struct regmap *, unsigned int, void *);
#include "readback-source.h"

static int regmap_read(struct regmap *map, unsigned int reg, void *out)
{
	unsigned int value;
	assert(map->reads < 2);
	map->trace[map->reads++] = reg;
	if (map->fail_at == map->reads)
		return -5;
	switch (reg) {
	case MT6315_BUCK_TOP_ELR2: value = map->elr; break;
	case MT6315_VBUCK2_DBG0: value = map->actual; break;
	case MT6315_VBUCK2_DBG4: value = map->enabled; break;
	default: assert(0); return -22;
	}
	/* Both source callbacks pass either int* or unsigned int*. */
	*(unsigned int *)out = value;
	return 0;
}

int main(void)
{
	const struct mt6315_regulator_info info = {
		.desc = { MT6315_BUCK_TOP_ELR2, 0xff },
		.da_vsel_reg = MT6315_VBUCK2_DBG0,
		.da_reg = MT6315_VBUCK2_DBG4,
		.qi = 1,
	};
	struct regmap map = {0};
	struct regulator_dev rdev = { &info.desc, &map };
	unsigned int enabled, elr, actual, fail;

	/* Entire advertised selector range, including values below the DT minimum.
	 * Bit 7 in DBG4 must not be mistaken for the bit-0 enable indication.
	 */
	for (enabled = 0; enabled < 2; enabled++) {
		for (elr = 0; elr < 0xc0; elr++) {
			for (actual = 0; actual < 0xc0; actual++) {
				map = (struct regmap){ .elr = elr, .actual = actual,
					.enabled = enabled | 0x80 };
				assert(mt6315_regulator_get_voltage_sel(&rdev) ==
				       (int)(enabled ? actual : elr));
				assert(map.reads == 2);
				assert(map.trace[0] == MT6315_VBUCK2_DBG4);
				assert(map.trace[1] == (enabled ? MT6315_VBUCK2_DBG0 :
								MT6315_BUCK_TOP_ELR2));
				map.reads = 0;
				assert(regulator_get_voltage_sel_regmap(&rdev) == (int)elr);
				assert(map.reads == 1);
				assert(map.trace[0] == MT6315_BUCK_TOP_ELR2);
			}
		}
	}
	for (enabled = 0; enabled < 2; enabled++) {
		for (fail = 1; fail <= 2; fail++) {
			map = (struct regmap){ .enabled = enabled, .fail_at = fail };
			assert(mt6315_regulator_get_voltage_sel(&rdev) == -5);
			assert(map.reads == fail);
		}
	}
	map = (struct regmap){ .fail_at = 1 };
	assert(regulator_get_voltage_sel_regmap(&rdev) == -5);
	assert(map.reads == 1);
	puts("PASS: 73728 selector/state pairs, register traces and 5 read failures");
	puts("Confirmed source mismatch: enabled VBUCK2 reads DBG0 in vendor, ELR2 in mainline");
	return 0;
}
