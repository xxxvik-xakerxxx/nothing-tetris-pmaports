// SPDX-License-Identifier: GPL-2.0-only
/* Diagnostic-only consumer of authenticated, reserved ordinary DRAM. */
#include <crypto/hash.h>
#include <linux/capability.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_reserved_mem.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <asm/page.h>

/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_GPUEB_FLAT_METADATA_H
#define TETRIS_GPUEB_FLAT_METADATA_H

#include <linux/errno.h>
#include <linux/of.h>
#include <linux/of_reserved_mem.h>
#include <linux/string.h>

#define TETRIS_FLAT_VERSION 1U
#define TETRIS_FLAT_BYTES 156064U
#define TETRIS_FLAT_ARENA_BYTES 0x100000U
#define TETRIS_FLAT_ARENA_ALIGN 0x10000U
#define TETRIS_FLAT_GPR_OFFSET 0x3fd1cU

struct tetris_gpueb_flat_metadata {
	u32 handoff_version;
	u32 payload_offset;
	u32 authenticated_bytes;
	u32 sram_offset;
	u32 profile_id;
	u8 plaintext_sha256[32];
	u8 primary_header_sha256[32];
	u8 ciphertext_sha256[32];
	u8 leaf_certificate_sha256[32];
	u8 container_sha256[32];
};

/* Same profile IDs as the actual U-Boot v1 producer: phone-a=1, B4.1=2.
 * These are signed firmware identities, not handset/calibration identities.
 */
static inline int tetris_gpueb_flat_profile_check(
		const struct tetris_gpueb_flat_metadata *metadata)
{
	static const u8 profiles[2][32] = {
		{ 0x96, 0x28, 0xa4, 0x46, 0xc2, 0x45, 0x36, 0x64,
		  0xee, 0xbb, 0x7c, 0xe0, 0xf5, 0xb6, 0xd9, 0xdb,
		  0x51, 0xd6, 0x77, 0xd6, 0xc1, 0xdb, 0x3c, 0x4a,
		  0xc1, 0x44, 0x9f, 0x4c, 0xfa, 0xad, 0x86, 0xd7 },
		{ 0x4c, 0xd3, 0xac, 0x60, 0x60, 0x5b, 0x30, 0xf9,
		  0x29, 0x88, 0xa7, 0x60, 0x6e, 0x95, 0xb7, 0xe4,
		  0xf8, 0x2d, 0x70, 0x51, 0x3b, 0xbd, 0x12, 0x92,
		  0x3a, 0x0e, 0x56, 0x2e, 0x9f, 0xc3, 0x17, 0x02 },
	};

	if (!metadata || metadata->profile_id < 1 || metadata->profile_id > 2)
		return -ENOEXEC;
	if (memcmp(metadata->plaintext_sha256,
		   profiles[metadata->profile_id - 1], 32))
		return -ENOEXEC;
	return 0;
}

static inline int tetris_gpueb_flat_metadata_validate(
		const struct tetris_gpueb_flat_metadata *metadata,
		const struct reserved_mem *memory)
{
	if (!metadata || !memory || metadata->handoff_version != TETRIS_FLAT_VERSION ||
	    memory->size != TETRIS_FLAT_ARENA_BYTES ||
	    memory->base < 0x40000000ULL ||
	    memory->base > 0x80000000ULL - TETRIS_FLAT_ARENA_BYTES ||
	    (memory->base & (TETRIS_FLAT_ARENA_ALIGN - 1)) ||
	    metadata->payload_offset || metadata->sram_offset ||
	    metadata->authenticated_bytes != TETRIS_FLAT_BYTES ||
	    metadata->payload_offset > memory->size ||
	    metadata->authenticated_bytes > memory->size - metadata->payload_offset ||
	    metadata->sram_offset > TETRIS_FLAT_GPR_OFFSET ||
	    metadata->authenticated_bytes > TETRIS_FLAT_GPR_OFFSET - metadata->sram_offset)
		return -EINVAL;
	/* Provenance must be present and copied, but is not a second signature
	 * verification. Container identity includes unauthenticated framing/xfile.
	 * Trust remains the reviewed bootloader producer and its signed postdigest.
	 */
	if (!memchr_inv(metadata->primary_header_sha256, 0, 32) ||
	    !memchr_inv(metadata->ciphertext_sha256, 0, 32) ||
	    !memchr_inv(metadata->leaf_certificate_sha256, 0, 32) ||
	    !memchr_inv(metadata->container_sha256, 0, 32))
		return -EINVAL;
	return tetris_gpueb_flat_profile_check(metadata);
}

