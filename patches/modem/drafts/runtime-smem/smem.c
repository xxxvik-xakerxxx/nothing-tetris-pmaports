/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/unaligned.h>
#include <asm/page.h>
#include "private.h"
#include "source_model.h"

static const struct tetris_metadata_window *bank_window(
		const struct tetris_smem_owner *owner, unsigned int bank)
{
	return bank ? &owner->banks.cache : &owner->banks.nc;
}

static int validate_rows(const unsigned char *raw, unsigned int bytes,
		const struct tetris_modem_smem_entry *entries, unsigned int count,
		struct tetris_smem_owner *owner, unsigned int bank, unsigned int first)
{
	const struct tetris_metadata_window *window = bank_window(owner, bank);
	unsigned int i, cursor = 0, used = 0, md_base = bank ? 0x8000000 : 0;

	if (!raw || !bytes || bytes % 40 || bytes > (count * 2) * 40)
		return -EBADMSG;
	for (i = 0; i < count; i++) {
		const struct tetris_modem_smem_entry *entry = &entries[i];
		unsigned int passes = entry->offset > cursor ? 2 : 1, pass;

		if (entry->offset < cursor || entry->offset > window->capacity ||
		    entry->size > window->capacity - entry->offset)
			return -ERANGE;
		for (pass = 0; pass < passes; pass++) {
			bool padding = passes == 2 && pass == 0;
			unsigned int offset = padding ? cursor : entry->offset;
			unsigned int size = padding ? entry->offset - cursor : entry->size;
			unsigned int flags = padding ? 4 : entry->flags;
			const unsigned char *row;

			if (bytes - used < 40)
				return -EBADMSG;
			row = raw + used;
			if (get_unaligned_le64(row) != window->base + offset ||
			    get_unaligned_le64(row + 8) || word(row + 16) != entry->id ||
			    word(row + 20) != offset || word(row + 24) != size ||
			    word(row + 28) || word(row + 32) != flags ||
			    word(row + 36) != md_base + offset)
				return -EBADMSG;
			used += 40;
		}
		owner->rows[first + i] = (struct tetris_smem_row) {
			.id = entry->id, .offset = entry->offset, .size = entry->size,
			.flags = entry->flags, .md_offset = md_base + entry->offset,
			.bank = bank,
		};
		cursor = entry->offset + entry->size;
	}
	return used == bytes ? 0 : -EBADMSG;
}

static int build_spans(struct tetris_smem_owner *owner)
{
	unsigned int i, j;
	struct tetris_smem_span *last = NULL;

	for (i = 0; i < ARRAY_SIZE(owner->rows); i++) {
		const struct tetris_smem_row *row = &owner->rows[i];
		const struct tetris_metadata_window *window = bank_window(owner, row->bank);
		unsigned long long start, end;

		if (row->flags & 8) {
			last = NULL;
			continue;
		}
		if (!row->size)
			continue;
		start = row->offset & ~((unsigned long long)PAGE_SIZE - 1);
		end = ((unsigned long long)row->offset + row->size + PAGE_SIZE - 1) &
			~((unsigned long long)PAGE_SIZE - 1);
		if ((window->base & (PAGE_SIZE - 1)) || end > window->capacity ||
		    end <= start || end > 0xffffffffU)
			return -ERANGE;
		/* Include actual alignment gaps in the extent, not summed row sizes.
		 * Page-rounded mappings must NEVER alias a NO_MAP region.
		 */
		if (last && last->bank == row->bank)
			last->size = end - last->offset;
		else {
			if (owner->span_count == ARRAY_SIZE(owner->spans))
				return -E2BIG;
			last = &owner->spans[owner->span_count++];
			last->bank = row->bank;
			last->offset = start;
			last->size = end - start;
		}
	}
	for (i = 0; i < owner->span_count; i++) {
		const struct tetris_smem_span *span = &owner->spans[i];

		for (j = 0; j < ARRAY_SIZE(owner->rows); j++) {
			const struct tetris_smem_row *row = &owner->rows[j];

			if (row->bank == span->bank && row->size && (row->flags & 8) &&
			    span->offset < row->offset + row->size &&
			    row->offset < span->offset + span->size)
				return -EADDRNOTAVAIL;
		}
	}
	return owner->span_count ? 0 : -ENODATA;
}

