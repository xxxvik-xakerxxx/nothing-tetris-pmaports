/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef MT6878_MD_FW_METADATA_H
#define MT6878_MD_FW_METADATA_H
#include <linux/types.h>
#include "tetris_modem_bundle.h"
struct device;
struct mt6878_md_fw_metadata;
#define MT6878_MD_FW_MEMBERS 3
struct mt6878_md_fw_member_identity {
	u32 stored_size;
	u64 header_offset, payload_offset;
	u8 header_sha256[32], payload_sha256[32];
	u8 cert1_sha256[32], cert2_sha256[32];
};
struct mt6878_md_fw_identity {
	/* Order: ROM, DRDI, DSP. Expected signed spans, not installed RAM hashes. */
	struct mt6878_md_fw_member_identity member[MT6878_MD_FW_MEMBERS];
	u64 source_size, consumed_size, reservation_capacity;
	u32 memory_size, logical_image_size, dsp_offset, dsp_capacity, region_count;
	u32 region_offset[8], region_size[8];
	u32 consys_size, udc_en, nv_cache_size, drdi_version;
};
/* Draft, not wired to startup. Snapshot and crypto precede publication, outside locks.
 * Caller supplies accessible input, immutable during initial copy; never a
 * protected physical RAM mapping. Capacity is a bound, not reservation proof.
 * Only real fixed-pin manufacturer verification creates the opaque owner.
 */
int mt6878_md_fw_prepare(const u8 *source, size_t size, u64 reservation_capacity,
			struct mt6878_md_fw_metadata **out);
int mt6878_md_fw_request(struct device *dev, const char *name, u64 reservation_capacity,
			struct mt6878_md_fw_metadata **out);
/* get requires an already-held/live reference, not an unprotected raw pointer.
 * Snapshot copies metadata; no input/certificate/payload pointer escapes.
 * prepare retains its private copy; request retains the const Linux firmware
 * blob without duplication. Both live until the last reference is released.
 * Kernel clients must obey the firmware API's immutable-data contract.
 */
struct mt6878_md_fw_metadata *mt6878_md_fw_get(struct mt6878_md_fw_metadata *owner);
void mt6878_md_fw_put(struct mt6878_md_fw_metadata *owner);
int mt6878_md_fw_snapshot(const struct mt6878_md_fw_metadata *owner,
			 struct mt6878_md_fw_identity *out);
/* Copy an authenticated ROM/DRDI/DSP payload slice to ordinary owned memory.
 * Hold a live reference throughout. Never pass protected RAM or an MMIO
 * mapping: this function proves source integrity, not access/admission rights.
 * Invalid requests leave destination unchanged. No implicit layout padding.
 */
int mt6878_md_fw_copy_payload(const struct mt6878_md_fw_metadata *owner,
			     unsigned int member_id, size_t offset,
			     void *destination, size_t size);
/* Existing B4.1 loader layout/SMEM contract from the same verified snapshot.
 * Copies ROM/DSP only, preserving gaps and tail; DRDI 3 is not placed.
 * Destination MUST be exclusively owned ordinary staging memory, never a
 * protected MD/MMIO mapping. This is not a physical loader permission API.
 * Effective ccb_gear comes from resolved boot policy, not authenticated ROM.
 * Hold a live reference throughout. Validate/plan before any output write.
 * No allocation, source reread, authentication pass, flush, SMC or READY tag.
 */
int mt6878_md_fw_place_b41(const struct mt6878_md_fw_metadata *owner,
			 void *destination, size_t capacity, unsigned int ccb_gear,
			 struct tetris_modem_boot_plan *plan);
#endif
