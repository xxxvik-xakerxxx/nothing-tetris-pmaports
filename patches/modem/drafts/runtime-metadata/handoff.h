/* SPDX-License-Identifier: GPL-2.0-only */
/* Observed boot result and AP tag reservation, not firmware/NS attestation. */
#include <linux/of_reserved_mem.h>
#include <linux/unaligned.h>
#include <linux/ioport.h>
#include <asm/page.h>
#include "metadata_resources.h"

struct tetris_nomap_cover {
	u64 cursor, end;
};

static int tetris_nomap_resource(struct resource *resource, void *data)
{
	struct tetris_nomap_cover *cover = data;

	/* arm64 request_standard_resources creates these top-level resources
	 * from NOMAP memblock.memory, not from the reserved_mem catalogue.
	 * walk_iomem_res_desc clips start/end and preserves flags/parent.
	 */
	if (resource->flags != IORESOURCE_MEM || resource->parent != &iomem_resource ||
	    resource->start != cover->cursor || resource->end < resource->start ||
	    resource->end >= cover->end)
		return -EBADMSG;
	cover->cursor = resource->end + 1;
	return 0;
}

static int tetris_retained_nomap(u64 base, u64 capacity)
{
	struct tetris_nomap_cover cover;
	u64 address;
	int ret;

	if (!capacity || base > U64_MAX - capacity ||
	    ((base | capacity) & (PAGE_SIZE - 1)) ||
	    (u64)(phys_addr_t)base != base || (u64)(phys_addr_t)(base + capacity - 1) != base + capacity - 1)
		return -ERANGE;
	cover.cursor = base;
	cover.end = base + capacity;
	ret = walk_iomem_res_desc(IORES_DESC_NONE, IORESOURCE_MEM, base,
		cover.end - 1, &cover, tetris_nomap_resource);
	if (ret || cover.cursor != cover.end)
		return ret ? ret : -EBADMSG;
	/* A negative map-memory query alone also accepts holes. Positive full
	 * resource coverage above is required; then check every retained PFN.
	 * arm64 exports pfn_is_map_memory and selects ARCH_KEEP_MEMBLOCK, so this
	 * is usable by modules after init and detects later NOMAP clearing too.
	 * Plain no-compatible reservations have no init/device release callback.
	 * No physical memory is read; this is NOT NS/firmware permission evidence.
	 */
	for (address = base; address < cover.end; address += PAGE_SIZE) {
		unsigned long pfn = (unsigned long)(address >> PAGE_SHIFT);

		if ((u64)pfn != address >> PAGE_SHIFT || pfn_is_map_memory(pfn))
			return -EBADMSG;
	}
	return 0;
}