static struct ccci_smem_region *table_region(struct ccci_smem_region *table,
		unsigned int count, unsigned int id)
{
	unsigned int i;

	for (i = 0; i < count; i++) {
		if (table[i].id == id)
			return &table[i];
	}
	return NULL;
}

static void populate_tables(struct tetris_smem_owner *owner)
{
	struct ccci_smem_region *ccb, *alias;
	unsigned int i, j, section_a, section_b;

	memcpy(owner->nc, tetris_nc_template, sizeof(owner->nc));
	memcpy(owner->cache, tetris_cache_template, sizeof(owner->cache));
	for (i = 0; i < ARRAY_SIZE(owner->rows); i++) {
		const struct tetris_smem_row *row = &owner->rows[i];
		struct ccci_smem_region *region = table_region(
			row->bank ? owner->cache : owner->nc,
			row->bank ? ARRAY_SIZE(owner->cache) : ARRAY_SIZE(owner->nc), row->id);

		if (!region)
			continue;
		region->offset = row->offset;
		region->size = row->size;
		region->base_ap_view_phy = bank_window(owner, row->bank)->base + row->offset;
		region->base_md_view_phy = 0x40000000ULL + row->md_offset;
		region->base_ap_view_vir = row->virtual;
	}
	/* Exact post_cfg_for_ccb partition, but in private consumer-ready tables. */
	ccb = table_region(owner->cache, ARRAY_SIZE(owner->cache), SMEM_USER_CCB_DHL);
	section_a = ccb->size > 0x200000 ? 0x200000 : 0;
	section_b = section_a ? ccb->size - section_a : 0;
	ccb->size = section_a;
	for (j = SMEM_USER_CCB_MD_MONITOR; j <= SMEM_USER_CCB_META; j++) {
		alias = table_region(owner->cache, ARRAY_SIZE(owner->cache), j);
		*alias = *ccb;
		alias->id = j;
	}
	for (j = SMEM_USER_RAW_DHL; j <= SMEM_USER_RAW_MDM; j++) {
		alias = table_region(owner->cache, ARRAY_SIZE(owner->cache), j);
		*alias = *ccb;
		alias->id = j;
		alias->size = section_b;
		if (section_b) {
			alias->offset += section_a;
			alias->base_ap_view_phy += section_a;
			alias->base_md_view_phy += section_a;
			if (alias->base_ap_view_vir)
				alias->base_ap_view_vir = (unsigned char __iomem *)alias->base_ap_view_vir + section_a;
		}
	}
	owner->layout.md_bank0 = (struct ccci_mem_region) {
		.base_ap_view_phy = owner->banks.firmware.base, .size = owner->logical,
	};
	owner->layout.md_bank4_noncacheable_total = (struct ccci_mem_region) {
		.base_ap_view_phy = owner->banks.nc.base, .base_md_view_phy = 0x40000000,
		.size = owner->nc_size, .base_ap_view_vir = owner->rows[0].virtual,
	};
	owner->layout.md_bank4_cacheable_total = (struct ccci_mem_region) {
		.base_ap_view_phy = owner->banks.cache.base, .base_md_view_phy = 0x48000000,
		.size = owner->cache_size, /* CONSYS prefix is deliberately unmapped. */
	};
	owner->layout.md_bank4_noncacheable = owner->nc;
	owner->layout.md_bank4_cacheable = owner->cache;
}

int tetris_smem_create(const struct tetris_smem_input *input,
		struct tetris_smem_owner **output)
{
	struct tetris_smem_owner *owner;
	struct tetris_modem_smem_plan plan;
	struct tetris_modem_smem_inputs policy;
	const unsigned char *chk;
	int ret;

