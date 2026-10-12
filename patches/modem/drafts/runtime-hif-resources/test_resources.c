/* SPDX-License-Identifier: GPL-2.0-only */
/* Native CI kernel-boundary fixture. Production bodies are inserted verbatim. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define EPROBE_DEFER 517
#define IS_ENABLED(x) (x)
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define READ_ONCE(x) (x)
#define GFP_KERNEL 0
#define IORESOURCE_MEM 1
#define DL_FLAG_AUTOREMOVE_CONSUMER 16
#define CCIF_HIF_ID 1
#define DPMAIF_HIF_ID 2
typedef uint64_t resource_size_t;
typedef uint32_t u32;
#define MAX_PHANDLE_ARGS 16
#define GIC_SPI 0
#define IRQ_TYPE_EDGE_RISING 1
#define IRQ_TYPE_LEVEL_HIGH 4
struct resource { resource_size_t start, end; unsigned long flags; };
struct module { int refs; };
struct clk { int unused; };
struct device_node {
	const char *compatible;
	bool available, power, assigned, iommu;
	bool extended, controller, irq_map;
	unsigned int irq_cells, irq_words;
	bool has_address_cells;
	bool pericfg_present, pericfg_bad;
	unsigned int address_cells, address_words;
	struct device_node *parent;
	int refs;
};
struct of_phandle_args { struct device_node *np; int args_count; uint32_t args[MAX_PHANDLE_ARGS]; };
struct device_driver { const char *name; struct module *owner; };
struct device {
	struct device_node *of_node;
	struct device_driver *driver;
	void *pm_domain;
	bool bound, locked;
	int refs;
};
struct platform_device { struct device dev; void *drvdata; struct resource mem[4]; int irq[2], trigger[2]; };
struct device_link { int unused; };
struct action { struct device *dev; void (*fn)(void *); void *arg; };
static struct action actions[256];
static unsigned int nactions;
static struct device_node nodes[8];
static struct platform_device suppliers[2], consumer;
static struct module module;
static struct clk clock_ref;
static struct device_link link_ref;
static struct device_driver drivers[2];
static void *ccci_hif[3], *ccci_hif_op[3];
static int fail_at, step, module_fail, action_fail, link_fail;
static int memory_claims, clocks, locks;
static int irq_parses;
struct live_claim { struct resource resource; bool active; };
static struct live_claim claims[32];
static struct resource auxiliary[2];
#define THIS_MODULE (&module)
#define IS_ERR(p) ((intptr_t)(p) < 0 && (intptr_t)(p) >= -4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
static bool fault(void) { return ++step == fail_at; }
static unsigned long resource_type(const struct resource *r) { return r->flags; }
static resource_size_t resource_size(const struct resource *r) { return r->end - r->start + 1; }
static const char *dev_name(struct device *d) { assert(d); return "fixture"; }
static void mock_free(void *p) { free(p); }
static void cleanup(struct device *d)
{
	unsigned int i = nactions;
	while (i) {
		i--;
		if (actions[i].dev == d) {
			actions[i].fn(actions[i].arg);
			memmove(actions + i, actions + i + 1, (nactions - i - 1) * sizeof(actions[0]));
			nactions--;
		}
	}
}
static int devm_add_action_or_reset(struct device *d, void (*fn)(void *), void *arg)
{
	if (action_fail || fault()) { fn(arg); return -ENOMEM; }
	assert(nactions < ARRAY_SIZE(actions));
	actions[nactions++] = (struct action){d, fn, arg};
	return 0;
}
static void *devm_kzalloc(struct device *d, size_t size, int flags)
{
	void *p;
	(void)flags;
	if (fault()) return NULL;
	p = calloc(1, size);
	assert(p && nactions < ARRAY_SIZE(actions));
	actions[nactions++] = (struct action){d, mock_free, p};
	return p;
}
static void drop_claim(void *p)
{
	struct live_claim *claim = p;
	assert(claim->active && memory_claims > 0);
	claim->active = false;
	memory_claims--;
}
static struct resource *devm_request_mem_region(struct device *d, resource_size_t start,
		resource_size_t size, const char *name)
{
	resource_size_t end = start + size - 1;
	assert(d && size && name && end >= start);
	if (fault()) return NULL;
	for (unsigned int i = 0; i < ARRAY_SIZE(claims); i++)
		if (claims[i].active && start <= claims[i].resource.end &&
		    claims[i].resource.start <= end) return NULL;
	for (unsigned int i = 0; i < ARRAY_SIZE(claims); i++) {
		if (claims[i].active) continue;
		claims[i].resource = (struct resource){start, end, IORESOURCE_MEM};
		claims[i].active = true;
		memory_claims++;
		assert(nactions < ARRAY_SIZE(actions));
		actions[nactions++] = (struct action){d, drop_claim, claims + i};
		return &claims[i].resource;
	}
	assert(false);
	return NULL;
}
static void drop_clock(void *p) { (void)p; clocks--; }
static struct clk *devm_clk_get(struct device *d, const char *name)
{
	assert(d && name);
	if (fault()) return (struct clk *)(intptr_t)-EPROBE_DEFER;
	clocks++;
	actions[nactions++] = (struct action){d, drop_clock, NULL};
	return &clock_ref;
}
static struct resource *platform_get_resource(struct platform_device *p, int type, unsigned int i)
{ assert(type == IORESOURCE_MEM); return i < 4 && p->mem[i].flags ? &p->mem[i] : NULL; }
static void *platform_get_drvdata(struct platform_device *p) { return p->drvdata; }
static void platform_set_drvdata(struct platform_device *p, void *data) { p->drvdata = data; }
static struct device_node *of_node_get(struct device_node *n) { if (n) n->refs++; return n; }
static void of_node_put(struct device_node *n) { if (n) { assert(n->refs > 0); n->refs--; } }
static int of_irq_parse_one(struct device_node *n, unsigned int i, struct of_phandle_args *irq)
{
	irq_parses++;
	if (fault()) return -EINVAL;
	for (unsigned int j = 0; j < ARRAY_SIZE(suppliers); j++) {
		if (suppliers[j].dev.of_node != n) continue;
		irq->np = of_node_get(nodes + 5); irq->args_count = nodes[5].irq_cells;
		/* Deliberately reproduce the pinned parser's unchecked copy bound. */
		for (unsigned int k = 0; k < nodes[5].irq_cells; k++) irq->args[k] = 0;
		irq->args[0] = GIC_SPI; irq->args[1] = suppliers[j].irq[i];
		irq->args[2] = suppliers[j].trigger[i];
		return 0;
	}
	return -ENODEV;
}
static bool of_device_is_available(struct device_node *n) { return n && n->available; }
static bool of_device_is_compatible(struct device_node *n, const char *name)
{ return n && n->compatible && !strcmp(n->compatible, name); }
static struct device_node *of_irq_find_parent(struct device_node *n)
{ assert(n); return fault() ? NULL : of_node_get(nodes + 5); }
static int of_property_read_u32(struct device_node *n, const char *name, u32 *value)
{
	assert(n); if (fault()) return -EINVAL;
	if (!strcmp(name, "#interrupt-cells")) *value = n->irq_cells;
	else { assert(!strcmp(name, "#address-cells") && n->has_address_cells); *value = n->address_cells; }
	return 0;
}
static int of_property_count_u32_elems(struct device_node *n, const char *name)
{
	assert(n); if (fault()) return -EINVAL;
	if (!strcmp(name, "interrupts")) return n->irq_words;
	assert(!strcmp(name, "#address-cells") && n->has_address_cells);
	return n->address_words;
}
static struct device_node *of_get_parent(struct device_node *n) { return of_node_get(n->parent); }
static void *of_find_property(struct device_node *n, const char *name, void *length)
{
	(void)length;
	if (!strcmp(name, "power-domains") && n->power) return n;
	if (!strcmp(name, "assigned-clocks") && n->assigned) return n;
	if ((!strcmp(name, "iommus") || !strcmp(name, "iommu-map")) && n->iommu) return n;
	if (!strcmp(name, "interrupts-extended") && n->extended) return n;
	if (!strcmp(name, "interrupt-controller") && n->controller) return n;
	if (!strcmp(name, "interrupt-map") && n->irq_map) return n;
	if (!strcmp(name, "#address-cells") && n->has_address_cells) return n;
	if (!strcmp(name, "ccif-pericfg") && n->pericfg_present) return n;
	return NULL;
}
static struct device_node *next_node(struct device_node *old, const char *compatible)
{
	unsigned int start = old ? (unsigned int)(old - nodes) + 1 : 0;
	of_node_put(old);
	for (unsigned int i = start; i < ARRAY_SIZE(nodes); i++)
		if (nodes[i].compatible && !strcmp(nodes[i].compatible, compatible)) return of_node_get(nodes + i);
	return NULL;
}
#define for_each_compatible_node(n, type, compatible) \
	for ((n) = next_node(NULL, compatible); (n); (n) = next_node(n, compatible))
