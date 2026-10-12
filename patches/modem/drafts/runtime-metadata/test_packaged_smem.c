/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the actual packaged importer and pinned vendor lookup. */
static unsigned int plan_allocs, plan_fail;
struct device_node { int unused; };
struct property { int unused; };
static struct device_node test_node;
static struct property test_property;
static unsigned char evidence_wire[336];
static bool node_exists = true, compatible = true, property_exists;
static int property_length = 336, property_read_error;
static unsigned int acquired, released;
static unsigned int module_pins;

void __module_get(void *module)
{
	assert(module == THIS_MODULE);
	module_pins++;
}

static struct device_node *of_find_node_by_path(const char *path)
{
	assert(!strcmp(path, "/modem"));
	if (!node_exists)
		return NULL;
	acquired++;
	return &test_node;
}
static bool of_device_is_compatible(const struct device_node *node, const char *name)
{
	assert(node == &test_node && !strcmp(name, "mediatek,mddriver"));
	return compatible;
}
static const struct property *of_find_property(const struct device_node *node,
		const char *name, int *length)
{
	assert(node == &test_node && !strcmp(name, "nothing,modem-smem-boot-evidence"));
	if (!property_exists)
		return NULL;
	*length = property_length;
	return &test_property;
}
static int of_property_read_u8_array(const struct device_node *node,
		const char *name, unsigned char *output, size_t size)
{
	assert(node == &test_node && !strcmp(name, "nothing,modem-smem-boot-evidence"));
	assert(size == sizeof(evidence_wire) && property_length == (int)size);
	if (property_read_error)
		return property_read_error;
	memcpy(output, evidence_wire, size);
	return 0;
}
static void of_node_put(struct device_node *node)
{
	assert(node == &test_node);
	released++;
}
void *kzalloc(size_t size, int flags)
{
	(void)flags;
	return ++plan_allocs == plan_fail ? NULL : calloc(1, size);
}
#include "owned_smem_plan.c"

static void put64(unsigned char *p, unsigned long long value)
{
	put32(p, value);
	put32(p + 4, value >> 32);
}

static void evidence_fixture(const struct tetris_metadata_banks *banks,
		unsigned int nc_size, unsigned int cache_size)
{
	static const unsigned char digest[32] =
		"\x5d\x2b\xed\xd0\x00\x49\xfc\xed\x98\x3d\x3a\xe5\x39\x89\x61\x6c"
		"\x5c\x9f\x46\xc4\xed\xdd\x32\xa0\x1a\x1a\xd4\x6f\xf8\xd2\xc5\x0f";
	unsigned int i;

	memset(evidence_wire, 0, sizeof(evidence_wire));
	put32(evidence_wire, 1);
	put32(evidence_wire + 4, sizeof(evidence_wire));
	put32(evidence_wire + 8, 1);
	put32(evidence_wire + 12, 2);
	put32(evidence_wire + 16, 6878);
	put32(evidence_wire + 20, 6299);
	put32(evidence_wire + 24, 11);
	put32(evidence_wire + 28, 15);
	memcpy(evidence_wire + 48, digest, sizeof(digest));
	for (i = 0; i < 2; i++) {
		const struct tetris_metadata_window *w = i ? &banks->cache : &banks->nc;
		unsigned char *p = evidence_wire + 80 + i * 128;
		unsigned long long size = ((unsigned long long)(i ? cache_size : nc_size) + 65535) & ~65535ULL;

		put32(p, i);
		put32(p + 4, 42 + i);
		put64(p + 8, w->base);
		put64(p + 16, w->capacity);
		put64(p + 24, w->base);
		put64(p + 32, size);
		put64(p + 40, w->base);
		put64(p + 48, w->base + size);
		put64(p + 56, 1);
		put64(p + 72, i ? 0xc00300c0ULL : 0xcff0f0c0ULL);
		put64(p + 120, 0xc00000000ULL);
	}
}