	if (!input || !output || !input->chk || input->chk_bytes != 512)
		return -EINVAL;
	ret = tetris_metadata_windows(&input->banks);
	if (ret)
		return ret;
	chk = input->chk;
	if (memcmp(chk, "CHECK_HEADER", 12) || word(chk + 12) != 6 ||
	    word(chk + 16) != 2 || word(chk + 20) != 14 || chk[168] != 1 ||
	    word(chk + 508) != 512 || !word(chk + 172) ||
	    word(chk + 172) > input->banks.firmware.capacity)
		return -EBADMSG;
	policy = (struct tetris_modem_smem_inputs) {
		.drdi_version = word(chk + 0x190), .udc_en = word(chk + 0x184),
		.consys_size = word(chk + 0x180), .nv_cache_size = word(chk + 0x18c),
		.ccb_gear = 1,
	};
	if (policy.udc_en || !policy.consys_size)
		return -EPROTONOSUPPORT;
	ret = tetris_modem_plan_smem_b41(&policy, &plan);
	if (ret)
		return ret;
	if (plan.nc_capacity > input->banks.nc.capacity ||
	    plan.cache_capacity > input->banks.cache.capacity ||
	    input->nc_bytes != plan.nc_rows * 40 || input->cache_bytes != plan.cache_rows * 40)
		return -ERANGE;
	owner = kzalloc(sizeof(*owner), GFP_KERNEL);
	if (!owner)
		return -ENOMEM;
	owner->banks = input->banks;
	owner->logical = word(chk + 172);
	/* Vendor total getters sum ALL wire rows, including padding, not the
	 * producer's rounded MPU capacity or the full LMB reservation tail.
	 */
	owner->nc_size = plan.nc[17].offset + plan.nc[17].size;
	owner->cache_size = plan.cache[4].offset + plan.cache[4].size;
	ret = validate_rows(input->nc, input->nc_bytes, plan.nc, 18, owner, 0, 0);
	if (!ret)
		ret = validate_rows(input->cache, input->cache_bytes, plan.cache, 5, owner, 1, 18);
	if (!ret)
		ret = build_spans(owner);
	if (ret) {
		kfree(owner);
		return ret;
	}
	mutex_init(&owner->lock);
	populate_tables(owner);
	owner->state = TETRIS_SMEM_VALIDATED;
	*output = owner;
	return 0;
}

static void unmap_private(struct tetris_smem_owner *owner)
{
	unsigned int i = owner->span_count;

	while (i) {
		struct tetris_smem_span *span = &owner->spans[--i];

		if (span->virtual) {
			iounmap(span->virtual);
			span->virtual = NULL;
		}
	}
}

static int fail_private(struct tetris_smem_owner *owner, int error)
{
	unsigned int i;

	if (!owner->first_error)
		owner->first_error = error;
	unmap_private(owner);
	for (i = 0; i < ARRAY_SIZE(owner->rows); i++)
		owner->rows[i].virtual = NULL;
	populate_tables(owner);
	owner->state = TETRIS_SMEM_FAILED;
	return owner->first_error;
}

int tetris_smem_map_private(struct tetris_smem_owner *owner)
{
	unsigned int i, j;
	int ret = 0;

	if (!owner)
		return -EINVAL;
	mutex_lock(&owner->lock);
	if (owner->state != TETRIS_SMEM_VALIDATED) {
		ret = owner->first_error ? owner->first_error : -EALREADY;
		goto out;
	}
	for (i = 0; i < owner->span_count; i++) {
		struct tetris_smem_span *span = &owner->spans[i];

		span->virtual = ioremap_wc(bank_window(owner, span->bank)->base + span->offset, span->size);
		if (!span->virtual) {
			ret = fail_private(owner, -ENOMEM);
			goto out;
		}
	}
	for (i = 0; i < ARRAY_SIZE(owner->rows); i++) {
		struct tetris_smem_row *row = &owner->rows[i];

		if (!row->size || (row->flags & 8))
			continue;
		for (j = 0; j < owner->span_count; j++) {
			const struct tetris_smem_span *span = &owner->spans[j];

			if (row->bank == span->bank && row->offset >= span->offset &&
			    row->offset + row->size <= span->offset + span->size) {
				row->virtual = (unsigned char __iomem *)span->virtual + (row->offset - span->offset);
				break;
			}
		}
	}
	populate_tables(owner);
	owner->state = TETRIS_SMEM_MAPPED;
out:
	mutex_unlock(&owner->lock);
	return ret;
}

void tetris_smem_slot_init(struct tetris_smem_slot *slot)
{
	mutex_init(&slot->lock);
	slot->owner = NULL;
}