static int tetris_owned_banks(struct tetris_metadata_banks *out)
{
	static const char * const paths[] = {
		"/reserved-memory/tetris-modem-diagnostic",
		"/reserved-memory/tetris-modem-boot-nc",
		"/reserved-memory/tetris-modem-boot-cache",
		"/reserved-memory/tetris-modem-linux-tags",
	};
	static const u64 capacities[] = { 0x20000000, 0x8000000, 0x8000000, 65536 };
	struct tetris_metadata_banks banks = { 0 };
	struct tetris_metadata_window *windows[] = {
		&banks.firmware, &banks.nc, &banks.cache, &banks.tags,
	};
	struct device_node *owned[4] = { NULL, NULL, NULL, NULL };
	struct device_node *parent = NULL, *root = NULL, *child = NULL, *memory = NULL;
	struct device_node *sib = NULL;
	const u8 *raw;
	struct reserved_mem *reserved;
	unsigned int i, j, seen = 0;
	int length = 0, offset, ret = -EBADMSG;

	parent = of_find_node_by_path("/reserved-memory");
	root = of_find_node_by_path("/");
	if (!root || !parent || !of_find_property(parent, "ranges", &length) || length)
		goto out;
	for (i = 0; i < 4; i++) {
		u64 alignment = i == 3 ? 4096 : 0x2000000;

		owned[i] = of_find_node_by_path(paths[i]);
		if (!owned[i]) {
			ret = -ENODATA;
			goto out;
		}
		if (of_n_addr_cells(owned[i]) != 2 || of_n_size_cells(owned[i]) != 2 ||
		    !of_find_property(owned[i], "no-map", &length) || length ||
		    of_find_property(owned[i], "reusable", NULL) ||
		    of_find_property(owned[i], "compatible", NULL))
			goto out;
		raw = of_get_property(owned[i], "reg", &length);
		if (!raw || length != 16)
			goto out;
		windows[i]->base = get_unaligned_be64(raw);
		windows[i]->capacity = get_unaligned_be64(raw + 8);
		if (!windows[i]->base || (windows[i]->base & (alignment - 1)) ||
		    windows[i]->capacity != capacities[i] ||
		    windows[i]->base > U64_MAX - capacities[i] ||
		    (i < 3 && windows[i]->base + capacities[i] > (1ULL << 35)))
			goto out;
		reserved = of_reserved_mem_lookup(owned[i]);
		if (!reserved || (u64)reserved->base != windows[i]->base ||
		    (u64)reserved->size != windows[i]->capacity)
			goto out;
		ret = tetris_retained_nomap(windows[i]->base, windows[i]->capacity);
		if (ret)
			goto out;
		ret = -EBADMSG;
	}
	/* Source allocator rejects all overlapping static reservations, including
	 * owned-bank aliases and full unused tails. Never adopt service-diagnostic.
	 */
	for_each_child_of_node(parent, child) {
		raw = of_get_property(child, "reg", &length);
		if (!raw) {
			if (of_find_property(child, "reg", NULL))
				goto out;
			continue; /* source permits Linux dynamic allocations around ours */
		}
		if (length <= 0 || length % 16)
			goto out;
		for (offset = 0; offset < length; offset += 16) {
			u64 base = get_unaligned_be64(raw + offset);
			u64 capacity = get_unaligned_be64(raw + offset + 8);

			if (!capacity || base > U64_MAX - capacity)
				goto out;
			for (j = 0; j < 4; j++) {
				if (child == owned[j])
					continue;
				if (base < windows[j]->base + windows[j]->capacity &&
				    windows[j]->base < base + capacity)
					goto out;
			}
		}
	}
	/* find_dram requires all three MD allocations in ONE common DRAM bank.
	 * Final producer's AP tags may be in another bank, but cannot straddle it.
	 * This is source data from DT, never the current handset's addresses.
	 */
	raw = of_get_property(root, "#address-cells", &length);
	if (!raw || length != 4 || get_unaligned_be32(raw) != 2)
		goto out;
	raw = of_get_property(root, "#size-cells", &length);
	if (!raw || length != 4 || get_unaligned_be32(raw) != 2)
		goto out;
	for_each_node_by_type(memory, "memory") {
		raw = of_get_property(memory, "reg", &length);
		if (!raw || length <= 0 || length % 16)
			goto out;
		for (offset = 0; offset < length; offset += 16) {
			u64 base = get_unaligned_be64(raw + offset);
			u64 capacity = get_unaligned_be64(raw + offset + 8);
			unsigned int within = 0;

			if (!capacity || base > U64_MAX - capacity)
				goto out;
			for (j = 0; j < 4; j++) {
				if (windows[j]->base >= base && windows[j]->base - base < capacity &&
				    windows[j]->capacity <= capacity - (windows[j]->base - base))
					within |= 1U << j;
			}
			if ((within & 7) == 7)
				seen |= 7;
			seen |= within & 8;
		}
	}
	sib = of_find_node_by_path("/reserved-memory/tetris-modem-boot-sib");
	if (seen != 15 || sib)
		goto out;
	*out = banks;
	ret = 0;
out:
	of_node_put(sib);
	of_node_put(memory);
	of_node_put(child);
	for (i = 0; i < 4; i++)
		of_node_put(owned[i]);
	of_node_put(parent);
	of_node_put(root);
	return ret;
}

static int tetris_brom_result(const u8 *raw, int length)
{
	static const unsigned int errors[] = { 4, 8, 16, 24, 32 };
	unsigned int i;

	if (!raw)
		return -ENODATA;
	if (length != 80 || get_unaligned_le32(raw) != 1)
		return -EBADMSG;
	/* Preserve producer order; positive values are malformed, not errno. */
	for (i = 0; i < ARRAY_SIZE(errors); i++) {
		s32 error = (s32)get_unaligned_le32(raw + errors[i]);

		if (error)
			return error < 0 ? error : -EBADMSG;
	}
	if (get_unaligned_le32(raw + 12) != 11 ||
	    get_unaligned_le32(raw + 20) != 15 ||
	    get_unaligned_le32(raw + 28) != 0 ||
	    get_unaligned_le64(raw + 64) != 0x100000001ULL ||
	    get_unaligned_le64(raw + 72) != 0x100000001ULL)
		return -EAGAIN;
	return 0;
}

