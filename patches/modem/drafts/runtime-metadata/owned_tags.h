/* SPDX-License-Identifier: GPL-2.0-only */
/* Included in ccci_util_boot_args.c. AP tag metadata only, no modem mappings. */
#include "semantic.h"
static unsigned char *tetris_owned_tags;
static int tetris_owned_tags_error;
static bool tetris_owned_tags_attempted;

int mtk_ccci_import_owned_tags(const void __iomem *mapped, unsigned int size,
		unsigned int version, unsigned int count, const struct tetris_metadata_banks *banks)
{
	static const struct {
		const char *name;
		unsigned int bytes, stride, maximum;
	} profile[] = {
		{ "hdr_count", 4, 0, 0 }, { "hdr_tbl_inf", 24, 0, 0 },
		{ "smem_layout", 40, 0, 0 }, { "ccb_info", 16, 0, 0 },
		{ "udc_layout", 8, 0, 0 }, { "md1_sib_info", 16, 0, 0 },
		{ "md1_phy_cap", 4, 0, 0 }, { "md1_chk", 512, 0, 0 },
		{ "md1img", 4, 0, 0 }, { "md_bank0_base", 8, 0, 0 },
		{ "md_mem_layout", 0, 24, 32 }, { "nc_smem_layout_num", 4, 0, 0 },
		{ "nc_smem_layout", 0, 40, 36 }, { "c_smem_layout_num", 4, 0, 0 },
		{ "c_smem_layout", 0, 40, 10 }, { "md1_bank4_cache_info", 24, 0, 0 },
		{ "md1_bank4_cache_layout", 120, 0, 0 },
		{ "nc_smem_info_ext_num", 4, 0, 0 },
		{ "nc_smem_info_ext", 288, 0, 0 },
		{ "md1_smem_cahce_offset", 4, 0, 0 }, { "free_in_kernel", 4, 0, 0 },
	};
	unsigned char *snapshot = NULL;
	unsigned int offsets[ARRAY_SIZE(profile)], lengths[ARRAY_SIZE(profile)];
	unsigned int i, cursor = ARRAY_SIZE(profile) * 76;
	int ret = -EBADMSG;

	if (tetris_owned_tags_attempted)
		return tetris_owned_tags_error ? tetris_owned_tags_error : -EALREADY;
	tetris_owned_tags_attempted = true;
	if (!s_init_done || !mapped || version != 2 || count != ARRAY_SIZE(profile) ||
	    size < cursor || size > 65536 ||
	    s_args_num > ARGS_KEY_VAL_MAX_KEY_NUM - ARRAY_SIZE(profile)) {
		ret = -EINVAL;
		goto fault;
	}
	ret = tetris_metadata_windows(banks);
	if (ret)
		goto fault;
	ret = -EBADMSG;
	snapshot = kmalloc(size, GFP_KERNEL);
	if (!snapshot) {
		ret = -ENOMEM;
		goto fault;
	}
	/* One copy from an already-admitted AP-owned mapping, never protected ROM/SMEM.
	 * Caller must keep that mapping coherent/stable for the duration of this copy.
	 */
	memcpy_fromio(snapshot, mapped, size);
	for (i = 0; i < ARRAY_SIZE(profile); i++) {
		const unsigned char *header = snapshot + i * 76;
		unsigned int bytes = get_unaligned_le32(header + 68);
		unsigned int name_size = strlen(profile[i].name) + 1;

		if (memcmp(header, profile[i].name, name_size) ||
		    memchr_inv(header + name_size, 0, 64 - name_size) ||
		    get_unaligned_le32(header + 64) != cursor ||
		    get_unaligned_le32(header + 72) !=
			(i + 1 < count ? (i + 1) * 76 : 0) ||
		    bytes > size - cursor ||
		    (profile[i].bytes && bytes != profile[i].bytes) ||
		    (profile[i].stride && (!bytes || bytes % profile[i].stride ||
			bytes / profile[i].stride > profile[i].maximum)))
			goto fault;
		if (is_key_exist(profile[i].name, name_size) >= 0) {
			ret = -EEXIST;
			goto fault;
		}
		offsets[i] = cursor;
		lengths[i] = bytes;
		cursor += bytes;
	}
	if (cursor != size || get_unaligned_le32(snapshot + offsets[0]) != 1 ||
	    get_unaligned_le32(snapshot + offsets[11]) != lengths[12] / 40 ||
	    get_unaligned_le32(snapshot + offsets[13]) != lengths[14] / 40 ||
	    get_unaligned_le32(snapshot + offsets[17]) != 18 ||
	    get_unaligned_le32(snapshot + offsets[19]) != 0x8000000 ||
	    get_unaligned_le32(snapshot + offsets[20]) != 0)
		goto fault;
	/* This is the producer's bounded B4.1 normal-Linux profile, not a
	 * universal SKU claim and not reauthentication of the retained CHK copy.
	 */
	{
		const unsigned char *chk = snapshot + offsets[7];
		const unsigned char *hdr = snapshot + offsets[1];

		if (memcmp(chk, "CHECK_HEADER", 12) || get_unaligned_le32(chk + 12) != 6 ||
		    get_unaligned_le32(chk + 16) != 2 || get_unaligned_le32(chk + 20) != 14 ||
		    chk[168] != 1 || get_unaligned_le32(chk + 508) != 512 ||
		    get_unaligned_le32(hdr + 8) != get_unaligned_le32(chk + 172) ||
		    hdr[12] || hdr[13] || hdr[14] != 14 ||
		    get_unaligned_le64(hdr) != get_unaligned_le64(snapshot + offsets[9]) ||
		    memchr_inv(snapshot + offsets[4], 0, lengths[4]) ||
		    memchr_inv(snapshot + offsets[5], 0, lengths[5]) ||
		    get_unaligned_le32(snapshot + offsets[6]) ||
		    get_unaligned_le32(chk + 0x184))
			goto fault;
	}
	ret = tetris_metadata_semantics(snapshot, offsets, lengths, banks);
	if (ret)
		goto fault;
	/* All allocation/validation happens before publication. No fallible append
	 * calls, shared-buffer bump allocator, or pointers into soon-unmapped LK I/O.
	 * Existing util module init is the sole serialized importer, before consumers.
	 */
	for (i = 0; i < ARRAY_SIZE(profile); i++) {
		struct args_key_val *arg = &s_args_tbl[s_args_num + i];

		arg->key_size = strlen(profile[i].name) + 1;
		memcpy(arg->key, profile[i].name, arg->key_size);
		arg->val_size = lengths[i];
		arg->source = FROM_KERNEL;
		arg->pdata = snapshot + offsets[i];
	}
	tetris_owned_tags = snapshot;
	s_args_num += ARRAY_SIZE(profile);
	return 0;
fault:
	kfree(snapshot);
	tetris_owned_tags_error = ret;
	return ret;
}