int tetris_smem_publish_private(struct tetris_smem_slot *slot,
		struct tetris_smem_owner *owner)
{
	int ret = 0;

	if (!slot || !owner)
		return -EINVAL;
	/* Always slot -> owner. No caller callbacks or device/scope locks. */
	mutex_lock(&slot->lock);
	mutex_lock(&owner->lock);
	if (owner->state == TETRIS_SMEM_PUBLISHED)
		ret = -EALREADY;
	else if (owner->first_error)
		ret = owner->first_error;
	else if (slot->owner)
		ret = fail_private(owner, -EEXIST);
	else if (owner->state != TETRIS_SMEM_MAPPED)
		ret = fail_private(owner, -ENODATA);
	else {
		owner->state = TETRIS_SMEM_PUBLISHED;
		slot->owner = owner;
	}
	mutex_unlock(&owner->lock);
	mutex_unlock(&slot->lock);
	return ret;
}

static bool output_overlap(const void *a, size_t a_size, const void *b, size_t b_size)
{
	unsigned long start_a = (unsigned long)a, start_b = (unsigned long)b;

	if (start_a > ~0UL - a_size || start_b > ~0UL - b_size)
		return true;
	return start_a < start_b + b_size && start_b < start_a + a_size;
}

static int copy_layout(const struct tetris_smem_owner *owner,
		struct ccci_mem_layout *layout, struct ccci_smem_region *nc,
		unsigned int nc_count, struct ccci_smem_region *cache,
		unsigned int cache_count)
{
	if (!layout || !nc || !cache || nc_count < ARRAY_SIZE(owner->nc) ||
	    cache_count < ARRAY_SIZE(owner->cache) ||
	    output_overlap(layout, sizeof(*layout), nc, sizeof(owner->nc)) ||
	    output_overlap(layout, sizeof(*layout), cache, sizeof(owner->cache)) ||
	    output_overlap(nc, sizeof(owner->nc), cache, sizeof(owner->cache)) ||
	    output_overlap(owner, sizeof(*owner), layout, sizeof(*layout)) ||
	    output_overlap(owner, sizeof(*owner), nc, sizeof(owner->nc)) ||
	    output_overlap(owner, sizeof(*owner), cache, sizeof(owner->cache)))
		return -EINVAL;
	memcpy(nc, owner->nc, sizeof(owner->nc));
	memcpy(cache, owner->cache, sizeof(owner->cache));
	*layout = owner->layout;
	layout->md_bank4_noncacheable = nc;
	layout->md_bank4_cacheable = cache;
	return 0;
}

int tetris_smem_preview(struct tetris_smem_owner *owner,
		struct ccci_mem_layout *layout, struct ccci_smem_region *nc,
		unsigned int nc_count, struct ccci_smem_region *cache,
		unsigned int cache_count)
{
	int ret;

	if (!owner)
		return -EINVAL;
	mutex_lock(&owner->lock);
	if (owner->state != TETRIS_SMEM_VALIDATED)
		ret = owner->first_error ? owner->first_error : -EALREADY;
	else
		ret = copy_layout(owner, layout, nc, nc_count, cache, cache_count);
	mutex_unlock(&owner->lock);
	return ret;
}

int tetris_smem_export_private(struct tetris_smem_slot *slot,
		struct ccci_mem_layout *layout, struct ccci_smem_region *nc,
		unsigned int nc_count, struct ccci_smem_region *cache,
		unsigned int cache_count)
{
	struct tetris_smem_owner *owner;
	int ret = 0;

	if (!slot)
		return -EINVAL;
	mutex_lock(&slot->lock);
	owner = slot->owner;
	if (!owner)
		ret = -ENODATA;
	else
		ret = copy_layout(owner, layout, nc, nc_count, cache, cache_count);
	mutex_unlock(&slot->lock);
	return ret;
}

int tetris_smem_destroy(struct tetris_smem_owner *owner)
{
	if (!owner)
		return -EINVAL;
	mutex_lock(&owner->lock);
	if (owner->state == TETRIS_SMEM_PUBLISHED) {
		mutex_unlock(&owner->lock);
		return -EBUSY;
	}
	unmap_private(owner);
	mutex_unlock(&owner->lock);
	kfree(owner);
	return 0;
}
