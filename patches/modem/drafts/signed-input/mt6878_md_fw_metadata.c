// SPDX-License-Identifier: GPL-2.0-or-later
/* Draft: signed input -> private authenticated expected-span owner, not installed-RAM
 * AUTH. Bundle/layout framing follows pinned U-Boot bffec9306e7c40a432d79deefb450230c2ee2360.
 */
#include <crypto/algapi.h>
#include <crypto/hash.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/refcount.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/vmalloc.h>
#include "mt6878_md_mtk_cert.h"
#include "mt6878_md_fw_metadata.h"

#define MD_SOURCE_MAX (256U * 1024 * 1024)
#define MD_PAYLOAD_MAX (64U * 1024 * 1024)

struct mt6878_md_fw_metadata {
	refcount_t refs;
	struct mt6878_md_fw_identity identity;
	struct tetris_modem_layout layout;
	const u8 *verified_source;
	const struct firmware *firmware;
};
struct md_fw_part {
	size_t header, payload, size;
	const char *name;
};

static u32 md_fw_word(const u8 *p)
{
	return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24;
}

static int md_fw_next(const u8 *data, size_t size, size_t *cursor, struct md_fw_part *part)
{
	const u8 *header;
	size_t end, i;

	if (*cursor > size || size - *cursor < 512)
		return -EMSGSIZE;
	header = data + *cursor;
	if (md_fw_word(header) != 0x58881688 || md_fw_word(header + 48) != 0x58891689 ||
	    md_fw_word(header + 52) != 512 || md_fw_word(header + 68) != 16)
		return -EPROTONOSUPPORT;
	for (i = 8; i < 40 && header[i]; i++)
		if (header[i] > 127)
			return -EBADMSG;
	if (i == 40)
		return -EBADMSG;
	part->header = *cursor;
	part->payload = *cursor + 512;
	part->size = md_fw_word(header + 4);
	part->name = (const char *)header + 8;
	if (!part->size || part->size > size - part->payload)
		return -EMSGSIZE;
	end = part->payload + part->size;
	*cursor = (end + 15) & ~(size_t)15; /* Source <=256MiB bounds addition. */
	return *cursor <= size ? 0 : -EMSGSIZE;
}

static int md_fw_hash(struct shash_desc *desc, const u8 *data, size_t size, u8 out[32])
{
	int ret = crypto_shash_digest(desc, data, size, out);

	return ret > 0 ? -EPROTO : ret;
}

static int md_fw_layout(const u8 *rom, struct mt6878_md_fw_metadata *owner)
{
	struct mt6878_md_fw_identity *out = &owner->identity;
	const struct tetris_modem_layout *layout = &owner->layout;
	const u8 *header;
	u32 i;
	int ret;

	/* Reuse the existing loader's bounded signed-layout implementation. */
	ret = tetris_modem_plan_layout(rom, out->member[0].stored_size,
		out->member[2].stored_size, out->reservation_capacity, &owner->layout);
	if (ret)
		return ret;
	header = rom + out->member[0].stored_size - 512;
	out->memory_size = layout->memory_size;
	out->logical_image_size = layout->logical_image_size;
	out->dsp_offset = layout->dsp_offset;
	out->dsp_capacity = layout->dsp_capacity;
	out->region_count = layout->region_count;
	for (i = 0; i < out->region_count; i++) {
		out->region_offset[i] = md_fw_word(header + 196 + 8 * i);
		out->region_size[i] = md_fw_word(header + 200 + 8 * i);
	}
	out->consys_size = md_fw_word(header + 0x180);
	out->udc_en = md_fw_word(header + 0x184);
	out->nv_cache_size = md_fw_word(header + 0x18c);
	out->drdi_version = md_fw_word(header + 0x190);
	return out->udc_en <= 1 ? 0 : -EPROTONOSUPPORT;
}

