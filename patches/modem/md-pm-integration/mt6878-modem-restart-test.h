/* SPDX-License-Identifier: GPL-2.0-only */
/* These tests exercise admission/errno only; they never invoke hardware helpers. */
#if IS_BUILTIN(CONFIG_KUNIT)
#include <kunit/test.h>

static void mt6878_md_restart_admission_test(struct kunit *test)
{
	struct mt6878_md_adoption *owner = kunit_kzalloc(test, sizeof(*owner), GFP_KERNEL);
	struct device *supplier = kunit_kzalloc(test, sizeof(*supplier), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, owner);
	KUNIT_ASSERT_NOT_NULL(test, supplier);
	owner->supplier = supplier;
	owner->state = MT6878_MD_FIRST_OFF_COMPLETE;
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, NULL, supplier), -EXDEV);
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, owner, NULL), -EXDEV);
	KUNIT_EXPECT_FALSE(test, owner->restart.attempted);
	owner->state = MT6878_MD_OBSERVED_ON;
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), -EBUSY);
	KUNIT_EXPECT_FALSE(test, owner->restart.attempted);
	owner->state = MT6878_MD_FIRST_OFF_COMPLETE;
	owner->attached = supplier;
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), -EBUSY);
	owner->attached = NULL;
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), 0);
	KUNIT_EXPECT_TRUE(test, owner->restart.attempted);
	KUNIT_EXPECT_EQ(test, owner->restart.step, MT6878_MD_RESTART_HANDOFF);
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), -EALREADY);
}

static void mt6878_md_restart_first_errno_test(struct kunit *test)
{
	struct mt6878_md_adoption *owner = kunit_kzalloc(test, sizeof(*owner), GFP_KERNEL);
	struct device *supplier = kunit_kzalloc(test, sizeof(*supplier), GFP_KERNEL);
	static const int errors[] = {
		-EPROBE_DEFER, -ESTALE, -EINVAL, -ENODEV, -EIO, -ETIMEDOUT, -EOPNOTSUPP,
	};
	unsigned int i;

	KUNIT_ASSERT_NOT_NULL(test, owner);
	KUNIT_ASSERT_NOT_NULL(test, supplier);
	for (i = 0; i < ARRAY_SIZE(errors); i++) {
		/* Each iteration is a fresh software fixture, not a production reset. */
		memset(owner, 0, sizeof(*owner));
		owner->supplier = supplier;
		owner->state = MT6878_MD_FIRST_OFF_COMPLETE;
		KUNIT_ASSERT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), 0);
		KUNIT_EXPECT_EQ(test, mt6878_md_restart_stop(owner, errors[i]), errors[i]);
		KUNIT_EXPECT_EQ(test, mt6878_md_restart_stop(owner, -EOPNOTSUPP), errors[i]);
		KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), errors[i]);
		KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, NULL, NULL), errors[i]);
		KUNIT_EXPECT_EQ(test, owner->state, MT6878_MD_FIRST_OFF_COMPLETE);
	}
}

static void mt6878_md_restart_no_grant_test(struct kunit *test)
{
	struct mt6878_md_adoption *owner = kunit_kzalloc(test, sizeof(*owner), GFP_KERNEL);
	struct device *supplier = kunit_kzalloc(test, sizeof(*supplier), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, owner);
	KUNIT_ASSERT_NOT_NULL(test, supplier);
	owner->supplier = supplier;
	owner->state = MT6878_MD_FIRST_OFF_COMPLETE;
	KUNIT_ASSERT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), 0);
	owner->restart.step = MT6878_MD_RESTART_INHIBIT_BOUNDARY;
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_stop(owner, -EOPNOTSUPP), -EOPNOTSUPP);
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), -EOPNOTSUPP);
	KUNIT_EXPECT_PTR_EQ(test, owner->supplier, supplier);
	KUNIT_EXPECT_PTR_EQ(test, owner->attached, NULL);
	KUNIT_EXPECT_EQ(test, owner->state, MT6878_MD_FIRST_OFF_COMPLETE);
	owner->first_error = 0;
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_stop(owner, 0), -EPROTO);
}

static void mt6878_md_restart_callback_veto_test(struct kunit *test)
{
	struct mt6878_md_adoption *owner = kunit_kzalloc(test, sizeof(*owner), GFP_KERNEL);
	struct scpsys_domain *pd = kunit_kzalloc(test, sizeof(*pd), GFP_KERNEL);
	struct device *supplier = kunit_kzalloc(test, sizeof(*supplier), GFP_KERNEL);
	struct device_node *node = kunit_kzalloc(test, sizeof(*node), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, owner);
	KUNIT_ASSERT_NOT_NULL(test, pd);
	KUNIT_ASSERT_NOT_NULL(test, supplier);
	KUNIT_ASSERT_NOT_NULL(test, node);
	mutex_init(&owner->lock);
	owner->supplier = supplier;
	owner->state = MT6878_MD_FIRST_OFF_COMPLETE;
	owner->restart.top_node = node;
	owner->restart.rail_nodes[0] = node;
	pd->md_adoption = owner;
	KUNIT_ASSERT_EQ(test, mt6878_md_restart_begin(owner, owner, supplier), 0);
	KUNIT_EXPECT_EQ(test, mt6878_md_adopt_transition(&pd->genpd), -EOPNOTSUPP);
	KUNIT_EXPECT_EQ(test, mt6878_md_restart_stop(owner, -EIO), -EIO);
	KUNIT_EXPECT_EQ(test, mt6878_md_adopt_transition(&pd->genpd), -EIO);
	KUNIT_EXPECT_PTR_EQ(test, owner->restart.top_node, node);
	KUNIT_EXPECT_PTR_EQ(test, owner->restart.rail_nodes[0], node);
}

static struct kunit_case mt6878_md_restart_cases[] = {
	KUNIT_CASE(mt6878_md_restart_admission_test),
	KUNIT_CASE(mt6878_md_restart_first_errno_test),
	KUNIT_CASE(mt6878_md_restart_no_grant_test),
	KUNIT_CASE(mt6878_md_restart_callback_veto_test),
	{ }
};

static struct kunit_suite mt6878_md_restart_suite = {
	.name = "mt6878-md-inhibited-restart-owner",
	.test_cases = mt6878_md_restart_cases,
};
kunit_test_suite(mt6878_md_restart_suite);
#endif
