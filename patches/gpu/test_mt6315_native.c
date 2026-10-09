/* SPDX-License-Identifier: GPL-2.0-only */
/* No hardware: exercise the actual patched helpers with bounded fake OF/regmap. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <linux/regulator/mt6315-regulator.h>

typedef uint32_t u32;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U >> (31 - (h))) & (~0U << (l)))

struct device_node {
	const char *name;
	bool available;
	struct device_node *children[4];
	bool has_mask;
	u32 mask;
	int property_error;
	unsigned int refs;
};
struct device { struct device_node *of_node; };
static const struct { struct { const char *of_match; } desc; }
	mt6315_regulators[] = {
		{ { "vbuck1" } }, { { "vbuck2" } },
		{ { "vbuck3" } }, { { "vbuck4" } },
	};

static struct device_node *of_get_child_by_name(struct device_node *node,
					       const char *name)
{
	if (!node)
		return NULL;
	for (unsigned int i = 0; i < 4; i++) {
		struct device_node *child = node->children[i];
		if (child && !strcmp(child->name, name)) {
			child->refs++;
			return child;
		}
	}
	return NULL;
}

static bool of_device_is_available(struct device_node *node)
{
	return node && node->available;
}

static void of_node_put(struct device_node *node)
{
	if (node) {
		assert(node->refs);
		node->refs--;
	}
}

static void *of_find_property(struct device_node *node, const char *name, void *len)
{
	(void)len;
	assert(!strcmp(name, "mediatek,buck1-mode-mask"));
	return node && node->has_mask ? node : NULL;
}

static int of_property_read_u32(struct device_node *node, const char *name, u32 *value)
{
	assert(!strcmp(name, "mediatek,buck1-mode-mask"));
	if (node->property_error)
		return node->property_error;
	*value = node->mask;
	return 0;
}

#ifdef TETRIS_VGPU_OBSERVER_TESTS
struct regmap {
	unsigned int values[3];
	unsigned int reads[3];
	unsigned int calls;
	unsigned int fail_at;
};

static int regmap_read(struct regmap *map, unsigned int address, unsigned int *value)
{
	assert(map->calls < 3);
	unsigned int step = map->calls++;
	map->reads[step] = address;
	if (map->fail_at == step + 1)
		return -EIO;
	*value = map->values[step];
	return 0;
}
#endif

#include "mt6315-test-helpers.h"

static void test_phases(void)
{
	struct device_node root = { .available = true };
	struct device dev = { .of_node = &root };
	struct mt_regulator_init_data init = { 0 };
	const unsigned int ids[] = { 3, 5, 6, 7, 9 };
	const unsigned int expected[] = { 3, 1, 11, 3, 1 };
	for (unsigned int i = 0; i < 5; i++) {
		assert(!mt6315_init_mode_masks(&dev, ids[i], &init));
		assert(init.modeset_mask[0] == expected[i]);
		/* Legacy selected outputs keep coupled/default topology. */
		assert(mt6315_mode_mask_owned(&dev, 1, init.modeset_mask[0]));
		assert(mt6315_mode_mask_owned(&dev, 15, init.modeset_mask[0]));
	}
	root.has_mask = true;
	root.mask = 11;
	assert(!mt6315_init_mode_masks(&dev, 6, &init));
	assert(!mt6315_mode_mask_owned(&dev, 1, init.modeset_mask[0]));
	assert(!mt6315_mode_mask_owned(&dev, 3, init.modeset_mask[0]));
	assert(mt6315_mode_mask_owned(&dev, 11, init.modeset_mask[0]));
	assert(mt6315_mode_mask_owned(&dev, 15, init.modeset_mask[0]));
	assert(mt6315_mode_mask_owned(&dev, 2, init.modeset_mask[0]));
	root.mask = 1;
	assert(!mt6315_init_mode_masks(&dev, 6, &init));
	assert(mt6315_mode_mask_owned(&dev, 1, init.modeset_mask[0]));
	for (unsigned int mask = 0; mask < 32; mask++) {
		root.mask = mask;
		assert(mt6315_init_mode_masks(&dev, 6, &init) ==
		       ((mask & 1) && mask < 16 ? 0 : -EINVAL));
	}
	root.property_error = -EIO;
	assert(mt6315_init_mode_masks(&dev, 6, &init) == -EIO);
}

static void test_children(void)
{
	struct device_node root = { .available = true };
	struct device_node regulators = { .name = "regulators", .available = true };
	struct device_node buck1 = { .name = "vbuck1", .available = true };
	struct device_node buck2 = { .name = "vbuck2", .available = true };
	struct device dev = { .of_node = &root };
	assert(mt6315_described_rails(&dev) == 15);
	root.children[0] = &regulators;
	assert(mt6315_described_rails(&dev) == -ENODEV);
	regulators.children[0] = &buck1;
	regulators.children[1] = &buck2;
	assert(mt6315_described_rails(&dev) == 3);
	buck1.available = false;
	assert(mt6315_described_rails(&dev) == 2);
	buck2.available = false;
	assert(mt6315_described_rails(&dev) == -ENODEV);
	regulators.available = false;
	buck1.available = true;
	assert(mt6315_described_rails(&dev) == -ENODEV);
	assert(!root.refs && !regulators.refs && !buck1.refs && !buck2.refs);
}

#ifdef TETRIS_VGPU_OBSERVER_TESTS
static void test_snapshot(void)
{
	for (unsigned int reg = 0; reg <= 0x16d0; reg++) {
		assert(!mt6315_vgpu_writeable_reg(NULL, reg));
		assert(mt6315_vgpu_readable_reg(NULL, reg) ==
		       (reg == MT6315_VBUCK2_DBG4 || reg == MT6315_VBUCK2_DBG0 ||
			reg == MT6315_BUCK_TOP_ELR2));
	}
	for (unsigned int enabled = 0; enabled <= 1; enabled++) {
		struct regmap map = { .values = { enabled, 0x80, enabled } };
		struct mt6315_vgpu_snapshot snapshot = { 0 };
		assert(!mt6315_read_vgpu(&map, &snapshot));
		assert(map.calls == 3 && snapshot.status == enabled);
		assert(snapshot.selector == 0x80);
		assert(map.reads[0] == MT6315_VBUCK2_DBG4);
		assert(map.reads[1] == (enabled ? MT6315_VBUCK2_DBG0 : MT6315_BUCK_TOP_ELR2));
		assert(map.reads[2] == MT6315_VBUCK2_DBG4);
	}
	for (unsigned int fail = 1; fail <= 5; fail++) {
		struct regmap map = { .values = { 1, 0x80, 1 }, .fail_at = fail };
		struct mt6315_vgpu_snapshot snapshot;
		struct mt6315_vgpu_snapshot before;
		memset(&snapshot, 0xa5, sizeof(snapshot));
		before = snapshot;
		int expected = -EIO;
		if (fail == 4) {
			map.values[2] = 0;
			expected = -EAGAIN;
		} else if (fail == 5) {
			map.values[1] = 0xc0;
			expected = -ERANGE;
		}
		assert(mt6315_read_vgpu(&map, &snapshot) == expected);
		assert(map.calls == (fail <= 3 ? fail : 3));
		assert(!memcmp(&snapshot, &before, sizeof(snapshot)));
	}
}
#endif

int main(void)
{
	test_phases();
	test_children();
#ifdef TETRIS_VGPU_OBSERVER_TESTS
	test_snapshot();
#endif
	return 0;
}
