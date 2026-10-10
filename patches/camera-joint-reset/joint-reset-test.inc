// SPDX-License-Identifier: GPL-2.0-only
#include <kunit/test.h>

static void joint_reset_reentry(struct kunit *test)
{
	struct mt6878_camera_joint_reset tx = { .attempted = true };

	KUNIT_EXPECT_EQ(test, joint_once(&tx), -EALREADY);
	tx.first_error = -ETIMEDOUT;
	KUNIT_EXPECT_EQ(test, joint_once(&tx), -ETIMEDOUT);
	KUNIT_EXPECT_EQ(test, mt6878_camera_joint_reset(&tx, NULL, NULL), -ETIMEDOUT);
	KUNIT_EXPECT_EQ(test, mt6878_camera_joint_reset(NULL, NULL, NULL), -EINVAL);
}

static void joint_reset_unbound(struct kunit *test)
{
	struct mt6878_native_capture *n = kunit_kzalloc(test, sizeof(*n), GFP_KERNEL);
	struct mt6878_camera_joint_reset tx = { 0 };
	struct mt6878_camsv_job job = { 0 };

	KUNIT_ASSERT_NOT_NULL(test, n);
	KUNIT_EXPECT_EQ(test, mt6878_camera_joint_reset(&tx, n, &job), -ENODEV);
	KUNIT_EXPECT_FALSE(test, tx.attempted);
	KUNIT_EXPECT_FALSE(test, tx.clamp_attempted);
}

static void joint_reset_cleanup_quarantine(struct kunit *test)
{
	struct mt6878_native_capture *n = kunit_kzalloc(test, sizeof(*n), GFP_KERNEL);
	struct mt6878_camera_joint_reset tx = { .attempted = true, .completed = true };

	KUNIT_ASSERT_NOT_NULL(test, n);
	mutex_init(&n->lock);
	n->reset_attempted = true;
	n->reset_completed = true; /* Reproduce previously visible healthy window. */
	mutex_lock(&n->lock);
	KUNIT_EXPECT_EQ(test, joint_finish(&tx, n, 0, -EIO), -EIO);
	KUNIT_EXPECT_EQ(test, n->first_error, -EIO);
	KUNIT_EXPECT_EQ(test, tx.first_error, -EIO);
	KUNIT_EXPECT_TRUE(test, n->reset_attempted);
	KUNIT_EXPECT_FALSE(test, n->reset_completed);
	KUNIT_EXPECT_FALSE(test, tx.completed);
	KUNIT_EXPECT_EQ(test, tx.lease_retire_error, -EIO);
	mutex_unlock(&n->lock);
}

static void joint_reset_first_failure_wins(struct kunit *test)
{
	struct mt6878_native_capture *n = kunit_kzalloc(test, sizeof(*n), GFP_KERNEL);
	struct mt6878_camera_joint_reset tx = { .attempted = true };

	KUNIT_ASSERT_NOT_NULL(test, n);
	mutex_init(&n->lock);
	n->first_error = -ETIMEDOUT;
	tx.first_error = -ETIMEDOUT;
	mutex_lock(&n->lock);
	KUNIT_EXPECT_EQ(test, joint_finish(&tx, n, -ETIMEDOUT, -EIO), -ETIMEDOUT);
	KUNIT_EXPECT_EQ(test, n->first_error, -ETIMEDOUT);
	KUNIT_EXPECT_EQ(test, tx.first_error, -ETIMEDOUT);
	KUNIT_EXPECT_EQ(test, tx.lease_retire_error, -EIO);
	KUNIT_EXPECT_FALSE(test, n->reset_completed);
	mutex_unlock(&n->lock);
}

static void joint_reset_cold_rejects_invalid_mode(struct kunit *test)
{
	struct mt6878_native_capture *n = kunit_kzalloc(test, sizeof(*n), GFP_KERNEL);
	struct mt6878_camera_cold_reset cold = { 0 };
	struct mt6878_camsv_job job = { .width = 1, .height = 1 };

	KUNIT_ASSERT_NOT_NULL(test, n);
	n->bound = true; /* Only reach request validation; no supplier is mocked. */
	KUNIT_EXPECT_EQ(test, mt6878_camera_cold_prepare(&cold, n, &job, 0, 0), -EINVAL);
	KUNIT_EXPECT_FALSE(test, cold.attempted);
	KUNIT_EXPECT_FALSE(test, cold.allocated);
}

static struct kunit_case joint_reset_cases[] = {
	KUNIT_CASE(joint_reset_reentry),
	KUNIT_CASE(joint_reset_unbound),
	KUNIT_CASE(joint_reset_cleanup_quarantine),
	KUNIT_CASE(joint_reset_first_failure_wins),
	KUNIT_CASE(joint_reset_cold_rejects_invalid_mode),
	{}
};

static struct kunit_suite joint_reset_suite = {
	.name = "mt6878-camera-joint-reset",
	.test_cases = joint_reset_cases,
};
kunit_test_suite(joint_reset_suite);
