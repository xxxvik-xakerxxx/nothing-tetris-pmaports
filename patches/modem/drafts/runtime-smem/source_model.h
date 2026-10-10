/* SPDX-License-Identifier: GPL-2.0-only */
/* Generated pinned source subsets; NO physical reads or admission. */
/* U-Boot 60cd9ade5b999732304f3b755c7dbe3d34307c13; vendor ee2be53cb75670b548948636a0db1d1ff112bf12; metadata 190ea155e1a8343dbdb4f0992f06b92848c9cdac. */
#ifndef TETRIS_RUNTIME_SMEM_SOURCE_MODEL_H
#define TETRIS_RUNTIME_SMEM_SOURCE_MODEL_H

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

static const struct ccci_smem_region tetris_nc_template[] = {
	{ SMEM_USER_RAW_DFD, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_UDC_DATA, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_MD_WIFI_PROXY, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_SECURITY_SMEM, 0, 0, SMF_NCLR_FIRST, 0, 0, 0 },
	{ SMEM_USER_RAW_MDCCCI_DBG, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_MDSS_DBG, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_32K_LOW_POWER, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_RESERVED, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_RUNTIME_DATA, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_FORCE_ASSERT, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_LOW_POWER, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_DBM, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_CCISM_SCP, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_CCB_CTRL, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_NETD, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_USB, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_AUDIO, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_CCISM_MCU, 0, 0, SMF_NCLR_FIRST, 0, 0, 0 },
	{ SMEM_USER_CCISM_MCU_EXP, 0, 0, SMF_NCLR_FIRST, 0, 0, 0 },
	{ SMEM_USER_RESERVED, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_MD_DRDI, 0, 0, SMF_NCLR_FIRST, 0, 0, 0 },
	{ SMEM_USER_RAW_LWA, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_PHY_CAP, 0, 0, SMF_NCLR_FIRST, 0, 0, 0 },
	{ SMEM_USER_RAW_AMMS_POS, 0, 0, SMF_NCLR_FIRST, 0, 0, 0 },
	{ SMEM_USER_RAW_ALIGN_PADDING, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_MAX, 0, 0, 0, 0, 0, 0 },
};

static const struct ccci_smem_region tetris_cache_template[] = {
	{ SMEM_USER_RAW_MD_CONSYS, 0, 0, (SMF_NCLR_FIRST | SMF_NO_REMAP), 0, 0, 0 },
	{ SMEM_USER_MD_NVRAM_CACHE, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_CCB_DHL, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_CCB_MD_MONITOR, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_CCB_META, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_DHL, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_MDM, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_MD_POST_DUMP, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_UDC_DESCTAB, 0, 0, 0, 0, 0, 0 },
	{ SMEM_USER_RAW_USIP, 0, 0, SMF_NCLR_FIRST, 0, 0, 0 },
	{ SMEM_USER_MAX, 0, 0, 0, 0, 0, 0 },
};
#endif