static int md_fw_prepare_snapshot(const u8 *snapshot, size_t size, u64 reservation_capacity,
				  struct mt6878_md_fw_metadata **out)
{
	static const char *const names[] = { "md1rom", "md1drdi", "md1dsp" };
	struct mt6878_md_fw_metadata *owner = NULL;
	struct crypto_shash *sha = NULL;
	struct shash_desc *desc = NULL;
	struct md_fw_part part, firmware = { 0 }, cert1 = { 0 };
	struct mt6878_md_signed_hashes signed_hashes;
	struct mt6878_md_fw_member_identity *member;
	u8 hash[32];
	size_t cursor = 0, rom_offset = 0;
	unsigned int count, found = 0, stage = 0, active = 0, index;
	int ret = -EINVAL;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!snapshot || !size || size > MD_SOURCE_MAX || !reservation_capacity)
		return -EINVAL;
	owner = kzalloc(sizeof(*owner), GFP_KERNEL);
	if (!owner) {
		ret = -ENOMEM;
		goto out;
	}
	owner->identity.source_size = size;
	owner->identity.reservation_capacity = reservation_capacity;
	sha = crypto_alloc_shash("sha256-lib", 0, 0);
	if (IS_ERR(sha)) {
		ret = PTR_ERR(sha);
		sha = NULL;
		goto out;
	}
	if (crypto_shash_digestsize(sha) != 32) {
		ret = -EPROTO;
		goto out;
	}
	desc = kzalloc(sizeof(*desc) + crypto_shash_descsize(sha), GFP_KERNEL);
	if (!desc) {
		ret = -ENOMEM;
		goto out;
	}
	desc->tfm = sha;
	for (count = 0; count < 128 && found != 7; count++) {
		ret = md_fw_next(snapshot, size, &cursor, &part);
		if (ret)
			goto out;
		if (!stage) {
			for (index = 0; index < MT6878_MD_FW_MEMBERS; index++)
				if (!strcmp(part.name, names[index]))
					break;
			if (index == MT6878_MD_FW_MEMBERS)
				continue;
			if (found & (1U << index)) {
				ret = -EEXIST;
				goto out;
			}
			if (part.size > MD_PAYLOAD_MAX || part.size % 16) {
				ret = -ERANGE;
				goto out;
			}
			active = index;
			firmware = part;
			stage = 1;
			continue;
		}
		if (part.size > 16384 || strcmp(part.name,
			stage == 1 ? (active == 0 ? "cert1md" : "cert1") : "cert2")) {
			ret = -EBADMSG;
			goto out;
		}
		if (stage == 1) {
			cert1 = part;
			stage = 2;
			continue;
		}
		ret = mt6878_md_mtk_verify_header(snapshot + cert1.payload, cert1.size,
			snapshot + part.payload, part.size, snapshot + firmware.header, 512, &signed_hashes);
		if (ret)
			goto out;
		ret = md_fw_hash(desc, snapshot + firmware.payload, firmware.size, hash);
		if (ret)
			goto out;
		if (crypto_memneq(hash, signed_hashes.payload_sha256, 32)) {
			ret = -EKEYREJECTED;
			goto out;
		}
		member = &owner->identity.member[active];
		member->stored_size = firmware.size;
		member->header_offset = firmware.header;
		member->payload_offset = firmware.payload;
		memcpy(member->header_sha256, signed_hashes.header_sha256, 32);
		memcpy(member->payload_sha256, signed_hashes.payload_sha256, 32);
		ret = md_fw_hash(desc, snapshot + cert1.payload, cert1.size, member->cert1_sha256);
		if (!ret)
			ret = md_fw_hash(desc, snapshot + part.payload, part.size, member->cert2_sha256);
		if (ret)
			goto out;
		if (active == 0)
			rom_offset = firmware.payload;
		found |= 1U << active;
		stage = 0;
	}
	if (found != 7) {
		ret = -E2BIG;
		goto out;
	}
	owner->identity.consumed_size = cursor;
	ret = md_fw_layout(snapshot + rom_offset, owner);
	if (ret)
		goto out;
	owner->verified_source = snapshot;
	refcount_set(&owner->refs, 1);
	*out = owner;
	owner = NULL;
out:
	kfree_sensitive(desc);
	if (sha)
		crypto_free_shash(sha);
	kfree_sensitive(owner);
	memzero_explicit(hash, sizeof(hash));
	memzero_explicit(&signed_hashes, sizeof(signed_hashes));
	return ret;
}

int mt6878_md_fw_prepare(const u8 *source, size_t size, u64 reservation_capacity,
			struct mt6878_md_fw_metadata **out)
{
	u8 *snapshot;
	int ret;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!source || !size || size > MD_SOURCE_MAX || !reservation_capacity)
		return -EINVAL;
	snapshot = kvmalloc(size, GFP_KERNEL);
	if (!snapshot)
		return -ENOMEM;
	memcpy(snapshot, source, size);
	ret = md_fw_prepare_snapshot(snapshot, size, reservation_capacity, out);
	if (ret)
		kvfree(snapshot);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_md_fw_prepare);

int mt6878_md_fw_request(struct device *dev, const char *name, u64 reservation_capacity,
			struct mt6878_md_fw_metadata **out)
{
	const struct firmware *firmware;
	struct mt6878_md_fw_metadata *owner;
	int ret;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!dev || !name || !*name || !reservation_capacity)
		return -EINVAL;
	ret = request_firmware(&firmware, name, dev);
	if (ret)
		return ret;
	/* The firmware API owns this immutable blob; retain its lifetime instead
	 * of duplicating the whole partition into a second snapshot allocation.
	 */
	ret = md_fw_prepare_snapshot(firmware->data, firmware->size, reservation_capacity, &owner);
	if (ret) {
		release_firmware(firmware);
		return ret;
	}
	owner->firmware = firmware;
	*out = owner;
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_md_fw_request);