static void test_evidence_collection(const struct tetris_metadata_banks *banks)
{
	unsigned int nc_size = tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.size;
	unsigned int cache_size = tetris_owned_smem_plan.layout.md_bank4_cacheable_total.size;
	unsigned int mode;
	static const int expected[] = { 0, -EMSGSIZE, -EMSGSIZE, -EMSGSIZE,
		-EBADMSG, -EIO, -ENODEV, -EINVAL, -ERANGE };

	for (mode = 0; mode < ARRAY_SIZE(expected); mode++) {
		mtk_ccci_owned_smem_cleanup();
		evidence_fixture(banks, nc_size, cache_size);
		node_exists = compatible = property_exists = true;
		property_length = sizeof(evidence_wire);
		property_read_error = 0;
		switch (mode) {
		case 1: property_length = 0; break;
		case 2: property_length--; break;
		case 3: property_length++; break;
		case 4: evidence_wire[8] ^= 2; break;
		case 5: property_read_error = -EIO; break;
		case 6: node_exists = false; break;
		case 7: compatible = false; break;
		case 8:
			/* Decoder-valid range that cannot cover the imported plan. */
			put64(evidence_wire + 80 + 32, 4096);
			put64(evidence_wire + 80 + 48, banks->nc.base + 4096);
			break;
		}
		assert(mtk_ccci_owned_smem_init() == expected[mode]);
		assert(acquired == released);
		if (expected[mode]) {
			assert(!tetris_owned_smem_plan.ready);
			assert(!tetris_owned_smem_plan.has_boot_evidence);
			assert(!tetris_owned_smem_plan.layout.md_bank4_noncacheable);
		} else {
			assert(tetris_owned_smem_plan.ready && tetris_owned_smem_plan.has_boot_evidence);
			assert(tetris_owned_smem_plan.boot_evidence.record[0].reservation_base == banks->nc.base);
			memset(evidence_wire, 0xa5, sizeof(evidence_wire));
			assert(tetris_owned_smem_plan.boot_evidence.version == 1);
			assert(!tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.base_ap_view_vir);
		}
	}
	node_exists = compatible = true;
	property_exists = false;
	property_read_error = 0;
	mtk_ccci_owned_smem_cleanup();
#if CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
	assert(mtk_ccci_owned_smem_init() == -ENODATA);
	assert(!tetris_owned_smem_plan.ready && !tetris_owned_smem_plan.owner);
#else
	assert(!mtk_ccci_owned_smem_init());
	assert(tetris_owned_smem_plan.ready && !tetris_owned_smem_plan.has_boot_evidence);
#endif
	assert(acquired == released);
}

#include "test_smem_reservation.c"

static void packaged_probe(struct tetris_metadata_banks *source, int imported)
{
	struct tetris_metadata_banks copied, untouched;
	unsigned int i;

	memset(&untouched, 0xa5, sizeof(untouched));
	copied = untouched;
	assert(mtk_ccci_owned_banks_copy(NULL) == -EINVAL);
	if (imported) {
		assert(mtk_ccci_owned_banks_copy(&copied) == -ENODATA);
		assert(!memcmp(&copied, &untouched, sizeof(copied)));
		assert(mtk_ccci_owned_smem_init() == -ENODATA);
		assert(!tetris_owned_smem_plan.ready && !plan_allocs);
	} else {
		assert(!mtk_ccci_owned_banks_copy(&copied));
		assert(!memcmp(&copied, source, sizeof(copied)));
		/* Prove retained banks, like tags, do not borrow caller storage. */
		memset(source, 0xa5, sizeof(*source));
		assert(!mtk_ccci_owned_banks_copy(&untouched));
		assert(!memcmp(&copied, &untouched, sizeof(copied)));
		for (i = 1; i <= 2; i++) {
			plan_allocs = 0;
			plan_fail = i;
			assert(mtk_ccci_owned_smem_init() == -ENOMEM);
			assert(!tetris_owned_smem_plan.ready);
		}
		plan_fail = 0;
#if CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
		{
			struct tetris_smem_owner *seed = NULL;

			assert(!tetris_smem_from_arguments(&copied, &seed));
			evidence_fixture(&copied, seed->nc_size, seed->cache_size);
			assert(!tetris_smem_destroy(seed));
			property_exists = true;
		}
#endif
		assert(!mtk_ccci_owned_smem_init());
		assert(tetris_owned_smem_plan.ready);
#if CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY
		assert(module_pins == 1);
		assert(tetris_owned_smem_plan.owner);
		assert(tetris_owned_smem_plan.reservation.count == 2);
#else
		assert(!module_pins);
#endif
		assert(mtk_ccci_owned_smem_init() == -EALREADY);
		assert(tetris_owned_smem_plan.layout.md_bank0.base_ap_view_phy == copied.firmware.base);
		assert(!tetris_owned_smem_plan.layout.md_bank0.base_ap_view_vir);
		assert(!tetris_owned_smem_plan.layout.md_bank4_noncacheable_total.base_ap_view_vir);
		assert(!tetris_owned_smem_plan.layout.md_bank4_cacheable_total.base_ap_view_vir);
		assert(tetris_owned_smem_plan.layout.md_bank4_noncacheable == tetris_owned_smem_plan.nc);
		assert(tetris_owned_smem_plan.layout.md_bank4_cacheable == tetris_owned_smem_plan.cache);
		for (i = 0; i < ARRAY_SIZE(tetris_owned_smem_plan.nc); i++)
			assert(!tetris_owned_smem_plan.nc[i].base_ap_view_vir);
		for (i = 0; i < ARRAY_SIZE(tetris_owned_smem_plan.cache); i++)
			assert(!tetris_owned_smem_plan.cache[i].base_ap_view_vir);
		test_evidence_collection(&copied);
		mtk_ccci_owned_smem_cleanup();
		test_smem_reservation(&copied);
	}
	mtk_ccci_owned_smem_cleanup();
	mtk_ccci_owned_args_cleanup();
	assert(!tetris_owned_smem_plan.ready && !tetris_owned_tags && !s_init_done);
	copied = untouched;
	assert(mtk_ccci_owned_banks_copy(&copied) == -ENODATA);
	assert(!memcmp(&copied, &untouched, sizeof(copied)));
	assert(mtk_ccci_owned_smem_init() == -ENODATA);
	mtk_ccci_owned_smem_cleanup();
	mtk_ccci_owned_args_cleanup();
}
