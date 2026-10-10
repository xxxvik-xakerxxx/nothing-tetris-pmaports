/* SPDX-License-Identifier: GPL-2.0-only */
/* Called ONLY after complete tag framing checks, against the private AP copy. */
#include "metadata_resources.h"
#include "layout_model.h"

static int tetris_metadata_windows(const struct tetris_metadata_banks *banks)
{
	const struct tetris_metadata_window *windows[4];
	unsigned int i, j;

	if (!banks)
		return -ENODATA;
	windows[0] = &banks->firmware;
	windows[1] = &banks->nc;
	windows[2] = &banks->cache;
	windows[3] = &banks->tags;
	/* Exact current owned producer profile, not capacities inferred from CHK. */
	if (windows[0]->capacity != 0x20000000ULL ||
	    windows[1]->capacity != 0x8000000ULL ||
	    windows[2]->capacity != 0x8000000ULL || windows[3]->capacity != 65536)
		return -EPROTONOSUPPORT;
	for (i = 0; i < 4; i++) {
		unsigned long long alignment = i == 3 ? 4096 : 0x2000000;
		const struct tetris_metadata_window *a = windows[i];

		if (!a->base || (a->base & (alignment - 1)) ||
		    a->base > ~0ULL - a->capacity ||
		    (i < 3 && a->base + a->capacity > (1ULL << 35)))
			return -ERANGE;
		for (j = 0; j < i; j++) {
			const struct tetris_metadata_window *b = windows[j];

			if (a->base < b->base + b->capacity && b->base < a->base + a->capacity)
				return -EEXIST;
		}
	}
	return 0;
}

static int tetris_metadata_smem_row(const unsigned char *raw,
		unsigned long long base, unsigned int id, unsigned int offset,
		unsigned int size, unsigned int flags, unsigned int md_offset)
{
	/* Producer put_smem: AP virtual pointer and alignment are always zero.
	 * A padding row deliberately uses the NEXT real row's ID and flags=4.
	 */
	if (get_unaligned_le64(raw) != base + offset ||
	    get_unaligned_le64(raw + 8) || word(raw + 16) != id ||
	    word(raw + 20) != offset || word(raw + 24) != size || word(raw + 28) ||
	    word(raw + 32) != flags || word(raw + 36) != md_offset + offset)
		return -EBADMSG;
	return 0;
}

static int tetris_metadata_smem(const unsigned char *raw, unsigned int bytes,
		const struct tetris_modem_smem_entry *entries, unsigned int count,
		const struct tetris_metadata_window *bank, unsigned int md_offset)
{
	unsigned int i, cursor = 0, used = 0;
	int ret;

	for (i = 0; i < count; i++) {
		const struct tetris_modem_smem_entry *entry = &entries[i];

		if (entry->offset < cursor || entry->offset > bank->capacity ||
		    entry->size > bank->capacity - entry->offset ||
		    entry->offset > 0xffffffffU - md_offset ||
		    entry->size > 0xffffffffU - md_offset - entry->offset)
			return -ERANGE;
		if (entry->offset > cursor) {
			if (bytes - used < 40)
				return -EBADMSG;
			ret = tetris_metadata_smem_row(raw + used, bank->base, entry->id,
				cursor, entry->offset - cursor, 4, md_offset);
			if (ret)
				return ret;
			used += 40;
		}
		if (bytes - used < 40)
			return -EBADMSG;
		ret = tetris_metadata_smem_row(raw + used, bank->base, entry->id,
			entry->offset, entry->size, entry->flags, md_offset);
		if (ret)
			return ret;
		used += 40;
		cursor = entry->offset + entry->size;
	}
	return used == bytes ? 0 : -EBADMSG;
}

