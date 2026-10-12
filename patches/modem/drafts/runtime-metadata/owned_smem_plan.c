/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/string.h>
#include "ccci_util_lib_main.h"
#include "tetris_runtime_smem/smem.h"
#include "smem_boot_evidence/boot_evidence.h"
#include "smem_reservation.h"

#if defined(CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ) && CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ
#if !defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) || !CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
#error "Tetris initial read requires the isolated resource-only profile"
#endif
#include <linux/io.h>
#include <linux/ioport.h>
#include <asm/page.h>
#include <asm/ptrace.h>
#include <asm/sysreg.h>
#endif

#if defined(CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY) && CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
#if !defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) || !CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
#error "Tetris mapped SMEM requires the isolated resource-only profile"
#endif
#if defined(CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ) && CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ
#error "Tetris mapped SMEM cannot be combined with the initial-read profile"
#endif
#include <linux/ioport.h>
#include <asm/page.h>
#include <asm/ptrace.h>
#include <asm/sysreg.h>
#include "tetris_runtime_smem/private.h"
#endif

/* Sole serialized util init/exit lifetime; no runtime consumer. */
static struct {
	struct ccci_mem_layout layout;
	struct ccci_smem_region nc[26], cache[11];
	struct tetris_smem_boot_evidence boot_evidence;
	bool has_boot_evidence;
	bool ready;
#if defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) && CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
	struct tetris_smem_extent_plan extents;
	struct tetris_smem_reservation reservation;
	struct tetris_smem_owner *owner;
#endif
} tetris_owned_smem_plan;

static int collect_boot_evidence(const struct tetris_metadata_banks *banks)
{
	struct device_node *node;
	struct tetris_smem_boot_evidence evidence;
	const struct ccci_mem_region *regions[2] = {
		&tetris_owned_smem_plan.layout.md_bank4_noncacheable_total,
		&tetris_owned_smem_plan.layout.md_bank4_cacheable_total,
	};
	unsigned char wire[TETRIS_SMEM_BOOT_BYTES];
	unsigned int i;
	int length = 0, ret = 0;

	/* The producer uses this sole disabled anchor; importer checked uniqueness.
	 * Absence supports older loaders. A present malformed record is fatal.
	 */
	node = of_find_node_by_path("/modem");
	if (!node)
		return -ENODEV;
	if (!of_device_is_compatible(node, "mediatek,mddriver")) {
		ret = -EINVAL;
		goto put;
	}
	if (!of_find_property(node, TETRIS_SMEM_BOOT_PROPERTY, &length))
		goto put;
	if (length != (int)sizeof(wire)) {
		ret = -EMSGSIZE;
		goto put;
	}
	ret = of_property_read_u8_array(node, TETRIS_SMEM_BOOT_PROPERTY, wire, sizeof(wire));
put:
	of_node_put(node);
	if (ret || !length)
		return ret;
	ret = tetris_smem_boot_decode(wire, sizeof(wire), banks, sizeof(*banks),
			&evidence, sizeof(evidence));
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(regions); i++) {
		if (regions[i]->base_ap_view_phy != evidence.record[i].range_start ||
		    !regions[i]->size || regions[i]->size > evidence.record[i].range_size ||
		    regions[i]->base_ap_view_vir)
			return -ERANGE;
	}
	/* Historical BL33 readbacks only, never Linux NS admission or a mapping. */
	tetris_owned_smem_plan.boot_evidence = evidence;
	tetris_owned_smem_plan.has_boot_evidence = true;
	return 0;
}