struct mt6878_md_fw_metadata *mt6878_md_fw_get(struct mt6878_md_fw_metadata *owner)
{
	return owner && refcount_inc_not_zero(&owner->refs) ? owner : NULL;
}
EXPORT_SYMBOL_GPL(mt6878_md_fw_get);

void mt6878_md_fw_put(struct mt6878_md_fw_metadata *owner)
{
	if (owner && refcount_dec_and_test(&owner->refs)) {
		if (owner->firmware)
			release_firmware(owner->firmware);
		else
			kvfree(owner->verified_source);
		kfree_sensitive(owner);
	}
}
EXPORT_SYMBOL_GPL(mt6878_md_fw_put);

int mt6878_md_fw_snapshot(const struct mt6878_md_fw_metadata *owner,
			 struct mt6878_md_fw_identity *out)
{
	if (!owner || !out)
		return -EINVAL;
	*out = owner->identity;
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_md_fw_snapshot);

static int md_fw_separate(const void *a, size_t an, const void *b, size_t bn)
{
	unsigned long first = (unsigned long)a, second = (unsigned long)b;

	return a && b && an && bn && an <= ~0UL - first && bn <= ~0UL - second &&
		(first + an <= second || second + bn <= first);
}

int mt6878_md_fw_copy_payload(const struct mt6878_md_fw_metadata *owner,
			     unsigned int member_id, size_t offset,
			     void *destination, size_t size)
{
	const struct mt6878_md_fw_member_identity *member;

	if (!owner || member_id >= MT6878_MD_FW_MEMBERS || !destination || !size)
		return -EINVAL;
	member = &owner->identity.member[member_id];
	if (offset > member->stored_size || size > member->stored_size - offset)
		return -ERANGE;
	if (!md_fw_separate(destination, size, owner, sizeof(*owner)) ||
	    !md_fw_separate(destination, size, owner->verified_source, owner->identity.source_size))
		return -EINVAL;
	/* Only the private, already authenticated snapshot is ever consumed.
	 * Destination must be ordinary caller-owned memory, never an MMIO mapping.
	 */
	memcpy(destination, owner->verified_source + member->payload_offset + offset, size);
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_md_fw_copy_payload);

int mt6878_md_fw_place_b41(const struct mt6878_md_fw_metadata *owner,
			 void *destination, size_t capacity, unsigned int ccb_gear,
			 struct tetris_modem_boot_plan *plan)
{
	struct tetris_modem_boot_plan loaded = { 0 };
	const u8 *rom, *dsp;
	int ret;

	if (!owner || !md_fw_separate(destination, capacity, plan, sizeof(*plan)) ||
	    !md_fw_separate(destination, capacity, owner, sizeof(*owner)) ||
	    !md_fw_separate(plan, sizeof(*plan), owner, sizeof(*owner)) ||
	    !md_fw_separate(destination, capacity, owner->verified_source, owner->identity.source_size) ||
	    !md_fw_separate(plan, sizeof(*plan), owner->verified_source, owner->identity.source_size))
		return -EINVAL;
	if (capacity < owner->layout.memory_size)
		return -ERANGE;
	rom = owner->verified_source + owner->identity.member[0].payload_offset;
	dsp = owner->verified_source + owner->identity.member[2].payload_offset;
	loaded.layout = owner->layout;
	/* Same inputs as the existing ROM planner, cached after authentication.
	 * No second header/bundle scan, payload rehash or duplicate load buffer.
	 */
	loaded.smem_inputs.drdi_version = owner->identity.drdi_version;
	loaded.smem_inputs.udc_en = owner->identity.udc_en;
	loaded.smem_inputs.consys_size = owner->identity.consys_size;
	loaded.smem_inputs.nv_cache_size = owner->identity.nv_cache_size;
	loaded.smem_inputs.ccb_gear = ccb_gear;
	ret = tetris_modem_plan_smem_b41(&loaded.smem_inputs, &loaded.smem);
	if (ret)
		return ret;
	/* No fallible operation after the first output write, as in the loader. */
	memcpy(destination, rom, loaded.layout.rom_size);
	memcpy((u8 *)destination + loaded.layout.dsp_offset, dsp, loaded.layout.dsp_size);
	*plan = loaded;
	return 0;
}
EXPORT_SYMBOL_GPL(mt6878_md_fw_place_b41);
MODULE_LICENSE("GPL");
