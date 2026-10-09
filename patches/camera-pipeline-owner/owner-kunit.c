// SPDX-License-Identifier: GPL-2.0-only
/* CI KUnit only. Synthetic exporter, no physical camera or MMIO. */
#include <kunit/test.h>
#include <kunit/resource.h>
#include <linux/module.h>
#include <linux/fcntl.h>
#include <linux/scatterlist.h>
#include <linux/slab.h>
#include "mt6878-camera-pipeline-owner.h"

enum fault { NO_FAULT, ATTACH_FAULT, MAP_FAULT, MULTI_SG, SHORT_SG, VMAP_FAULT, IOMEM_VMAP };

struct exporter {
	enum fault fault;
	unsigned int attaches, detaches, maps, unmaps, vmaps, vunmaps;
	unsigned char bytes[1024];
};

static int test_attach(struct dma_buf *buffer, struct dma_buf_attachment *attachment)
{
	struct exporter *exporter = buffer->priv;

	exporter->attaches++;
	return exporter->fault == ATTACH_FAULT ? -EACCES : 0;
}

static void test_detach(struct dma_buf *buffer, struct dma_buf_attachment *attachment)
{
	struct exporter *exporter = buffer->priv;

	exporter->detaches++;
}

static struct sg_table *test_map(struct dma_buf_attachment *attachment, enum dma_data_direction dir)
{
	struct exporter *exporter = attachment->dmabuf->priv;
	struct sg_table *table;
	int ret;

	exporter->maps++;
	if (exporter->fault == MAP_FAULT)
		return ERR_PTR(-ENOSPC);
	table = kzalloc(sizeof(*table), GFP_KERNEL);
	if (!table)
		return ERR_PTR(-ENOMEM);
	ret = sg_alloc_table(table, exporter->fault == MULTI_SG ? 2 : 1, GFP_KERNEL);
	if (ret) {
		kfree(table);
		return ERR_PTR(ret);
	}
	/* Synthetic mapped IOVA supplied by this fault exporter, never a physical address. */
	sg_dma_address(table->sgl) = 0x100000000ULL;
	sg_dma_len(table->sgl) = exporter->fault == SHORT_SG ? 512 : sizeof(exporter->bytes);
	return table;
}

static void test_unmap(struct dma_buf_attachment *attachment,
	struct sg_table *table, enum dma_data_direction dir)
{
	struct exporter *exporter = attachment->dmabuf->priv;

	exporter->unmaps++;
	sg_free_table(table);
	kfree(table);
}

static int test_vmap(struct dma_buf *buffer, struct iosys_map *map)
{
	struct exporter *exporter = buffer->priv;

	exporter->vmaps++;
	iosys_map_set_vaddr(map, exporter->bytes);
	map->is_iomem = exporter->fault == IOMEM_VMAP;
	return 0;
}

static void test_vunmap(struct dma_buf *buffer, struct iosys_map *map)
{
	struct exporter *exporter = buffer->priv;

	exporter->vunmaps++;
}

static void test_release(struct dma_buf *buffer)
{
	kfree(buffer->priv);
}

static const struct dma_buf_ops ops = {
	.attach = test_attach, .detach = test_detach,
	.map_dma_buf = test_map, .unmap_dma_buf = test_unmap,
	.vmap = test_vmap, .vunmap = test_vunmap, .release = test_release,
};

/* Missing vmap is a real error path without DMA-BUF's WARN_ON exporter error. */
static const struct dma_buf_ops ops_no_vmap = {
	.attach = test_attach, .detach = test_detach,
	.map_dma_buf = test_map, .unmap_dma_buf = test_unmap, .release = test_release,
};

static void put_buffer(void *buffer)
{
	dma_buf_put(buffer);
}

static void put_root(void *device)
{
	root_device_unregister(device);
}

