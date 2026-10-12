/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_HIF_RESOURCES_H
#define TETRIS_HIF_RESOURCES_H
#include <linux/clk.h>
#include <linux/device.h>
#include <linux/ioport.h>
#include <linux/irq.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/string.h>
#include "ccci_hif.h"
#include <dt-bindings/interrupt-controller/arm-gic.h>

#if !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER) || !IS_ENABLED(CONFIG_TETRIS_CCCI_SMEM_CONSUMER)
#error "HIF resources require the private OWNER + SMEM consumer stack"
#endif
#ifndef MODULE
#error "HIF resource lifetime requires real module ownership"
#endif

/* Only resource handles. No virtual register pointer, DMA address or HIF ops. */
struct tetris_hif_resources {
	struct platform_device *pdev;
	struct module *owner;
	unsigned int hif_id;
	struct resource mem[4];
	struct resource *claim[4];
	struct clk *clk[6];
	struct of_phandle_args irq[2];
	unsigned int nmem, nclk, nirq;
};

struct tetris_hif_lease {
	struct platform_device *pdev;
	struct module *owner;
};

static inline int tetris_resource_range(const struct resource *res)
{
	if (!res || resource_type(res) != IORESOURCE_MEM ||
	    res->end < res->start || res->end - res->start == (resource_size_t)~0)
		return -EINVAL;
	return 0;
}

static inline int tetris_resource_claim(struct device *dev,
		const struct resource *res, struct resource **claim)
{
	int ret = tetris_resource_range(res);

	if (ret)
		return ret;
	*claim = devm_request_mem_region(dev, res->start, resource_size(res), dev_name(dev));
	return *claim ? 0 : -EBUSY;
}

static inline int tetris_unique_node(const char *compatible, struct device_node **out)
{
	struct device_node *node, *selected = NULL;

	for_each_compatible_node(node, NULL, compatible) {
		if (!of_device_is_available(node))
			continue;
		if (selected) {
			of_node_put(selected);
			of_node_put(node);
			return -EINVAL;
		}
		selected = of_node_get(node);
	}
	if (!selected)
		return -ENODEV;
	*out = selected;
	return 0;
}

static inline void tetris_node_put(void *data)
{
	of_node_put(data);
}

static inline bool tetris_irq_shape(const struct of_phandle_args *irq)
{
    return irq->np && of_device_is_compatible(irq->np, "arm,gic-v3") &&
        (irq->args_count == 3 || irq->args_count == 4) &&
        irq->args[0] == GIC_SPI &&
        (irq->args[2] == IRQ_TYPE_EDGE_RISING || irq->args[2] == IRQ_TYPE_LEVEL_HIGH) &&
        (irq->args_count == 3 || !irq->args[3]);
}

static inline int tetris_irq_address_shape(struct device_node *controller)
{
	struct device_node *node = of_node_get(controller);
	u32 cells;
	int ret;

	/* Mirror the parser's inherited lookup without reading its address buffer. */
	while (node) {
		struct device_node *next;

		if (of_find_property(node, "#address-cells", NULL)) {
			ret = of_property_count_u32_elems(node, "#address-cells");
			if (ret != 1) {
				of_node_put(node);
				return -EINVAL;
			}
			ret = of_property_read_u32(node, "#address-cells", &cells);
			of_node_put(node);
			if (ret)
				return ret;
			return cells <= 2 ? 0 : -EOPNOTSUPP;
		}
		next = of_get_parent(node);
		of_node_put(node);
		node = next;
	}
	/* The pinned parser defaults to two cells when no ancestor declares it. */
	return 0;
}

static inline int tetris_irq_descriptor(struct device *dev, unsigned int index,
        struct of_phandle_args *irq)
{
    struct of_phandle_args parsed = {0};
    struct device_node *parent;
    u32 cells;
    int count, ret;

    /* The pinned legacy parser copies cells before checking args[] capacity.
     * B4.1 uses direct GIC SPI descriptions, not extended/nexus translation.
     */
    if (of_find_property(dev->of_node, "interrupts-extended", NULL))
        return -EOPNOTSUPP;
    parent = of_irq_find_parent(dev->of_node);
    if (!parent)
        return -EINVAL;
    ret = of_property_read_u32(parent, "#interrupt-cells", &cells);
    if (ret)
        goto put_parent;
    ret = -EOPNOTSUPP;
    if (!of_device_is_compatible(parent, "arm,gic-v3") ||
        !of_find_property(parent, "interrupt-controller", NULL) ||
        of_find_property(parent, "interrupt-map", NULL) ||
        cells > MAX_PHANDLE_ARGS || (cells != 3 && cells != 4))
        goto put_parent;
    count = of_property_count_u32_elems(dev->of_node, "interrupts");
    ret = count < 0 ? count : -EINVAL;
    if (count <= 0 || count % cells || index >= count / cells)
        goto put_parent;
    ret = tetris_irq_address_shape(parent);
    if (ret)
        goto put_parent;
    ret = of_irq_parse_one(dev->of_node, index, &parsed);
    if (ret)
        goto put_parent;
    if (parsed.np != parent || !tetris_irq_shape(&parsed)) {
        of_node_put(parsed.np);
        ret = -EINVAL;
        goto put_parent;
	}
    ret = devm_add_action_or_reset(dev, tetris_node_put, parsed.np);
    if (!ret)
        *irq = parsed;
put_parent:
    of_node_put(parent);
    return ret;
}