static inline int tetris_gpueb_flat_read_u32(const struct device_node *node,
		const char *name, u32 *value)
{
	if (of_property_count_u32_elems(node, name) != 1)
		return -EINVAL;
	return of_property_read_u32(node, name, value);
}

static inline int tetris_gpueb_flat_read_digest(const struct device_node *node,
		const char *name, u8 value[32])
{
	const void *property;
	int length;

	property = of_get_property(node, name, &length);
	if (!property || length != 32)
		return -EINVAL;
	memcpy(value, property, 32);
	return 0;
}

/* Metadata only; the existing consumer must validate plain NOMAP ordinary RAM,
 * claim the whole arena, recheck resources/PFNs and hash its private snapshot.
 * No borrowed DT property pointer survives. Failure leaves *result unchanged.
 */
static inline int tetris_gpueb_flat_metadata_read(const struct device_node *node,
		const struct reserved_mem *memory,
		struct tetris_gpueb_flat_metadata *result)
{
	struct tetris_gpueb_flat_metadata metadata = { 0 };
	int ret;

	if (!node || !result || !of_device_is_available(node) ||
	    of_property_count_strings(node, "compatible") != 1 ||
	    !of_device_is_compatible(node, "nothing,tetris-gpueb-flat-analysis-v1"))
		return -EINVAL;
#define READ_U32(property, field) do { \
	ret = tetris_gpueb_flat_read_u32(node, property, &metadata.field); \
	if (ret) return ret; \
} while (0)
#define READ_DIGEST(property, field) do { \
	ret = tetris_gpueb_flat_read_digest(node, property, metadata.field); \
	if (ret) return ret; \
} while (0)
	READ_U32("nothing,handoff-version", handoff_version);
	READ_U32("nothing,payload-offset", payload_offset);
	READ_U32("nothing,authenticated-bytes", authenticated_bytes);
	READ_U32("nothing,sram-offset", sram_offset);
	READ_U32("nothing,profile-id", profile_id);
	READ_DIGEST("nothing,plaintext-sha256", plaintext_sha256);
	READ_DIGEST("nothing,primary-header-sha256", primary_header_sha256);
	READ_DIGEST("nothing,ciphertext-sha256", ciphertext_sha256);
	READ_DIGEST("nothing,leaf-certificate-sha256", leaf_certificate_sha256);
	READ_DIGEST("nothing,container-sha256", container_sha256);
#undef READ_U32
#undef READ_DIGEST
	ret = tetris_gpueb_flat_metadata_validate(&metadata, memory);
	if (ret)
		return ret;
	*result = metadata;
	return 0;
}

/* digest must be the actual SHA256 of the owned private snapshot. Admission
 * covers signed bytes only; it grants no upload/reset/IRQ/start authority.
 */
static inline int tetris_gpueb_flat_snapshot_check(
		const struct tetris_gpueb_flat_metadata *metadata,
		const u8 digest[32], size_t bytes)
{
	int ret;

	if (!metadata || !digest || bytes != TETRIS_FLAT_BYTES ||
	    bytes != metadata->authenticated_bytes)
		return -EINVAL;
	ret = tetris_gpueb_flat_profile_check(metadata);
	if (ret)
		return ret;
	return memcmp(digest, metadata->plaintext_sha256, 32) ? -EBADMSG : 0;
}

#endif

struct flat_analysis {
	struct miscdevice misc;
	struct resource *reservation;
	u8 *snapshot;
	u32 size;
	struct tetris_gpueb_flat_metadata metadata;
};

struct flat_ram_check {
	resource_size_t cursor, end;
};

static int flat_reserved_resource(struct resource *resource, void *data)
{
	struct flat_ram_check *check = data;

	/* Linux d84b264: ARM64 setup.c creates top-level IORESOURCE_MEM for
	 * NOMAP DRAM. resource.c clips spans, preserving flags/desc/parent but
	 * NOT name or child. Require gap-free coverage, then claim below.
	 */
	if (resource->flags != IORESOURCE_MEM ||
	    resource->desc != IORES_DESC_NONE ||
	    resource->parent != &iomem_resource ||
	    resource->start != check->cursor || resource->end < resource->start ||
	    resource->end >= check->end)
		return -ENXIO;
	check->cursor = resource->end + 1;
	return 0;
}