static struct device_node *of_parse_phandle(struct device_node *n, const char *property, int index)
{
	assert(n && property && index == 0);
	if (!strcmp(property, "ccif-pericfg") && n->pericfg_bad) return NULL;
	return fault() ? NULL : of_node_get(nodes + 5);
}
static int of_address_to_resource(struct device_node *n, int index, struct resource *r)
{
	assert(n && index == 0);
	*r = n == nodes + 3 ? auxiliary[0] : n == nodes + 4 ? auxiliary[1] :
		(struct resource){0x8000, 0x8fff, IORESOURCE_MEM};
	return fault() ? -EINVAL : 0;
}
static bool device_trylock(struct device *d) { if (d->locked) return false; d->locked = true; locks++; return true; }
static void device_unlock(struct device *d) { assert(d->locked); d->locked = false; locks--; }
static bool device_is_bound(struct device *d) { return d->bound; }
static bool try_module_get(struct module *m) { if (module_fail) return false; m->refs++; return true; }
static void module_put(struct module *m) { assert(m && m->refs > 0); m->refs--; }
static struct device *get_device(struct device *d) { d->refs++; return d; }
static void put_device(struct device *d) { assert(d->refs > 0); d->refs--; }
static struct platform_device *of_find_device_by_node(struct device_node *n)
{
	for (unsigned int i = 0; i < ARRAY_SIZE(suppliers); i++) {
		if (suppliers[i].dev.of_node == n) { get_device(&suppliers[i].dev); return suppliers + i; }
	}
	return NULL;
}
static struct device_link *device_link_add(struct device *c, struct device *s, unsigned int flags)
{ assert(c && s && flags == DL_FLAG_AUTOREMOVE_CONSUMER); return link_fail ? NULL : &link_ref; }

