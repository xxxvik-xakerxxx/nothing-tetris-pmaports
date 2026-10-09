// SPDX-License-Identifier: GPL-2.0-only
#include <linux/errno.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_reserved_mem.h>
#include <linux/overflow.h>
#include <linux/slab.h>
#include <linux/string.h>
#include "mt6878_md_handoff_reservation.h"

#ifdef MODULE
#error "MD handoff reservation owner must be built-in"
#endif

struct mt6878_md_handoff_reservation {
	struct device_node *rom_node, *smem_node;
	struct resource *rom_claim, *smem_claim;
	struct mt6878_md_handoff_state state;
};

static int md_reserved_range(struct device_node *node, u64 *base, u64 *size)
{
	struct device_node *parent;
	struct reserved_mem *reserved;
	struct resource resource, extra;
	u64 end;
	bool correct_parent;
	int ret, address_cells, size_cells;

	if (!node || !of_device_is_available(node))
		return -ENODEV;
	parent = of_get_parent(node);
	correct_parent = parent && !strcmp(parent->full_name, "/reserved-memory");
	of_node_put(parent);
	if (!correct_parent || !of_property_read_bool(node, "no-map") ||
	    of_property_read_bool(node, "reusable"))
		return -EINVAL;
	address_cells = of_n_addr_cells(node);
	size_cells = of_n_size_cells(node);
	if (address_cells < 1 || address_cells > 2 || size_cells < 1 || size_cells > 2 ||
	    of_property_count_u32_elems(node, "reg") != address_cells + size_cells)
		return -EINVAL;
	reserved = of_reserved_mem_lookup(node);
	if (!reserved || reserved->ops)
		return -EOPNOTSUPP;
	ret = of_address_to_resource(node, 0, &resource);
	if (ret)
		return ret;
	if (!of_address_to_resource(node, 1, &extra))
		return -EINVAL;
	if (!(resource.flags & IORESOURCE_MEM) || resource.end < resource.start ||
	    !reserved->size ||
	    check_add_overflow((u64)reserved->base, (u64)reserved->size, &end))
		return -EINVAL;
	/* lookup uses basename, not identity; never accept a mismatching range. */
	if (resource.start != reserved->base || resource.end != end - 1)
		return -ESTALE;
	*base = reserved->base;
	*size = reserved->size;
	return 0;
}

int mt6878_md_handoff_reserve(struct device_node *rom, struct device_node *smem,
			    const u8 digest_claim[32],
			    struct mt6878_md_handoff_reservation **out)
{
	struct mt6878_md_handoff_reservation *owner;
	u64 rom_end, smem_end;
	int ret;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!digest_claim || !rom || !smem || rom == smem)
		return -EINVAL;
	/* The record deliberately has no mutable-tree refresh or hot-unbind path. */
	if (IS_ENABLED(CONFIG_OF_DYNAMIC))
		return -EOPNOTSUPP;
	owner = kzalloc(sizeof(*owner), GFP_KERNEL);
	if (!owner)
		return -ENOMEM;
	ret = md_reserved_range(rom, &owner->state.rom_base, &owner->state.rom_size);
	if (ret)
		goto free;
	ret = md_reserved_range(smem, &owner->state.smem_base, &owner->state.smem_size);
	if (ret)
		goto free;
	rom_end = owner->state.rom_base + owner->state.rom_size;
	smem_end = owner->state.smem_base + owner->state.smem_size;
	if (owner->state.rom_base < smem_end && owner->state.smem_base < rom_end) {
		ret = -EINVAL;
		goto free;
	}
	owner->rom_claim = request_mem_region(owner->state.rom_base,
		owner->state.rom_size, "mt6878-md-rom-metadata");
	if (!owner->rom_claim) {
		ret = -EBUSY;
		goto free;
	}
	owner->smem_claim = request_mem_region(owner->state.smem_base,
		owner->state.smem_size, "mt6878-md-smem-metadata");
	if (!owner->smem_claim) {
		ret = -EBUSY;
		release_mem_region(owner->state.rom_base, owner->state.rom_size);
		goto free;
	}
	owner->rom_node = of_node_get(rom);
	owner->smem_node = of_node_get(smem);
	memcpy(owner->state.rom_digest, digest_claim, sizeof(owner->state.rom_digest));
	/* Publish once, after all claims. No caller retains a writable state alias. */
	*out = owner;
	return 0;
free:
	kfree(owner);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_handoff_reserve);

static int md_reserved_snapshot(void *context, struct mt6878_md_handoff_state *out)
{
	const struct mt6878_md_handoff_reservation *owner = context;

	if (!owner || !out)
		return -EINVAL;
	*out = owner->state;
	return 0;
}

static int md_reserved_authenticate(void *context,
				  const struct mt6878_md_handoff_state *state)
{
	const struct mt6878_md_handoff_reservation *owner = context;

	if (!owner || !state)
		return -EINVAL;
	if (state->rom_base != owner->state.rom_base ||
	    state->rom_size != owner->state.rom_size ||
	    state->smem_base != owner->state.smem_base ||
	    state->smem_size != owner->state.smem_size ||
	    memcmp(state->rom_digest, owner->state.rom_digest, sizeof(state->rom_digest)))
		return -ESTALE;
	/* Reservation/header/BROM status is not signature verification evidence. */
	return -ENOKEY;
}

const struct mt6878_md_handoff_owner mt6878_md_reserved_handoff_ops = {
	.module = THIS_MODULE,
	.snapshot = md_reserved_snapshot,
	.authenticate = md_reserved_authenticate,
};
EXPORT_SYMBOL_GPL(mt6878_md_reserved_handoff_ops);
MODULE_LICENSE("GPL");
