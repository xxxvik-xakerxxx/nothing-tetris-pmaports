/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U << (l)) & (~0U >> (31 - (h))))
enum { MT6315_VBUCK1, MT6315_VBUCK2, MT6315_VBUCK3,
       MT6315_VBUCK4, MT6315_VBUCK_MAX };
struct device_node {
    bool present, available;
    int references;
    struct device_node *children[4];
};
struct device { struct device_node *of_node; };
struct regulator_desc { const char *of_match; };
struct regulator_info { struct regulator_desc desc; };
static const struct regulator_info mt6315_regulators[] = {
    { { "vbuck1" } }, { { "vbuck2" } }, { { "vbuck3" } }, { { "vbuck4" } }
};
static struct device_node *container;

static struct device_node *of_get_child_by_name(struct device_node *parent, const char *name)
{
    struct device_node *node = NULL;
    if (!strcmp(name, "regulators")) {
        if (parent && container->present)
            node = container;
    } else {
        assert(parent == container);
        for (unsigned int i = 0; i < 4; i++)
            if (!strcmp(name, mt6315_regulators[i].desc.of_match))
                node = parent->children[i];
        assert(name[0] == 'v');
        if (node && !node->present)
            node = NULL;
    }
    if (node)
        node->references++;
    return node;
}
static bool of_device_is_available(struct device_node *node)
{
    return node && node->available;
}
static void of_node_put(struct device_node *node)
{
    if (node) {
        assert(node->references > 0);
        node->references--;
    }
}

#include "described-rails-source.h"

int main(void)
{
    struct device_node root = {0}, regs = {0}, rails[4] = {0};
    struct device dev = { .of_node = &root };
    container = &regs;
    unsigned int cases = 0;
    assert(mt6315_described_rails(&dev) == 15);
    dev.of_node = NULL;
    assert(mt6315_described_rails(&dev) == 15);
    dev.of_node = &root;
    for (unsigned int available = 0; available < 2; available++)
    for (unsigned int present = 0; present < 16; present++)
    for (unsigned int enabled = 0; enabled < 16; enabled++) {
        regs.present = true;
        regs.available = available;
        for (unsigned int i = 0; i < 4; i++) {
            regs.children[i] = &rails[i];
            rails[i].present = !!(present & BIT(i));
            rails[i].available = !!(enabled & BIT(i));
        }
        int mask = available ? present & enabled : 0;
        assert(mt6315_described_rails(&dev) == (mask ? mask : -ENODEV));
        assert(regs.references == 0);
        for (unsigned int i = 0; i < 4; i++)
            assert(rails[i].references == 0);
        cases++;
    }
    printf("PASS: %u described-rail cases, legacy fallback and balanced DT references\n", cases);
    return 0;
}
