/* SPDX-License-Identifier: GPL-2.0-only */
#include <kunit/test.h>

static void epoch_sticky_error(struct kunit *test)
{
	struct mt6878_capture_epoch *e = kunit_kzalloc(test, sizeof(*e), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, e);
	KUNIT_EXPECT_EQ(test, epoch_error(e, -ETIMEDOUT), -ETIMEDOUT);
	KUNIT_EXPECT_EQ(test, epoch_error(e, -EIO), -ETIMEDOUT);
	KUNIT_EXPECT_EQ(test, epoch_error(e, 0), -ETIMEDOUT);
}

static void epoch_unretired_storage(struct kunit *test)
{
	struct mt6878_capture_epoch *e = kunit_kzalloc(test, sizeof(*e), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, e);
	KUNIT_EXPECT_EQ(test, mt6878_capture_epoch_free(e), -EBUSY);
}

static void epoch_requires_bound_owner(struct kunit *test)
{
	struct mt6878_native_capture *n = kunit_kzalloc(test, sizeof(*n), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, n);
	KUNIT_EXPECT_EQ(test, PTR_ERR(mt6878_capture_epoch_alloc(n)), -ENODEV);
}

static void epoch_stale_done_does_not_complete(struct kunit *test)
{
	struct mt6878_camsv_transaction *tx = kunit_kzalloc(test, sizeof(*tx), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, tx);
	tx->submitted = 1;
	tx->job.sequence = 12;
	tx->job.raw_tag = 0;
	tx->job.pdaf_tag = 1;
	tx->job.group_tags[0] = BIT(0) | BIT(1);
	KUNIT_EXPECT_EQ(test, mt6878_camsv_done(tx, BIT(16), 11), -ESTALE);
	KUNIT_EXPECT_EQ(test, tx->complete_tags, 0U);
	KUNIT_EXPECT_EQ(test, mt6878_camsv_done(tx, BIT(16), 12), 1);
}

static void epoch_failed_stop_never_authorizes_next(struct kunit *test)
{
	struct mt6878_camsv_direct *d = kunit_kzalloc(test, sizeof(*d), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, d);
	d->job.raw_tag = 0;
	d->job.pdaf_tag = 1;
	d->completion_observed = true;
	d->pair.completed = 1;
	d->pair.tx.hw_attempted = 1;
	d->pair.tx.off_attempted = 1;
	d->pair.tx.complete_tags = BIT(0) | BIT(1);
	KUNIT_EXPECT_EQ(test, epoch_done(d), -EBUSY); /* Missing actual DMA OFF. */
	d->pair.tx.first_error = -ETIMEDOUT;
	KUNIT_EXPECT_EQ(test, epoch_done(d), -ETIMEDOUT);
}

static struct kunit_case epoch_cases[] = {
	KUNIT_CASE(epoch_sticky_error),
	KUNIT_CASE(epoch_unretired_storage),
	KUNIT_CASE(epoch_requires_bound_owner),
	KUNIT_CASE(epoch_stale_done_does_not_complete),
	KUNIT_CASE(epoch_failed_stop_never_authorizes_next),
	{}
};

static struct kunit_suite epoch_suite = {
	.name = "mt6878-capture-epoch",
	.test_cases = epoch_cases,
};
kunit_test_suite(epoch_suite);