static void mapping_faults(struct kunit *test)
{
	DEFINE_DMA_BUF_EXPORT_INFO(info);
	struct mt6878_pipeline_mapping mapping = { 0 };
	struct device *device;
	struct exporter *exporter;
	struct dma_buf *buffer;
	enum fault fault;
	int ret, expected;

	device = root_device_register("mt6878-camera-owner-kunit");
	KUNIT_ASSERT_FALSE(test, IS_ERR(device));
	KUNIT_ASSERT_EQ(test, kunit_add_action_or_reset(test, put_root, device), 0);
	for (fault = NO_FAULT; fault <= IOMEM_VMAP; fault++) {
		exporter = kzalloc(sizeof(*exporter), GFP_KERNEL);
		KUNIT_ASSERT_NOT_NULL(test, exporter);
		exporter->fault = fault;
		info.ops = fault == VMAP_FAULT ? &ops_no_vmap : &ops;
		info.size = sizeof(exporter->bytes);
		info.flags = O_RDWR;
		info.priv = exporter;
		buffer = dma_buf_export(&info);
		if (IS_ERR(buffer)) {
			kfree(exporter);
			KUNIT_FAIL(test, "fault exporter creation failed");
			return;
		}
		KUNIT_ASSERT_EQ(test, kunit_add_action_or_reset(test, put_buffer, buffer), 0);
		expected = fault == NO_FAULT ? 0 :
			fault == ATTACH_FAULT ? -EACCES : fault == MAP_FAULT ? -ENOSPC :
			fault == VMAP_FAULT ? -EINVAL : fault == IOMEM_VMAP ? -EOPNOTSUPP : -ERANGE;
		ret = mt6878_pipeline_map(&mapping, buffer, device, 956);
		KUNIT_EXPECT_EQ(test, ret, expected);
		if (!ret) {
			KUNIT_EXPECT_EQ(test, mapping.range.dma, 0x100000000ULL);
			KUNIT_EXPECT_EQ(test, mapping.range.size, 1024U);
			KUNIT_EXPECT_EQ(test, file_count(buffer->file), 2UL);
			mt6878_pipeline_unmap(&mapping);
		}
		KUNIT_EXPECT_PTR_EQ(test, mapping.buffer, NULL);
		KUNIT_EXPECT_EQ(test, file_count(buffer->file), 1UL);
		KUNIT_EXPECT_EQ(test, exporter->attaches, 1U);
		KUNIT_EXPECT_EQ(test, exporter->detaches, fault == ATTACH_FAULT ? 0U : 1U);
		KUNIT_EXPECT_EQ(test, exporter->unmaps,
			fault == ATTACH_FAULT || fault == MAP_FAULT ? 0U : 1U);
		KUNIT_EXPECT_EQ(test, exporter->vunmaps,
			fault == NO_FAULT || fault == IOMEM_VMAP ? 1U : 0U);
	}
}

static void callback_gate(struct kunit *test)
{
	struct mt6878_pipeline_owner *owner;

	owner = kunit_kzalloc(test, sizeof(*owner), GFP_KERNEL);
	KUNIT_ASSERT_NOT_NULL(test, owner);
	spin_lock_init(&owner->callback_lock);
	mt6878_camera_ccd_init(&owner->ccd, 0);
	/* Foreign callback reaches the real CCD identity checker and releases its entry. */
	KUNIT_EXPECT_EQ(test, mt6878_pipeline_rx(NULL, NULL, 0, owner, 0), -ESTALE);
	KUNIT_EXPECT_EQ(test, owner->callback_users, 0U);
	/* Simulate an entry already held; closure refuses to report drain. */
	owner->callback_users = 1;
	KUNIT_EXPECT_EQ(test, mt6878_pipeline_close_callback_gate(owner), -EBUSY);
	KUNIT_EXPECT_EQ(test, mt6878_pipeline_rx(NULL, NULL, 0, owner, 0), -ESHUTDOWN);
	KUNIT_EXPECT_EQ(test, owner->callback_users, 1U);
	owner->callback_users = 0;
	KUNIT_EXPECT_EQ(test, mt6878_pipeline_close_callback_gate(owner), 0);
	KUNIT_EXPECT_EQ(test, mt6878_pipeline_start(owner), -EOPNOTSUPP);
}

static struct kunit_case cases[] = {
	KUNIT_CASE(mapping_faults), KUNIT_CASE(callback_gate), {}
};

static struct kunit_suite suite = {
	.name = "mt6878-camera-pipeline-owner", .test_cases = cases,
};
kunit_test_suite(suite);
MODULE_LICENSE("GPL");
MODULE_IMPORT_NS("DMA_BUF");
