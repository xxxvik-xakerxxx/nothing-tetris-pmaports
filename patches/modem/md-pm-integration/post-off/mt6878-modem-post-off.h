/* SPDX-License-Identifier: GPL-2.0-only */
/* Staged include AFTER mt6878-modem-adopt.h; no callers in the frozen provider. */
#ifndef MT6878_MODEM_POST_OFF_H
#define MT6878_MODEM_POST_OFF_H

#include <linux/lockdep.h>
#include <linux/mfd/syscon.h>

#define MT6878_MD_POST_OFF_TOP_REG 0
#define MT6878_MD_POST_OFF_TOP_MASK (BIT(8) | BIT(9))

/* Non-devm sidecar of the one retained native first-OFF owner, through reboot. */
struct mt6878_md_post_off_top {
	struct mt6878_md_adoption *owner;
	struct device_node *node;
	struct regmap *map;
	bool acquire_attempted;
	bool acquired;
	bool gate_attempted;
	bool top_only_complete;
	u32 off[5];
	u32 value;
};

/* Both native locks belong to the caller; they are serialization, not inhibition. */
static int mt6878_md_post_off_owner(struct scpsys_domain *pd,
				  struct mt6878_md_adoption *owner)
{
	if (!pd || !owner)
		return -EINVAL;
	lockdep_assert_held(&mt6878_md_first_off_lock);
	lockdep_assert_held(&owner->lock);
	if (owner->first_error)
		return owner->first_error;
	if (owner != mt6878_md_first_off_owner || !owner->supplier ||
	    owner->supplier != pd->scpsys->dev)
		return -EXDEV;
	if (owner->state != MT6878_MD_FIRST_OFF_COMPLETE || owner->attached)
		return -EBUSY;
	return 0;
}

/* Mapping only. Preserve node/map and the first errno even on failed acquisition. */
static int mt6878_md_post_off_top_acquire(struct scpsys_domain *pd,
					struct mt6878_md_adoption *owner,
					struct mt6878_md_post_off_top *top)
{
	u32 width;
	int ret;

	if (!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_POST_OFF_TOP_STAGING))
		return -EOPNOTSUPP;
	if (!top)
		return -EINVAL;
	ret = mt6878_md_post_off_owner(pd, owner);
	if (ret)
		return ret;
	if (top->owner && top->owner != owner)
		return -EXDEV;
	if (top->acquire_attempted)
		return -EALREADY;
	top->owner = owner;
	top->acquire_attempted = true;
	ret = mt6878_md_first_off_profile(pd);
	if (!ret)
		ret = mt6878_md_adopt_binding(pd, owner->modem, false);
	if (!ret)
		ret = mt6878_md_adopt_revalidate_resources(pd, owner);
	if (ret)
		goto fault;
	if (of_count_phandle_with_args(owner->modem, "ccci-topckgen", NULL) != 1) {
		ret = -EINVAL;
		goto fault;
	}
	top->node = of_parse_phandle(owner->modem, "ccci-topckgen", 0);
	ret = mt6878_md_adopt_map_node(top->node,
				      "mediatek,mt6878-topckgen", 0x10000000);
	if (ret)
		goto fault;
	if (!of_device_is_available(top->node) ||
	    of_property_present(top->node, "big-endian") ||
	    of_property_present(top->node, "native-endian")) {
		ret = -EINVAL;
		goto fault;
	}
	if (of_property_present(top->node, "reg-io-width")) {
		ret = mt6878_md_adopt_scalar(top->node, "reg-io-width", 4);
		if (ret)
			goto fault;
	}
	/* Cached native syscon; never a private ioremap or a modem MMIO window. */
	top->map = device_node_to_regmap(top->node);
	if (IS_ERR_OR_NULL(top->map)) {
		ret = top->map ? PTR_ERR(top->map) : -ENODEV;
		goto fault;
	}
	ret = regmap_get_val_bytes(top->map);
	width = ret > 0 ? ret : 0;
	if (width != sizeof(u32)) {
		ret = ret < 0 ? ret : -EINVAL;
		goto fault;
	}
	top->acquired = true;
	return 0;
fault:
	return mt6878_md_adopt_fault(owner, ret);
}

/*
 * TOP-only primitive, not a full shutdown entry point. The caller must first
 * finish owned UFS unblock, >=4ms settle and the real FLIGHT(true) operation.
 * No boolean "inhibited" or secure-return-as-proof argument exists here.
 */
static int mt6878_md_post_off_top_gate(struct scpsys_domain *pd,
				     struct mt6878_md_adoption *owner,
				     struct mt6878_md_post_off_top *top)
{
	int ret;

	if (!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_POST_OFF_TOP_STAGING))
		return -EOPNOTSUPP;
	if (!top)
		return -EINVAL;
	ret = mt6878_md_post_off_owner(pd, owner);
	if (ret)
		return ret;
	if (top->owner != owner)
		return -EXDEV;
	if (!top->acquired || IS_ERR_OR_NULL(top->map))
		return -ENODATA;
	if (top->gate_attempted)
		return -EALREADY;
	top->gate_attempted = true;
	/* Recheck current physical OFF, not just the software completion enum. */
	ret = mt6878_md_first_off_readback(pd, top->off);
	if (ret)
		goto fault;
	/* One locked masked RMW; preserve all shared TOP bits outside bits 8/9. */
	ret = regmap_set_bits(top->map, MT6878_MD_POST_OFF_TOP_REG,
			      MT6878_MD_POST_OFF_TOP_MASK);
	if (ret)
		goto fault;
	ret = regmap_read(top->map, MT6878_MD_POST_OFF_TOP_REG, &top->value);
	if (ret)
		goto fault;
	if ((top->value & MT6878_MD_POST_OFF_TOP_MASK) != MT6878_MD_POST_OFF_TOP_MASK) {
		ret = -EIO;
		goto fault;
	}
	top->top_only_complete = true;
	return 0;
fault:
	/* No rollback, ungate, retry, regulator, SMC, reset or MTCMOS ON. */
	return mt6878_md_adopt_fault(owner, ret);
}

#endif