/* PRODUCTION */

static const char *const names[] = {"c0", "c1", "c2", "c3", "c4", "c5"};
static void reset(void)
{
	assert(nactions == 0 && module.refs == 0 && memory_claims == 0 && clocks == 0 && locks == 0);
	for (unsigned int i = 0; i < ARRAY_SIZE(nodes); i++) assert(nodes[i].refs == 0);
	memset(nodes, 0, sizeof(nodes)); memset(suppliers, 0, sizeof(suppliers));
	memset(&consumer, 0, sizeof(consumer));
	nodes[0] = (struct device_node){.compatible="mediatek,ccci_ccif", .available=true};
	nodes[1] = (struct device_node){.compatible="mediatek,dpmaif", .available=true};
	nodes[2] = (struct device_node){.compatible="mediatek,infracfg", .available=true};
	nodes[3] = (struct device_node){.compatible="mediatek,md_ccif4", .available=true};
	nodes[4] = (struct device_node){.compatible="mediatek,md_ccif5", .available=true};
	nodes[5].available = true; nodes[6].available = true;
	nodes[5].compatible = "arm,gic-v3";
	nodes[5].controller = true; nodes[5].irq_cells = 4;
	auxiliary[0] = (struct resource){0x30000, 0x30fff, IORESOURCE_MEM};
	auxiliary[1] = (struct resource){0x31000, 0x31fff, IORESOURCE_MEM};
	consumer.dev.of_node = nodes + 6;
	for (unsigned int i = 0; i < 2; i++) {
		suppliers[i].dev.of_node = nodes + i;
		nodes[i].irq_words = 8;
		drivers[i] = (struct device_driver){i ? "tetris_dpmaif_resources" : "tetris_ccif_resources", &module};
		suppliers[i].dev.driver = drivers + i;
		for (unsigned int j = 0; j < 4; j++)
			suppliers[i].mem[j] = (struct resource){0x1000U * (j + 1) + i * 0x10000U,
				0x1000U * (j + 2) - 1 + i * 0x10000U, IORESOURCE_MEM};
		suppliers[i].irq[0] = 20 + i * 100; suppliers[i].irq[1] = 21 + i * 100;
		suppliers[i].trigger[0] = suppliers[i].trigger[1] = IRQ_TYPE_LEVEL_HIGH;
	}
	fail_at = step = module_fail = action_fail = link_fail = 0;
	irq_parses = 0;
}
static int prepare(unsigned int index)
{
	int ret = tetris_hif_supplier_probe(suppliers + index, index ? DPMAIF_HIF_ID : CCIF_HIF_ID,
		names, index ? 3 : 6, index ? 1 : 2);
	if (!ret) suppliers[index].dev.bound = true;
	return ret;
}
static void finish(void)
{
	cleanup(&consumer.dev);
	for (unsigned int i = 0; i < 2; i++) {
		assert(suppliers[i].dev.refs == 0);
		tetris_hif_supplier_remove(suppliers + i);
		cleanup(&suppliers[i].dev);
	}
}
int main(void)
{
	int total[2];
	for (unsigned int i = 0; i < 2; i++) {
		reset(); assert(prepare(i) == 0); total[i] = step; finish();
		for (int f = 1; f <= total[i]; f++) {
			reset(); fail_at = f; assert(prepare(i) < 0);
			assert(!suppliers[i].drvdata); finish();
		}
	}
	reset(); nodes[0].pericfg_present = true;
	assert(prepare(0) == 0); int optional_total = step; finish();
	for (int f = 1; f <= optional_total; f++) {
		reset(); nodes[0].pericfg_present = true; fail_at = f;
		assert(prepare(0) < 0 && !suppliers[0].drvdata); finish();
	}
	reset(); nodes[0].power = true;
	assert(tetris_preflight_driver("mediatek,ccci_ccif") == -EOPNOTSUPP);
	assert(prepare(0) == -EOPNOTSUPP && !step); finish();
	reset(); nodes[0].assigned = true; assert(prepare(0) == -EOPNOTSUPP); finish();
	reset(); nodes[0].parent = nodes + 7; nodes[7].iommu = true;
	assert(prepare(0) == -EOPNOTSUPP && !nodes[7].refs); finish();
	reset(); nodes[7] = nodes[0];
	assert(tetris_preflight_driver("mediatek,ccci_ccif") == -EINVAL); finish();
	reset(); suppliers[0].mem[1] = suppliers[0].mem[0]; assert(prepare(0) == -EINVAL); finish();
	reset(); suppliers[0].irq[1] = suppliers[0].irq[0]; assert(prepare(0) == -EINVAL); finish();
	reset(); suppliers[0].irq[1] = suppliers[0].irq[0];
	suppliers[0].trigger[1] = IRQ_TYPE_EDGE_RISING;
	assert(prepare(0) == -EINVAL); finish();
	reset(); nodes[5].irq_cells = MAX_PHANDLE_ARGS + 1;
	assert(prepare(0) == -EOPNOTSUPP && irq_parses == 0); finish();
	reset(); nodes[5].has_address_cells = true;
	nodes[5].address_cells = 4; nodes[5].address_words = 1;
	assert(prepare(0) == -EOPNOTSUPP && irq_parses == 0); finish();
	reset(); nodes[5].parent = nodes + 7; nodes[7].has_address_cells = true;
	nodes[7].address_cells = 4; nodes[7].address_words = 1;
	assert(prepare(0) == -EOPNOTSUPP && irq_parses == 0); finish();
	reset(); nodes[5].has_address_cells = true; nodes[5].address_words = 0;
	assert(prepare(0) == -EINVAL && irq_parses == 0); finish();
	reset(); nodes[0].irq_words = 7;
	assert(prepare(0) == -EINVAL && irq_parses == 0); finish();
	reset(); nodes[0].extended = true;
	assert(prepare(0) == -EOPNOTSUPP && irq_parses == 0); finish();
	reset(); assert(!nodes[0].pericfg_present && prepare(0) == 0); finish();
	reset(); nodes[0].pericfg_present = true; assert(prepare(0) == 0); finish();
	reset(); nodes[0].pericfg_present = nodes[0].pericfg_bad = true;
	assert(prepare(0) == -ENODEV); finish();
	reset(); nodes[5].irq_map = true;
	assert(prepare(0) == -EOPNOTSUPP && irq_parses == 0); finish();
	reset(); auxiliary[1] = auxiliary[0];
	assert(prepare(0) == -EBUSY); finish();
	reset(); assert(prepare(0) == 0); suppliers[1].mem[0] = suppliers[0].mem[0];
	assert(prepare(1) == -EBUSY); finish();
	reset(); nodes[3].available = false; assert(prepare(0) == -ENODEV); finish();
	reset(); assert(prepare(0) == 0 && prepare(1) == 0);
	assert(tetris_resource_dependencies(&consumer) == 0 && module.refs == 2);
	assert(!ccci_hif[1] && !ccci_hif[2] && !ccci_hif_op[1] && !ccci_hif_op[2]); finish();
	reset(); assert(prepare(0) == 0 && prepare(1) == 0); suppliers[1].dev.bound = false;
	assert(tetris_resource_dependencies(&consumer) == -EPROBE_DEFER && module.refs == 1); finish();
	reset(); assert(prepare(0) == 0); drivers[0].name = "legacy";
	assert(tetris_hif_acquire(&consumer.dev, suppliers, CCIF_HIF_ID) == -EPROTOTYPE); finish();
	reset(); assert(prepare(0) == 0); module_fail = 1;
	assert(tetris_hif_acquire(&consumer.dev, suppliers, CCIF_HIF_ID) == -ENODEV); finish();
	reset(); assert(prepare(0) == 0); action_fail = 1;
	assert(tetris_hif_acquire(&consumer.dev, suppliers, CCIF_HIF_ID) == -ENOMEM && !module.refs); finish();
	reset(); assert(prepare(0) == 0); suppliers[0].dev.locked = true;
	assert(tetris_hif_acquire(&consumer.dev, suppliers, CCIF_HIF_ID) == -EPROBE_DEFER);
	suppliers[0].dev.locked = false; finish();
	reset(); ccci_hif[1] = &consumer;
	assert(tetris_resource_dependencies(&consumer) == -EBUSY && !step); ccci_hif[1] = NULL; finish();
	reset(); link_fail = 1; assert(tetris_resource_dependencies(&consumer) == -ENOMEM); finish();
	reset(); puts("resource supplier fault unwind / leases / dependency isolation PASS");
	return 0;
}