#if defined(CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ) && CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ
static int initial_nc_read(const struct tetris_metadata_banks *banks)
{
	const struct tetris_smem_extent_plan *plan = &tetris_owned_smem_plan.extents;
	const struct tetris_smem_reservation *claims = &tetris_owned_smem_plan.reservation;
	const struct tetris_smem_boot_evidence *evidence = &tetris_owned_smem_plan.boot_evidence;
	const struct tetris_smem_boot_record *record = &evidence->record[0];
	const struct tetris_smem_extent *nc = &plan->span[0];
	struct tetris_smem_extent_plan exact;
	void __iomem *mapped;
	u32 word;
	unsigned int i;
	int ret;

	if (!tetris_owned_smem_plan.owner || !tetris_owned_smem_plan.has_boot_evidence)
		return -ENODATA;
	ret = tetris_smem_extent_preview(tetris_owned_smem_plan.owner, &exact);
	if (ret)
		return ret;
	if (!plan->count || plan->count > TETRIS_SMEM_SPANS_MAX ||
	    plan->count != exact.count || claims->count != plan->count)
		return -ERANGE;
	/* Revalidate the copied capsule and actual claims before any SMEM access. */
	for (i = 0; i < plan->count; i++) {
		const struct tetris_smem_extent *span = &plan->span[i];
		const struct resource *held = claims->held[i];

		if (span->bank != exact.span[i].bank || span->base != exact.span[i].base ||
		    span->bytes != exact.span[i].bytes || !span->bytes ||
		    span->base > ~0ULL - span->bytes || !held ||
		    held->start != span->base || held->end != span->base + span->bytes - 1)
			return -ERANGE;
	}
	if (nc->bank != 0 || nc->bytes < PAGE_SIZE || !banks->nc.base ||
	    banks->nc.base > ~0ULL - banks->nc.capacity ||
	    ((nc->base | nc->bytes) & (PAGE_SIZE - 1)) ||
	    nc->base < banks->nc.base || nc->base - banks->nc.base >= banks->nc.capacity ||
	    nc->bytes > banks->nc.capacity - (nc->base - banks->nc.base))
		return -ERANGE;
	if (evidence->version != 1 || evidence->bytes != TETRIS_SMEM_BOOT_BYTES ||
	    evidence->scope != 1 || evidence->count != 2 ||
	    record->bank != 0 || record->slot != 42 ||
	    record->reservation_base != banks->nc.base ||
	    record->reservation_capacity != banks->nc.capacity)
		return -EBADMSG;
	if (record->range_start != banks->nc.base || !record->range_size ||
	    record->range_size > banks->nc.capacity ||
	    record->range_start > ~0ULL - record->range_size ||
	    ((record->range_start | record->range_size) & 4095) ||
	    nc->base < record->range_start ||
	    nc->base - record->range_start >= record->range_size ||
	    nc->bytes > record->range_size - (nc->base - record->range_start))
		return -ERANGE;
	if (record->actual_enable != 1 || record->actual_start != record->range_start ||
	    (record->actual_end & ~TETRIS_SMEM_BOOT_END_MARKER) !=
			record->range_start + record->range_size ||
	    ((record->policy[7] >> 34) & 3ULL) != 3ULL)
		return -EACCES;
	/* Nonshipping initial-read hypothesis: scope-1 history is not immutable
	 * permission or protection against an independent secure writer. Slot
	 * overlap arbitration remains unknown. No new certificate is asserted.
	 */
	if (read_sysreg(CurrentEL) != CurrentEL_EL1)
		return -EACCES;
	mapped = ioremap_wc((phys_addr_t)nc->base, PAGE_SIZE);
	if (!mapped)
		return -ENOMEM;
	word = readl(mapped);
	iounmap(mapped);
	pr_info("Tetris CCCI: initial NC read completed; %s\n", word ? "nonzero" : "zero");
	return 0;
}
#endif