static inline bool tetris_same_irq(const struct of_phandle_args *a,
		const struct of_phandle_args *b)
{
    return a->np == b->np && a->args[0] == b->args[0] && a->args[1] == b->args[1];
}

static inline int tetris_relation(struct device *dev, const char *property,
		const char *compatible, bool exclusive)
{
	struct device_node *node;
	struct resource res, *claim;
	int ret;

	if (property) {
		node = of_parse_phandle(dev->of_node, property, 0);
		if (!node)
			return -ENODEV;
		if (!of_device_is_available(node)) {
			of_node_put(node);
			return -ENODEV;
		}
	} else {
		ret = tetris_unique_node(compatible, &node);
		if (ret)
			return ret;
	}
	ret = of_address_to_resource(node, 0, &res);
	if (!ret)
		ret = tetris_resource_range(&res);
	if (!ret && exclusive)
		ret = tetris_resource_claim(dev, &res, &claim);
	if (ret) {
		of_node_put(node);
		return ret;
	}
	/* Shared syscon: retain the actual node, never map it or claim its owner. */
	return devm_add_action_or_reset(dev, tetris_node_put, node);
}

/* platform_probe performs defaults/genpd before calling our probe. Check before
 * driver registration, too. OF population/hot-add is outside this fixed-DT draft. */
static inline int tetris_passive_node(struct device_node *node)
{
	struct device_node *parent;
	bool unsafe;

	if (!node || !of_device_is_available(node))
		return -ENODEV;
	if (of_find_property(node, "power-domains", NULL) ||
	    of_find_property(node, "assigned-clocks", NULL) ||
	    of_find_property(node, "assigned-clock-parents", NULL) ||
	    of_find_property(node, "assigned-clock-rates", NULL) ||
	    of_find_property(node, "iommus", NULL))
		return -EOPNOTSUPP;
	parent = of_get_parent(node);
	while (parent) {
		struct device_node *next;

		unsafe = of_find_property(parent, "iommu-map", NULL) != NULL;
		next = of_get_parent(parent);
		of_node_put(parent);
		if (unsafe) {
			of_node_put(next);
			return -EOPNOTSUPP;
		}
		parent = next;
	}
	return 0;
}

static inline int tetris_preflight_driver(const char *compatible)
{
	struct device_node *node;
	int ret;

	ret = tetris_unique_node(compatible, &node);
	/* An absent/disabled target permits inert registration, not probe success. */
	if (ret == -ENODEV)
		return 0;
	if (ret)
		return ret;
	ret = tetris_passive_node(node);
	of_node_put(node);
	return ret;
}

static inline void tetris_hif_release(void *data)
{
	struct tetris_hif_lease *lease = data;

	module_put(lease->owner);
	put_device(&lease->pdev->dev);
}

static inline int tetris_hif_acquire(struct device *consumer,
		struct platform_device *supplier, unsigned int id)
{
	const char *name = id == CCIF_HIF_ID ? "tetris_ccif_resources" :
		"tetris_dpmaif_resources";
	struct tetris_hif_resources *res;
	struct tetris_hif_lease *lease;
	unsigned int i;
	int ret = -EPROBE_DEFER;

	if (id != CCIF_HIF_ID && id != DPMAIF_HIF_ID)
		return -EINVAL;
	lease = devm_kzalloc(consumer, sizeof(*lease), GFP_KERNEL);
	if (!lease)
		return -ENOMEM;
	if (!device_trylock(&supplier->dev))
		return -EPROBE_DEFER;
	if (!device_is_bound(&supplier->dev))
		goto out;
	/* Legacy suppliers use platform_data; their drvdata is never interpreted. */
	if (!supplier->dev.driver || strcmp(supplier->dev.driver->name, name)) {
		ret = -EPROTOTYPE;
		goto out;
	}
	res = platform_get_drvdata(supplier);
	ret = -EPROTO;
	if (!res || res->pdev != supplier || res->hif_id != id ||
	    res->owner != supplier->dev.driver->owner || !res->owner ||
	    res->nmem != (id == CCIF_HIF_ID ? 2U : 4U) ||
	    res->nclk != (id == CCIF_HIF_ID ? 6U : 3U) ||
	    !res->nirq || res->nirq > ARRAY_SIZE(res->irq))
		goto out;
	for (i = 0; i < res->nmem; i++) {
		if (tetris_resource_range(&res->mem[i]) || !res->claim[i])
			goto out;
	}
	for (i = 0; i < res->nclk; i++) {
		if (IS_ERR_OR_NULL(res->clk[i]))
			goto out;
	}
	for (i = 0; i < res->nirq; i++) {
		if (!tetris_irq_shape(&res->irq[i]))
			goto out;
	}
	if (!try_module_get(res->owner)) {
		ret = -ENODEV;
		goto out;
	}
	lease->owner = res->owner;
	lease->pdev = supplier;
	get_device(&supplier->dev);
	ret = devm_add_action_or_reset(consumer, tetris_hif_release, lease);
out:
	device_unlock(&supplier->dev);
	return ret;
}
#endif
