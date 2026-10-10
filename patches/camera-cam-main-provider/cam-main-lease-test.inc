// SPDX-License-Identifier: GPL-2.0-only
#include <kunit/test.h>
#include <linux/completion.h>
#include <linux/kthread.h>

static void cam_main_invalid_acquire(struct kunit *test)
{
	struct mt6878_cam_main_lease *lease = (void *)test;

	KUNIT_EXPECT_EQ(test, mt6878_cam_main_prepare(NULL, &lease), -EINVAL);
	KUNIT_EXPECT_PTR_EQ(test, lease, NULL);
	KUNIT_EXPECT_EQ(test, mt6878_cam_main_prepare(NULL, NULL), -EINVAL);
}

static void cam_main_wrong_task_retirement(struct kunit *test)
{
	struct mt6878_cam_main_lease lease = { .task = NULL };
	struct mt6878_cam_main_lease *slot = &lease;

	KUNIT_EXPECT_EQ(test, mt6878_cam_main_retire(&slot), -EPERM);
	KUNIT_EXPECT_PTR_EQ(test, slot, &lease);
	KUNIT_EXPECT_EQ(test, mt6878_cam_main_retire(NULL), -EINVAL);
}

static void cam_main_reset_without_lease(struct kunit *test)
{
	KUNIT_EXPECT_EQ(test, mt6878_cam_main_reset_pulse(NULL, 0), -EINVAL);
	KUNIT_EXPECT_TRUE(test, IS_ERR(mt6878_cam_main_regmap(NULL)));
}

struct cam_main_lock_race {
	struct device supplier;
	struct completion attempted;
	int result;
};

static int cam_main_other_task(void *arg)
{
	struct cam_main_lock_race *race = arg;

	race->result = device_trylock(&race->supplier) ? 0 : -EBUSY;
	if (!race->result)
		device_unlock(&race->supplier);
	complete(&race->attempted);
	/* Keep stack storage and task valid until the test always stops us. */
	set_current_state(TASK_INTERRUPTIBLE);
	while (!kthread_should_stop()) {
		schedule();
		set_current_state(TASK_INTERRUPTIBLE);
	}
	__set_current_state(TASK_RUNNING);
	return 0;
}

static void cam_main_device_lock_exclusion(struct kunit *test)
{
	struct cam_main_lock_race race = { .result = -EINPROGRESS };
	struct task_struct *task;
	unsigned long done;
	bool locked;

	/* Same mutex the driver core holds across remove; no hardware device. */
	mutex_init(&race.supplier.mutex);
	init_completion(&race.attempted);
	device_lock(&race.supplier);
	task = kthread_run(cam_main_other_task, &race, "cam-main-lease-test");
	if (IS_ERR(task)) {
		device_unlock(&race.supplier);
		KUNIT_FAIL(test, "cannot create lease contention worker");
		return;
	}
	done = wait_for_completion_timeout(&race.attempted, HZ);
	KUNIT_EXPECT_NE(test, done, 0UL);
	if (done)
		KUNIT_EXPECT_EQ(test, race.result, -EBUSY);
	device_unlock(&race.supplier);
	kthread_stop(task);
	locked = device_trylock(&race.supplier);
	KUNIT_EXPECT_TRUE(test, locked);
	if (locked)
		device_unlock(&race.supplier);
}

static struct kunit_case cam_main_lease_cases[] = {
	KUNIT_CASE(cam_main_invalid_acquire),
	KUNIT_CASE(cam_main_wrong_task_retirement),
	KUNIT_CASE(cam_main_reset_without_lease),
	KUNIT_CASE(cam_main_device_lock_exclusion),
	{}
};

static struct kunit_suite cam_main_lease_suite = {
	.name = "mt6878-cam-main-lease",
	.test_cases = cam_main_lease_cases,
};
kunit_test_suite(cam_main_lease_suite);