#if defined(CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY) && CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
static int map_owned_smem(const struct tetris_metadata_banks *banks)
{
	const struct tetris_smem_extent_plan *plan = &tetris_owned_smem_plan.extents;
	const struct tetris_smem_reservation *claims = &tetris_owned_smem_plan.reservation;
	const struct tetris_smem_boot_evidence *evidence = &tetris_owned_smem_plan.boot_evidence;
	struct tetris_smem_owner *owner = tetris_owned_smem_plan.owner;
	struct tetris_metadata_banks snapshot;
	struct tetris_smem_extent_plan exact;
	unsigned int i, j;
	int ret;

	if (!owner || !tetris_owned_smem_plan.has_boot_evidence)
		return -ENODATA;
	ret = mtk_ccci_owned_banks_copy(&snapshot);
	if (ret)
		return ret;
	if (memcmp(&snapshot, banks, sizeof(snapshot)) ||
	    memcmp(&owner->banks, banks, sizeof(snapshot)))
		return -ERANGE;
	ret = tetris_smem_extent_preview(owner, &exact);
	if (ret)
		return ret;
	if (!plan->count || plan->count > TETRIS_SMEM_SPANS_MAX ||
	    plan->count != exact.count || claims->count != plan->count)
		return -ERANGE;
	if (evidence->version != 1 || evidence->bytes != TETRIS_SMEM_BOOT_BYTES ||
	    evidence->scope != 1 || evidence->count != 2)
		return -EBADMSG;
	for (i = 0; i < 2; i++) {
		const struct tetris_metadata_window *bank = i ? &banks->cache : &banks->nc;
		const struct tetris_smem_boot_record *record = &evidence->record[i];

		if (!bank->base || !bank->capacity || bank->base > ~0ULL - bank->capacity ||
		    ((bank->base | bank->capacity) & (PAGE_SIZE - 1)))
			return -ERANGE;
		if (record->bank != i || record->slot != 42 + i ||
		    record->reservation_base != bank->base ||
		    record->reservation_capacity != bank->capacity)
			return -EBADMSG;
		if (record->range_start != bank->base || !record->range_size ||
		    record->range_size > bank->capacity ||
		    record->range_start > ~0ULL - record->range_size ||
		    ((record->range_start | record->range_size) & 4095))
			return -ERANGE;
		if (record->actual_enable != 1 || record->actual_start != record->range_start ||
		    (record->actual_end & ~TETRIS_SMEM_BOOT_END_MARKER) !=
				record->range_start + record->range_size ||
		    ((record->policy[7] >> 34) & 3ULL) != 3ULL)
			return -EACCES;
	}
	for (i = 0; i < plan->count; i++) {
		const struct tetris_smem_extent *span = &plan->span[i];
		const struct resource *held = claims->held[i];
		const struct tetris_smem_boot_record *record;

		if (span->bank > 1 || span->bank != exact.span[i].bank ||
		    span->base != exact.span[i].base || span->bytes != exact.span[i].bytes ||
		    !span->bytes || ((span->base | span->bytes) & (PAGE_SIZE - 1)) ||
		    span->base > ~0ULL - span->bytes || !held ||
		    held->start != span->base || held->end != span->base + span->bytes - 1)
			return -ERANGE;
		record = &evidence->record[span->bank];
		if (span->base < record->range_start ||
		    span->base - record->range_start >= record->range_size ||
		    span->bytes > record->range_size - (span->base - record->range_start))
			return -ERANGE;
		for (j = 0; j < ARRAY_SIZE(owner->rows); j++) {
			const struct tetris_smem_row *row = &owner->rows[j];
			const struct tetris_metadata_window *bank = row->bank ? &banks->cache : &banks->nc;

			if (row->bank == span->bank && row->size && (row->flags & 8) &&
			    span->base < bank->base + row->offset + row->size &&
			    bank->base + row->offset < span->base + span->bytes)
				return -EADDRNOTAVAIL;
		}
	}
	/* Initial EL1 inherits matching trustedboot evidence. This is not a fresh
	 * NS certificate, protection against independent writers, or modem READY.
	 */
	if (read_sysreg(CurrentEL) != CurrentEL_EL1)
		return -EACCES;
	ret = tetris_smem_map_private(owner);
	if (ret)
		return ret;
	return tetris_smem_export_mapped_private(owner, &tetris_owned_smem_plan.layout,
		tetris_owned_smem_plan.nc, ARRAY_SIZE(tetris_owned_smem_plan.nc),
		tetris_owned_smem_plan.cache, ARRAY_SIZE(tetris_owned_smem_plan.cache));
}
#endif

