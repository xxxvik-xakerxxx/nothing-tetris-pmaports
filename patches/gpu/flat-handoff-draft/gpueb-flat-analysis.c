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

struct flat_analysis {
	struct miscdevice misc;
	u8 *snapshot;
	u32 size;
};

struct flat_ram_check {
	resource_size_t start, end;
	bool found;
};

static int flat_reserved_resource(struct resource *resource, void *data)
{
	struct flat_ram_check *check = data;

	/* ARM64 setup.c registers memblock NOMAP DRAM as "reserved", not
	 * IORESOURCE_SYSTEM_RAM. Require that exact covering resource as well
	 * as the firmware memory-node bounds below; arbitrary MMIO is rejected.
	 */
	if (resource->start <= check->start && resource->end >= check->end &&
	    resource->name && !strcmp(resource->name, "reserved") &&
	    !(resource->flags & IORESOURCE_SYSRAM))
		check->found = true;
	return 0;
}

static int flat_normal_reserved_ram(struct reserved_mem *memory)
{
	struct device_node *node;
	struct resource resource;
	struct flat_ram_check check = {
		.start = memory->base,
		.end = memory->base + memory->size - 1,
	};
	bool in_ram = false;
	int i, ret;

	for_each_node_by_type(node, "memory") {
		for (i = 0; !of_address_to_resource(node, i, &resource); i++)
			if (resource.start <= check.start && resource.end >= check.end)
				in_ram = true;
	}
	if (!in_ram || region_intersects(memory->base, memory->size,
		IORESOURCE_SYSTEM_RAM, IORES_DESC_NONE) != REGION_DISJOINT)
		return -ENXIO;
	ret = walk_iomem_res_desc(IORES_DESC_NONE, IORESOURCE_MEM,
		check.start, check.end, &check, flat_reserved_resource);
	return ret ? ret : check.found ? 0 : -ENXIO;
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
	.read = flat_read,
	.llseek = no_llseek,
};

static int flat_probe(struct platform_device *pdev)
{
	struct device_node *node;
	struct reserved_mem *memory;
	struct flat_analysis *analysis;
	struct crypto_shash *hash;
	struct shash_desc *desc;
	const u8 *expected;
	u8 digest[32];
	void *mapping;
	u32 size;
	int length, ret;

	if (of_property_count_u32_elems(pdev->dev.of_node, "memory-region") != 1)
		return -EINVAL;
	node = of_parse_phandle(pdev->dev.of_node, "memory-region", 0);
	if (!node)
		return -EINVAL;
	memory = of_reserved_mem_lookup(node);
	ret = of_property_read_bool(node, "no-map") &&
	      !of_property_read_bool(node, "reusable") ? 0 : -EINVAL;
	of_node_put(node);
	if (ret || !memory)
		return -EINVAL;
	if (memory->size != 0x100000 || !memory->base ||
	    memory->base & 0xffff || memory->base > 0x80000000ULL - memory->size)
		return -EINVAL;
	if (of_property_read_u32(pdev->dev.of_node, "nothing,authenticated-bytes", &size) ||
	    size != 156064 || size > memory->size)
		return -EINVAL;
	expected = of_get_property(pdev->dev.of_node, "nothing,plaintext-sha256", &length);
	if (!expected || length != sizeof(digest))
		return -EINVAL;
	/* Never treat a no-map carveout's missing SYSRAM flag as permission for MMIO. */
	ret = flat_normal_reserved_ram(memory);
	if (ret)
		return ret;
	analysis = kzalloc(sizeof(*analysis), GFP_KERNEL);
	if (!analysis)
		return -ENOMEM;
	analysis->snapshot = kvmalloc(size, GFP_KERNEL);
	if (!analysis->snapshot) {
		ret = -ENOMEM;
		goto free_analysis;
	}
	mapping = memremap(memory->base, size, MEMREMAP_WB);
	if (!mapping) {
		ret = -ENOMEM;
		goto erase;
	}
	memcpy(analysis->snapshot, mapping, size);
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
	if (!ret && memcmp(digest, expected, sizeof(digest)))
		ret = -EBADMSG;
	memzero_explicit(digest, sizeof(digest));
	if (ret)
		goto erase;
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
free_analysis:
	kfree(analysis);
	return ret;
}

/* No remove/unbind: open descriptors reference the immutable verified snapshot.
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