static int flat_plain_reservation(struct device_node *node,
				  struct reserved_mem *memory)
{
	struct device_node *parent;
	struct resource resource;
	int length, ret = -EINVAL;

	/* Failed compatible init can clear NOMAP without removing the catalog.
	 * Match the producer's static plain node, with no init/release owner.
	 */
	if (!memory || memory->ops || !of_device_is_available(node) ||
	    !of_find_property(node, "no-map", &length) || length ||
	    of_find_property(node, "compatible", NULL) ||
	    of_find_property(node, "reusable", NULL) ||
	    of_n_addr_cells(node) != 2 || of_n_size_cells(node) != 2 ||
	    !of_find_property(node, "reg", &length) || length != 16)
		return -EINVAL;
	parent = of_find_node_by_path("/reserved-memory");
	if (!parent)
		return -EINVAL;
	if (node->parent == parent && of_device_is_available(parent) &&
	    of_n_addr_cells(parent) == 2 && of_n_size_cells(parent) == 2 &&
	    of_find_property(parent, "ranges", &length) && !length &&
	    !of_address_to_resource(node, 0, &resource) &&
	    resource.flags == IORESOURCE_MEM && resource.start == memory->base &&
	    resource_size(&resource) == memory->size)
		ret = 0;
	of_node_put(parent);
	return ret;
}

static int flat_normal_reserved_ram(struct reserved_mem *memory)
{
	struct device_node *node;
	struct resource resource;
	struct flat_ram_check check = {
		.cursor = memory->base,
		.end = memory->base + memory->size,
	};
	phys_addr_t address;
	bool in_ram = false;
	int i, ret;

	if ((memory->base | memory->size) & (PAGE_SIZE - 1))
		return -EINVAL;
	for_each_node_by_type(node, "memory") {
		for (i = 0; !of_address_to_resource(node, i, &resource); i++)
			if (of_device_is_available(node) &&
			    resource.flags == IORESOURCE_MEM &&
			    resource.start <= memory->base && resource.end >= check.end - 1)
				in_ram = true;
	}
	if (!in_ram || region_intersects(memory->base, memory->size,
		IORESOURCE_SYSTEM_RAM, IORES_DESC_NONE) != REGION_DISJOINT)
		return -ENXIO;
	ret = walk_iomem_res_desc(IORES_DESC_NONE, IORESOURCE_MEM,
		memory->base, check.end - 1, &check, flat_reserved_resource);
	if (ret || check.cursor != check.end)
		return ret ? ret : -ENXIO;
	/* ARM64 exports this API and keeps memblock after init. Resource coverage
	 * rejects holes; every PFN check also catches later NOMAP clearing.
	 * Neither check grants secure-world access or locks arbitrary mutations.
	 */
	for (address = memory->base; address < check.end; address += PAGE_SIZE) {
		unsigned long pfn = (unsigned long)(address >> PAGE_SHIFT);

		if ((phys_addr_t)pfn != address >> PAGE_SHIFT || pfn_is_map_memory(pfn))
			return -ENXIO;
	}
	return 0;
}

static int flat_claim_reserved_ram(struct flat_analysis *analysis,
				   struct reserved_mem *memory)
{
	struct resource *claim, *parent;
	int ret;

	ret = flat_normal_reserved_ram(memory);
	if (ret)
		return ret;
	claim = request_mem_region_exclusive(memory->base, memory->size,
					     "gpueb-flat-analysis");
	if (!claim)
		return -EBUSY;
	analysis->reservation = claim;
	parent = claim->parent;
	/* __request_region descends through nonbusy containers. Reject adoption
	 * under a pre-existing child; overlapping children instead fail the claim.
	 * A single exact claim must fit one top-level NOMAP resource. Even valid
	 * adjacent spans are rejected if the whole reservation cannot be claimed.
	 */
	if (claim->start != memory->base ||
	    resource_size(claim) != memory->size || claim->child ||
	    claim->flags != (IORESOURCE_MEM | IORESOURCE_BUSY | IORESOURCE_EXCLUSIVE) ||
	    claim->desc != IORES_DESC_NONE || !parent ||
	    parent->parent != &iomem_resource || parent->flags != IORESOURCE_MEM ||
	    parent->desc != IORES_DESC_NONE || !parent->name ||
	    strcmp(parent->name, "reserved") ||
	    parent->start > claim->start || parent->end < claim->end)
		return -ENXIO;
	/* Recheck retained PFNs/resources with ownership held before mapping. */
	return flat_normal_reserved_ram(memory);
}

