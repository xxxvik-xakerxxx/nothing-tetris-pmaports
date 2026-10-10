/* SPDX-License-Identifier: GPL-2.0+ */
/* Generated pure layout logic from U-Boot 60cd9ade5b999732304f3b755c7dbe3d34307c13. */
#ifndef TETRIS_METADATA_LAYOUT_MODEL_H
#define TETRIS_METADATA_LAYOUT_MODEL_H
#define TETRIS_MODEM_MAX_BLOCKS 32

struct tetris_modem_layout {
	unsigned int memory_size;
	unsigned int logical_image_size;
	unsigned int rom_size;
	unsigned int dsp_offset;
	unsigned int dsp_capacity;
	unsigned int dsp_size;
	unsigned int region_count;
};

struct tetris_modem_block {
	unsigned int offset;
	unsigned int size;
	unsigned int info;
	unsigned int attributes;
	unsigned long long physical;
};

struct tetris_modem_memory_map {
	unsigned int count;
	struct tetris_modem_block blocks[TETRIS_MODEM_MAX_BLOCKS];
};

struct tetris_modem_smem_entry {
	unsigned int id;
	unsigned int offset;
	unsigned int size;
	unsigned int flags;
};

struct tetris_modem_smem_inputs {
	unsigned int drdi_version;
	unsigned int udc_en;
	unsigned int consys_size;
	unsigned int nv_cache_size;
	unsigned int ccb_gear;
};

struct tetris_modem_smem_plan {
	struct tetris_modem_smem_entry nc[18];
	struct tetris_modem_smem_entry cache[5];
	unsigned int nc_capacity;
	unsigned int cache_capacity;
	unsigned int nc_rows;
	unsigned int cache_rows;
};

static unsigned int word(const unsigned char *p)
{
	return (unsigned int)p[0] | (unsigned int)p[1] << 8 |
		(unsigned int)p[2] << 16 | (unsigned int)p[3] << 24;
}

static int contained(unsigned int offset, unsigned int size, unsigned int total)
{
	return size && offset < total && size <= total - offset;
}

static int annotate(struct tetris_modem_memory_map *map, unsigned int offset,
		    unsigned int size, unsigned int info, unsigned int attributes)
{
	unsigned int i;

	if (!size)
		return -EINVAL;
	for (i = 0; i < map->count; i++) {
		struct tetris_modem_block old = map->blocks[i];
		struct tetris_modem_block parts[3];
		unsigned int count = 0, end;

		if (offset < old.offset || offset - old.offset >= old.size)
			continue;
		if (size > old.size - (offset - old.offset))
			return -ERANGE;
		if (offset == old.offset && size == old.size &&
		    (old.info & info) == info &&
		    (old.attributes & attributes) == attributes)
			return -EINVAL;
		end = offset + size;
		if (offset != old.offset) {
			parts[count] = old;
			parts[count++].size = offset - old.offset;
		}
		parts[count] = old;
		parts[count].offset = offset;
		parts[count].size = size;
		parts[count].info |= info;
		parts[count++].attributes |= attributes;
		if (end != old.offset + old.size) {
			parts[count] = old;
			parts[count].offset = end;
			parts[count++].size = old.offset + old.size - end;
		}
		if (count - 1 > TETRIS_MODEM_MAX_BLOCKS - map->count)
			return -E2BIG;
		memmove(&map->blocks[i + count], &map->blocks[i + 1],
			(map->count - i - 1) * sizeof(old));
		memcpy(&map->blocks[i], parts, count * sizeof(old));
		map->count += count - 1;
		return 0;
	}
	return -ERANGE;
}

static int smem_place(struct tetris_modem_smem_entry *entries,
		      const unsigned int *alignments, unsigned int count,
		      unsigned int limit, unsigned int *capacity, unsigned int *rows)
{
	unsigned long long cursor = 0, offset;
	unsigned int i;

	*rows = count;
	for (i = 0; i < count; i++) {
		offset = cursor;
		if (alignments[i])
			offset = (cursor + alignments[i] - 1) &
				 ~((unsigned long long)alignments[i] - 1);
		if (offset != cursor)
			(*rows)++;
		cursor = offset + entries[i].size;
		if (cursor > limit)
			return -ERANGE;
		entries[i].offset = offset;
	}
	cursor = (cursor + 0xffff) & ~0xffffULL;
	if (!cursor || cursor > limit)
		return -ERANGE;
	*capacity = cursor;
	return 0;
}

static int tetris_modem_plan_smem_b41(const struct tetris_modem_smem_inputs *inputs,
			       struct tetris_modem_smem_plan *plan)
{
	static const unsigned int nc_ids[] = {
		31, 12, 13, 37, 18, 14, 15, 33, 0, 16, 4, 7, 8, 9, 19, 20, 40, 41,
	};
	static const unsigned int nc_sizes[] = {
		0x10000, 0x800, 0x6000, 0x8000, 0, 0x1000, 0x400, 0x200, 0x200,
		0x8000, 0x1000, 0x2000, 0xb000, 0xd000, 0xb4400, 0x1e400, 0, 0x10000,
	};
	static const unsigned int nc_align[18] = { [17] = 0x1000 };
	static const unsigned int cache_align[] = { 0x10000, 0x40, 0x100000, 0x10000, 0x80 };
	struct tetris_modem_smem_plan out = { 0 };
	unsigned int ccb_size, i;
	int ret;