static int tetris_descriptor_bytes(const u8 *raw, int length, u64 *base,
		unsigned int *used)
{
	if (!raw)
		return -ENODATA;
	if (length != 32)
		return -EBADMSG;
	*base = get_unaligned_le64(raw);
	*used = get_unaligned_le32(raw + 8);
	if (!*base || (*base & 4095) || *base > U64_MAX - 65536 ||
	    *used < 21 * 76 || *used > 65536 ||
	    get_unaligned_le32(raw + 12) || get_unaligned_le32(raw + 16) != 2 ||
	    get_unaligned_le32(raw + 20) != 21 ||
	    get_unaligned_le32(raw + 24) || get_unaligned_le32(raw + 28))
		return -EBADMSG;
	return 0;
}

int mtk_ccci_validate_owned_handoff(struct device_node *consumer)
{
	static const struct { const char *name; u32 value; } scalars[] = {
		{ "nothing,modem-brom-preflight-stage", 16 },
		{ "nothing,modem-brom-preflight-status", 1 },
		{ "nothing,modem-brom-preflight-error", 0 },
		{ "nothing,modem-brom-loader-entered", 1 },
		{ "nothing,modem-brom-publication-error", 0 },
	};
	struct device_node *chosen = NULL, *node;
	struct tetris_metadata_banks banks;
	const u8 *raw;
	u64 base;
	unsigned int used, i;
	int length = 0, ret, count = 0;

	if (!consumer || !of_device_is_compatible(consumer, "mediatek,mddriver"))
		return -EINVAL;
	for_each_compatible_node(node, NULL, "mediatek,mddriver")
		count++;
	if (count != 1)
		return -EEXIST;
	chosen = of_find_node_by_path("/chosen");
	raw = of_get_property(chosen, "nothing,modem-brom-report", &length);
	ret = tetris_brom_result(raw, length);
	if (ret)
		goto out;
	for (i = 0; i < ARRAY_SIZE(scalars); i++) {
		raw = of_get_property(chosen, scalars[i].name, &length);
		if (!raw || length != 4 || get_unaligned_be32(raw) != scalars[i].value) {
			ret = -EBADMSG;
			goto out;
		}
	}
	if (of_find_property(consumer, "ccci,modem_info", NULL)) {
		ret = -EPROTONOSUPPORT;
		goto out;
	}
	raw = of_get_property(consumer, "ccci,modem_info_v2", &length);
	ret = tetris_descriptor_bytes(raw, length, &base, &used);
	if (ret)
		goto out;
	ret = tetris_owned_banks(&banks);
	if (ret)
		goto out;
	ret = banks.tags.base == base ? 0 : -EBADMSG;
out:
	of_node_put(chosen);
	return ret;
}
EXPORT_SYMBOL_GPL(mtk_ccci_validate_owned_handoff);

static int tetris_collect_owned_metadata(struct device_node *consumer)
{
	const u8 *raw;
	void __iomem *mapped;
	struct tetris_metadata_banks banks;
	u64 base;
	unsigned int used;
	int length, ret;

	ret = mtk_ccci_validate_owned_handoff(consumer);
	if (ret)
		return ret;
	raw = of_get_property(consumer, "ccci,modem_info_v2", &length);
	ret = tetris_descriptor_bytes(raw, length, &base, &used);
	if (ret)
		return ret;
	if ((u64)(phys_addr_t)base != base)
		return -ERANGE;
	ret = tetris_owned_banks(&banks);
	if (ret)
		return ret;
	if (banks.tags.base != base)
		return -EBADMSG;
	/* Map ONLY the source-created, cache-clean AP tag buffer. Never MD RAM. */
	mapped = ioremap_wc((phys_addr_t)base, 65536);
	if (!mapped)
		return -ENOMEM;
	ret = mtk_ccci_import_owned_tags(mapped, used, 2, 21, &banks);
	iounmap(mapped);
	/* No LK_LOAD_MD_EN, SMEM mapping/clearing or FSM READY publication. */
	return ret;
}
