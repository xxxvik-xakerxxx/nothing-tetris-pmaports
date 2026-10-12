/* SPDX-License-Identifier: GPL-2.0-only */
#include <kunit/test.h>

static void camisp_no_iommu_component(struct kunit *test)
{
	struct mtk_smi_larb larb = { 0 };

	KUNIT_EXPECT_EQ(test, camisp_translation_check(&larb), -ENODEV);
}

static void camisp_normal_domain_ports(struct kunit *test)
{
	u32 mask = BIT(0) | BIT(1);
	u8 bank[32] = { 0 };
	struct mtk_smi_larb larb = { .mmu = &mask, .bank = bank };

	KUNIT_EXPECT_EQ(test, camisp_translation_check(&larb), 0);
	mask |= BIT(2);
	KUNIT_EXPECT_EQ(test, camisp_translation_check(&larb), -EBUSY);
	mask = BIT(0);
	KUNIT_EXPECT_EQ(test, camisp_translation_check(&larb), -EBUSY);
}

static void camisp_wrong_bank(struct kunit *test)
{
	u32 mask = BIT(0) | BIT(1);
	u8 bank[32] = { 0 };
	struct mtk_smi_larb larb = { .mmu = &mask, .bank = bank };
	unsigned int i;

	for (i = 0; i < 2; i++) {
		bank[i] = 1;
		KUNIT_EXPECT_EQ(test, camisp_translation_check(&larb), -EOPNOTSUPP);
		bank[i] = 0;
	}
}

static void camisp_no_array_padding(struct kunit *test)
{
	KUNIT_EXPECT_EQ(test, ARRAY_SIZE(camisp_larb13_bwl), (size_t)5);
	KUNIT_EXPECT_EQ(test, ARRAY_SIZE(camisp_larb14_bwl), (size_t)4);
	KUNIT_EXPECT_EQ(test, camisp_larb13_bwl[3], (u8)0x10);
	KUNIT_EXPECT_EQ(test, camisp_larb14_bwl[3], (u8)0x1);
}

static void camisp_display_root_identity(struct kunit *test)
{
	char compatible[] = "mediatek,mt6878-smi-common";
	char names[] = "apb\0smi";
	__be32 id = cpu_to_be32(0);
	struct property compat = {
		.name = "compatible", .value = compatible, .length = sizeof(compatible)
	};
	struct property clocks = {
		.name = "clock-names", .value = names, .length = sizeof(names), .next = &compat
	};
	struct property identity = {
		.name = "mediatek,common-id", .value = &id, .length = sizeof(id), .next = &clocks
	};
	struct device_node node = { .properties = &clocks };

	/* Stack-local properties, never an OF changeset or a registered device. */
	KUNIT_EXPECT_TRUE(test, camisp_display_root(&node));
	node.properties = &identity;
	KUNIT_EXPECT_TRUE(test, camisp_display_root(&node));
	id = cpu_to_be32(16);
	KUNIT_EXPECT_FALSE(test, camisp_display_root(&node));
	id = cpu_to_be32(0);
	identity.length = 3;
	KUNIT_EXPECT_FALSE(test, camisp_display_root(&node));
	identity.name = "mediatek,smi";
	KUNIT_EXPECT_FALSE(test, camisp_display_root(&node));
}

static struct kunit_case camisp_smi_cases[] = {
	KUNIT_CASE(camisp_no_iommu_component),
	KUNIT_CASE(camisp_normal_domain_ports),
	KUNIT_CASE(camisp_wrong_bank),
	KUNIT_CASE(camisp_no_array_padding),
	KUNIT_CASE(camisp_display_root_identity),
	{ }
};

static struct kunit_suite camisp_smi_suite = {
	.name = "mt6878-camisp-smi",
	.test_cases = camisp_smi_cases,
};
kunit_test_suite(camisp_smi_suite);