	if (!inputs || !plan)
		return -EINVAL;
	if (inputs->drdi_version != 3 || inputs->udc_en > 1)
		return -EINVAL;
	switch (inputs->ccb_gear) {
	case 0:
	case 1:
		ccb_size = 0x1600000;
		break;
	case 2:
		ccb_size = 0xc00000;
		break;
	case 3:
		ccb_size = 0;
		break;
	case 4:
		ccb_size = 0x2000000;
		break;
	case 11:
		ccb_size = 0x400000;
		break;
	case 12:
		ccb_size = 0x4000000;
		break;
	case 13:
		ccb_size = 0x6000000;
		break;
	case 16:
		ccb_size = 0xc000000;
		break;
	default:
		return -EINVAL;
	}
	for (i = 0; i < 18; i++) {
		out.nc[i].id = nc_ids[i];
		out.nc[i].size = nc_sizes[i];
		out.nc[i].flags = 1;
	}
	out.cache[0] = (struct tetris_modem_smem_entry){ 22, 0, inputs->consys_size, 0x4a };
	out.cache[1] = (struct tetris_modem_smem_entry){
		32, 0, inputs->nv_cache_size ? inputs->nv_cache_size : 0x300000, 2,
	};
	out.cache[2] = (struct tetris_modem_smem_entry){ 1, 0, ccb_size, 2 };
	out.cache[3] = (struct tetris_modem_smem_entry){ 28, 0, inputs->udc_en ? 0x80000 : 0, 2 };
	out.cache[4] = (struct tetris_modem_smem_entry){ 24, 0, 0x60000, 2 };
	ret = smem_place(out.nc, nc_align, 18, 0xa000000,
			 &out.nc_capacity, &out.nc_rows);
	if (ret)
		return ret;
	ret = smem_place(out.cache, cache_align, 5, 0x8000000,
			 &out.cache_capacity, &out.cache_rows);
	if (ret)
		return ret;
	*plan = out;
	return 0;
}

static int tetris_metadata_memory(const unsigned char *chk, size_t rom_size,
			     unsigned long long base, size_t capacity,
			     struct tetris_modem_memory_map *map)
{
	struct tetris_modem_memory_map out = { 0 };
	struct tetris_modem_layout layout;
	const unsigned char *header;
	unsigned int i;
	int ret;

	if (!map || !base || !capacity || capacity > 0xffffffffU ||
	    base > ~0ULL - capacity)
		return -EINVAL;
	/* Caller checked the fixed CHK and all region bounds. No ROM read. */
	memset(&layout, 0, sizeof(layout));
	layout.memory_size = word(chk + 172);
	layout.dsp_offset = word(chk + 184);
	layout.dsp_capacity = word(chk + 188);
	layout.region_count = word(chk + 192);
	header = chk;
	out.count = 1;
	out.blocks[0].size = capacity;
	ret = annotate(&out, 0, layout.memory_size, 0, 1);
	if (ret)
		return ret;
	for (i = 0; i < layout.region_count; i++) {
		ret = annotate(&out, word(header + 196 + 8 * i),
			       word(header + 200 + 8 * i), 1U << i, 0);
		if (ret)
			return ret;
	}
	ret = annotate(&out, layout.dsp_offset, layout.dsp_capacity, 0, 2);
	if (ret)
		return ret;
	for (i = 0; i < 8; i++) {
		unsigned int offset = word(header + 0x11c + 8 * i);
		unsigned int size = word(header + 0x120 + 8 * i);

		if (!size)
			continue;
		if (!contained(offset, size, layout.memory_size) ||
		    offset < rom_size ||
		    (offset < layout.dsp_offset + layout.dsp_capacity &&
		     layout.dsp_offset < offset + size))
			return -ERANGE;
		ret = annotate(&out, offset, size, 0, 4);
		if (ret)
			return ret;
	}
	/* Stock processes DRDI windows even when mode 3 skips the image load. */
	for (i = 0; i < 3; i++) {
		unsigned int field = i == 2 ? 0x164 : 0x16c + 8 * i;
		unsigned int offset = word(header + field);
		unsigned int size = word(header + field + 4);

		if (!size)
			continue;
		if (!contained(offset, size, layout.memory_size))
			return -ERANGE;
		ret = annotate(&out, offset, size, 0, 0x20U << i);
		if (ret)
			return ret;
	}
	for (i = 0; i < out.count; i++)
		out.blocks[i].physical = base + out.blocks[i].offset;
	*map = out;
	return 0;
}

static void padding(struct tetris_modem_memory_map *map)
{
	unsigned int i, candidates = 0, biggest = 0, index = 0;

	/* Exact LK 0x27128..0x27260; one preset row (slot40) in this image. */
	for (i = 0; i < map->count; i++) {
		struct tetris_modem_block *b = &map->blocks[i];

		if (b->attributes & 8) {
			candidates++;
		} else if (b->attributes & 4) {
			if (i + 1 < map->count &&
			    (b->info & map->blocks[i + 1].info & 0xff)) {
				b->attributes |= 8;
				candidates++;
			} else {
				b->attributes |= 0x10;
			}
		}
	}
	if (candidates <= 1) {
		for (i = 0; i < map->count; i++)
			if (map->blocks[i].attributes & 8)
				map->blocks[i].attributes |= 0x10;
		return;
	}
	for (i = 0; i < map->count; i++) {
		const struct tetris_modem_block *b = &map->blocks[i];

		if ((b->attributes & 0x18) == 8 && b->size > biggest) {
			biggest = b->size;
			index = i;
		}
	}
	if (biggest)
		map->blocks[index].attributes |= 0x10;
}
#endif