static int tetris_metadata_semantics(const unsigned char *snapshot,
		const unsigned int offsets[21], const unsigned int lengths[21],
		const struct tetris_metadata_banks *banks)
{
	const unsigned char *chk = snapshot + offsets[7];
	const unsigned char *hdr = snapshot + offsets[1];
	struct tetris_modem_memory_map memory;
	struct tetris_modem_smem_plan smem;
	struct tetris_modem_smem_inputs inputs;
	unsigned int logical = word(chk + 172), rom_size = word(snapshot + offsets[8]);
	unsigned int dsp_offset = word(chk + 184), dsp_capacity = word(chk + 188);
	unsigned int regions = word(chk + 192), i, j;
	int ret;

	ret = tetris_metadata_windows(banks);
	if (ret)
		return ret;
	if (!logical || logical > banks->firmware.capacity ||
	    !word(chk + 176) || word(chk + 176) > logical ||
	    rom_size < 512 || rom_size > 64U * 1024 * 1024 || (rom_size & 15) ||
	    rom_size > logical || !contained(dsp_offset, dsp_capacity, logical) ||
	    dsp_offset < rom_size || !regions || regions > 8)
		return -ERANGE;
	if (get_unaligned_le64(hdr) != banks->firmware.base ||
	    get_unaligned_le64(snapshot + offsets[9]) != banks->firmware.base ||
	    memchr_inv(hdr + 15, 0, 9))
		return -EBADMSG;
	for (i = 0; i < regions; i++) {
		unsigned int offset = word(chk + 196 + i * 8);
		unsigned int size = word(chk + 200 + i * 8);

		if (!contained(offset, size, logical))
			return -ERANGE;
		for (j = 0; j < i; j++) {
			unsigned int previous = word(chk + 196 + j * 8);
			unsigned int length = word(chk + 200 + j * 8);

			if (offset < previous + length && previous < offset + size)
				return -ERANGE;
		}
	}
	/* Exact source-derived splitting + post-EMI padding attributes. No ROM
	 * mapping and no invented DSP payload length: only retained CHK is used.
	 */
	ret = tetris_metadata_memory(chk, rom_size, banks->firmware.base,
		banks->firmware.capacity, &memory);
	if (ret)
		return ret;
	padding(&memory);
	if (lengths[10] != memory.count * 24)
		return -EBADMSG;
	for (i = 0; i < memory.count; i++) {
		const struct tetris_modem_block *block = &memory.blocks[i];
		const unsigned char *raw = snapshot + offsets[10] + i * 24;

		if (word(raw) != block->offset || word(raw + 4) != block->size ||
		    word(raw + 8) != block->info || word(raw + 12) != block->attributes ||
		    get_unaligned_le64(raw + 16) != block->physical)
			return -EBADMSG;
	}
	inputs = (struct tetris_modem_smem_inputs) {
		.drdi_version = word(chk + 0x190), .udc_en = word(chk + 0x184),
		.consys_size = word(chk + 0x180), .nv_cache_size = word(chk + 0x18c),
		.ccb_gear = 1, /* explicit source producer's normal Linux policy */
	};
	if (inputs.udc_en || !inputs.consys_size)
		return -EPROTONOSUPPORT;
	ret = tetris_modem_plan_smem_b41(&inputs, &smem);
	if (ret)
		return ret;
	if (smem.nc_capacity > banks->nc.capacity || smem.cache_capacity > banks->cache.capacity ||
	    lengths[12] != smem.nc_rows * 40 || lengths[14] != smem.cache_rows * 40)
		return -ERANGE;
	ret = tetris_metadata_smem(snapshot + offsets[12], lengths[12], smem.nc, 18,
		&banks->nc, 0);
	if (!ret)
		ret = tetris_metadata_smem(snapshot + offsets[14], lengths[14], smem.cache, 5,
			&banks->cache, 0x8000000);
	if (ret)
		return ret;
	/* Every legacy mirror and summary must describe the very same plan. */
	{
		const unsigned char *raw = snapshot + offsets[2];

		if (get_unaligned_le64(raw) != banks->nc.base || word(raw + 8) ||
		    word(raw + 12) != smem.nc_capacity || memchr_inv(raw + 16, 0, 16) ||
		    word(raw + 32) != smem.nc_capacity || word(raw + 36))
			return -EBADMSG;
		raw = snapshot + offsets[3];
		if (get_unaligned_le64(raw) != banks->cache.base + smem.cache[2].offset ||
		    word(raw + 8) != smem.cache[2].size || word(raw + 12))
			return -EBADMSG;
		raw = snapshot + offsets[15];
		if (get_unaligned_le64(raw) != banks->cache.base || word(raw + 8) != 0x8000000 ||
		    word(raw + 12) != smem.cache_capacity || word(raw + 16) != 5 || word(raw + 20))
			return -EBADMSG;
	}
	for (i = 0; i < 5; i++) {
		const unsigned char *raw = snapshot + offsets[16] + i * 24;

		if (get_unaligned_le64(raw) != banks->cache.base + smem.cache[i].offset ||
		    word(raw + 8) != smem.cache[i].offset || word(raw + 12) != smem.cache[i].size ||
		    word(raw + 16) != smem.cache[i].id || word(raw + 20))
			return -EBADMSG;
	}
	for (i = 0; i < 18; i++) {
		const unsigned char *raw = snapshot + offsets[18] + i * 16;

		if (word(raw) != smem.nc[i].offset || word(raw + 4) != smem.nc[i].offset ||
		    word(raw + 8) != smem.nc[i].size || word(raw + 12) != smem.nc[i].id)
			return -EBADMSG;
	}
	/* This closes layout consistency only. Signed platform selector and SMEM
	 * admission remain absent; this function must never imply AUTH or READY.
	 */
	return 0;
}