static ssize_t flat_read(struct file *file, char __user *out, size_t count,
			loff_t *position)
{
	struct flat_analysis *analysis = container_of(file->private_data,
					struct flat_analysis, misc);

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	return simple_read_from_buffer(out, count, position,
				       analysis->snapshot, analysis->size);
}

static const struct file_operations flat_fops = {
	.owner = THIS_MODULE,
	.open = nonseekable_open,
	.read = flat_read,
};

static int flat_probe(struct platform_device *pdev)
{
	struct device_node *node;
	struct reserved_mem *memory;
	struct flat_analysis *analysis;
	struct crypto_shash *hash;
	struct shash_desc *desc;
	struct tetris_gpueb_flat_metadata metadata;
	u8 digest[32];
	void *mapping;
	u32 size;
	int ret;

	if (of_property_count_u32_elems(pdev->dev.of_node, "memory-region") != 1)
		return -EINVAL;
	node = of_parse_phandle(pdev->dev.of_node, "memory-region", 0);
	if (!node)
		return -EINVAL;
	memory = of_reserved_mem_lookup(node);
	ret = flat_plain_reservation(node, memory);
	of_node_put(node);
	if (ret || !memory)
		return -EINVAL;
	ret = tetris_gpueb_flat_metadata_read(pdev->dev.of_node, memory, &metadata);
	if (ret)
		return ret;
	size = metadata.authenticated_bytes;
	analysis = kzalloc(sizeof(*analysis), GFP_KERNEL);
	if (!analysis)
		return -ENOMEM;
	ret = flat_claim_reserved_ram(analysis, memory);
	if (ret)
		goto release;
	analysis->snapshot = kvmalloc(size, GFP_KERNEL);
	if (!analysis->snapshot) {
		ret = -ENOMEM;
		goto release;
	}
	mapping = memremap(memory->base, size, MEMREMAP_WB);
	if (!mapping) {
		ret = -ENOMEM;
		goto erase;
	}
	memcpy(analysis->snapshot, (u8 *)mapping + metadata.payload_offset, size);
	memunmap(mapping);
	hash = crypto_alloc_shash("sha256", 0, 0);
	if (IS_ERR(hash)) {
		ret = PTR_ERR(hash);
		goto erase;
	}
	desc = kmalloc(sizeof(*desc) + crypto_shash_descsize(hash), GFP_KERNEL);
	if (!desc) {
		crypto_free_shash(hash);
		ret = -ENOMEM;
		goto erase;
	}
	desc->tfm = hash;
	ret = crypto_shash_digest(desc, analysis->snapshot, size, digest);
	kfree_sensitive(desc);
	crypto_free_shash(hash);
	if (!ret)
		ret = tetris_gpueb_flat_snapshot_check(&metadata, digest, size);
	memzero_explicit(digest, sizeof(digest));
	if (ret)
		goto erase;
	analysis->metadata = metadata;
	analysis->size = size;
	analysis->misc.minor = MISC_DYNAMIC_MINOR;
	analysis->misc.name = "gpueb-flat-analysis";
	analysis->misc.mode = 0600;
	analysis->misc.fops = &flat_fops;
	analysis->misc.parent = &pdev->dev;
	ret = misc_register(&analysis->misc);
	if (ret)
		goto erase;
	platform_set_drvdata(pdev, analysis);
	return 0;
erase:
	kvfree_sensitive(analysis->snapshot, size);
release:
	if (analysis->reservation)
		release_mem_region(analysis->reservation->start,
				   resource_size(analysis->reservation));
	kfree(analysis);
	return ret;
}

/* No remove/unbind: retain the full exclusive RAM claim and verified snapshot.
 * Pin on successful probe; diagnostic module lifetime is the entire boot.
 */
static int flat_bound_probe(struct platform_device *pdev)
{
	int ret;

	if (!try_module_get(THIS_MODULE))
		return -ENODEV;
	ret = flat_probe(pdev);
	if (ret)
		module_put(THIS_MODULE);
	return ret;
}

static const struct of_device_id flat_match[] = {
	{ .compatible = "nothing,tetris-gpueb-flat-analysis-v1" },
	{ }
};
MODULE_DEVICE_TABLE(of, flat_match);
static struct platform_driver flat_driver = {
	.probe = flat_bound_probe,
	.driver = {
		.name = "gpueb-flat-analysis",
		.of_match_table = flat_match,
		.suppress_bind_attrs = true,
	},
};
module_platform_driver(flat_driver);
MODULE_LICENSE("GPL");
