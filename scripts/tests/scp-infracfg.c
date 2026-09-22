#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

struct device_node { int refs; bool available; };
struct resource { unsigned long size; };
struct regmap { int unused; };
static struct device_node scp_node, infra_node;
static struct regmap shared_map;
static struct { struct regmap *scpsys; } scpreg;
static bool missing_scp, missing_phandle, wrong_chip, no_syscon;
static int cells, resource_error, map_error, map_calls;
static unsigned long size;
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
static struct device_node *of_find_compatible_node(void *a, void *b, const char *s)
{
    assert(!a && !b && !strcmp(s, "mediatek,scp"));
    if (missing_scp) return NULL;
    scp_node.refs++;
    return &scp_node;
}
static bool of_device_is_available(struct device_node *n) { return n->available; }
static void of_node_put(struct device_node *n) { assert(n->refs > 0); n->refs--; }
static int of_property_count_u32_elems(struct device_node *n, const char *s)
{
    assert(n == &scp_node && !strcmp(s, "mediatek,infracfg"));
    return cells;
}
static struct device_node *of_parse_phandle(struct device_node *n, const char *s, int i)
{
    assert(n == &scp_node && !strcmp(s, "mediatek,infracfg") && !i);
    if (missing_phandle) return NULL;
    infra_node.refs++;
    return &infra_node;
}
static bool of_device_is_compatible(struct device_node *n, const char *s)
{
    assert(n == &infra_node);
    if (!strcmp(s, "syscon")) return !no_syscon;
    assert(!strcmp(s, "mediatek,mt6878-infracfg-ao"));
    return !wrong_chip;
}
static int of_address_to_resource(struct device_node *n, int i, struct resource *r)
{
    assert(n == &infra_node && !i);
    r->size = size;
    return resource_error;
}
static unsigned long resource_size(struct resource *r) { return r->size; }
static struct regmap *syscon_node_to_regmap(struct device_node *n)
{
    assert(n == &infra_node);
    map_calls++;
    return map_error ? (void *)(intptr_t)map_error : &shared_map;
}

/* INSERT_PATCHED_HELPER */

static void reset(void)
{
    assert(!scp_node.refs && !infra_node.refs);
    scp_node.available = infra_node.available = true;
    missing_scp = missing_phandle = wrong_chip = no_syscon = false;
    cells = 1;
    size = 0x1000;
    resource_error = map_error = map_calls = 0;
    scpreg.scpsys = NULL;
}
static void check(int expected, int calls)
{
    assert(scp_infracfg_init() == expected);
    assert(!scp_node.refs && !infra_node.refs);
    assert(map_calls == calls);
    assert(scpreg.scpsys == (expected ? NULL : &shared_map));
}
int main(void)
{
    reset(); missing_scp = true; check(-ENODEV, 0);
    reset(); scp_node.available = false; check(-ENODEV, 0);
    reset(); cells = -EINVAL; check(-EINVAL, 0);
    reset(); cells = 0; check(-EINVAL, 0);
    reset(); cells = 2; check(-EINVAL, 0);
    reset(); missing_phandle = true; check(-EINVAL, 0);
    reset(); infra_node.available = false; check(-EINVAL, 0);
    reset(); wrong_chip = true; check(-EINVAL, 0);
    reset(); no_syscon = true; check(-EINVAL, 0);
    reset(); resource_error = -EINVAL; check(-EINVAL, 0);
    reset(); size = 0; check(-ERANGE, 0);
    reset(); size = 0xfff; check(-ERANGE, 0);
    reset(); map_error = -EBUSY; check(-EBUSY, 1);
    reset(); map_error = -517; check(-517, 1);
    reset(); check(0, 1);
    reset(); size = 0x2000; check(0, 1);
    puts("PASS: 16 infracfg ownership/dependency cases; balanced DT references");
    return 0;
}