void mtk_ccci_owned_smem_cleanup(void)
{
#if defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) && CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
	/* No profile publishes the owner. Destroy unwinds private mappings before
	 * releasing claims; successful resource/mapped init remains boot-pinned.
	 */
	if (tetris_owned_smem_plan.owner) {
		int ret = tetris_smem_destroy(tetris_owned_smem_plan.owner);

		if (WARN_ON(ret))
			return;
	}
	tetris_smem_release_extents(&tetris_owned_smem_plan.reservation);
#endif
	memset(&tetris_owned_smem_plan, 0, sizeof(tetris_owned_smem_plan));
}

int mtk_ccci_owned_smem_init(void)
{
	struct tetris_metadata_banks banks;
	struct tetris_smem_owner *owner = NULL;
	int ret;

	if (tetris_owned_smem_plan.ready)
		return -EALREADY;
	ret = mtk_ccci_owned_banks_copy(&banks);
	if (ret)
		return ret;
	ret = tetris_smem_from_arguments(&banks, &owner);
	if (ret)
		return ret;
	ret = tetris_smem_preview(owner, &tetris_owned_smem_plan.layout,
			tetris_owned_smem_plan.nc, ARRAY_SIZE(tetris_owned_smem_plan.nc),
			tetris_owned_smem_plan.cache, ARRAY_SIZE(tetris_owned_smem_plan.cache));
#if defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) && CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
	if (!ret)
		ret = tetris_smem_extent_preview(owner, &tetris_owned_smem_plan.extents);
#endif
#if defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) && CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
	tetris_owned_smem_plan.owner = owner;
#else
	{
		int release = tetris_smem_destroy(owner);

		if (!ret)
			ret = release;
	}
#endif
	if (!ret)
		ret = collect_boot_evidence(&banks);
#if defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) && CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
	if (!ret)
		ret = tetris_owned_smem_plan.has_boot_evidence ?
			tetris_smem_reserve_extents(&tetris_owned_smem_plan.extents,
				&tetris_owned_smem_plan.boot_evidence,
				&tetris_owned_smem_plan.reservation) : -ENODATA;
#endif
#if defined(CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ) && CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ
	if (!ret)
		ret = initial_nc_read(&banks);
#endif
#if defined(CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY) && CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
	if (!ret)
		ret = map_owned_smem(&banks);
#endif
	if (ret) {
		mtk_ccci_owned_smem_cleanup();
		return ret;
	}
	tetris_owned_smem_plan.ready = true;
#if defined(CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY) && CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
	/* No runtime consumer can release these boot-lifetime resources. */
	__module_get(THIS_MODULE);
#if !defined(CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ) || !CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ
#if !defined(CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY) || !CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
	pr_info("Tetris CCCI: kernel SMEM extents reserved; count=%u; physical access disabled\n",
		tetris_owned_smem_plan.reservation.count);
#endif
#endif
#endif
#if !defined(CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ) || !CONFIG_TETRIS_CCCI_SMEM_INITIAL_READ
#if !defined(CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY) || !CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
	if (tetris_owned_smem_plan.has_boot_evidence)
		pr_info("Tetris CCCI: SMEM boot evidence retained; Linux NS admission not established\n");
	pr_info("Tetris CCCI: owned SMEM plan ready; NC=%u cache=%u; memory access disabled\n",
		tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.size,
		tetris_owned_smem_plan.layout.md_bank4_cacheable_total.size);
#endif
#endif
#if defined(CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY) && CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY
	pr_info("Tetris CCCI: private SMEM mappings retained; no memory access or transport\n");
#endif
	return 0;
}
