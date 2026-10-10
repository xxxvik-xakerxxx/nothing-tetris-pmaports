// SPDX-License-Identifier: GPL-2.0-only
#include <kunit/test.h>
#include "mt6878-native-capture.h"

struct failed_start_fixture {
	struct mt6878_native_capture owner;
	struct v4l2_subdev sensor, receiver;
	struct media_pad sensor_pad, receiver_pads[2];
	unsigned int cleanup_calls, writes;
	int cleanup_error;
};

static int fail_on(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
	u32 pad, u64 mask)
{
	(void)sd;
	(void)state;
	(void)pad;
	(void)mask;
	return -EIO;
}

static int fail_off(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
	u32 pad, u64 mask)
{
	return fail_on(sd, state, pad, mask); /* Must not be invoked for failed ON. */
}

static int cleanup(struct v4l2_subdev *sd, int on)
{
	struct failed_start_fixture *f = v4l2_get_subdevdata(sd);

	if (on)
		return -EINVAL;
	f->cleanup_calls++;
	return f->cleanup_error;
}

static const struct v4l2_subdev_core_ops core_ops = { .s_power = cleanup };
static const struct v4l2_subdev_pad_ops pad_ops = {
	.enable_streams = fail_on, .disable_streams = fail_off,
};
static const struct v4l2_subdev_ops sensor_ops = { .core = &core_ops, .pad = &pad_ops };
static const struct v4l2_subdev_ops receiver_ops = { .pad = &pad_ops };

static int read_fixture(void *context, enum mt6878_seninf_region r,
	unsigned int offset, unsigned int *value)
{
	(void)context;
	(void)r;
	(void)offset;
	*value = 0;
	return 0;
}

static int write_fixture(void *context, enum mt6878_seninf_region r,
	unsigned int offset, unsigned int value)
{
	struct failed_start_fixture *f = context;

	(void)r;
	(void)offset;
	(void)value;
	f->writes++;
	return 0;
}

static int check_fixture(void *context, enum mt6878_seninf_action action,
	const struct mt6878_seninf_plan *plan)
{
	(void)context;
	(void)action;
	(void)plan;
	return 0; /* KUnit in-memory register fixture, no live provider or mapping. */
}

static int delay_fixture(void *context, unsigned int us)
{
	(void)context;
	(void)us;
	return 0;
}

static void failed_start(struct kunit *test)
{
	struct failed_start_fixture *f;
	struct mt6878_seninf_controller *c;
	struct mt6878_camsv_platform *p;
	unsigned int writes;
	int error;

	for (error = 0; error >= -EIO; error -= EIO) {
		f = kunit_kzalloc(test, sizeof(*f), GFP_KERNEL);
		KUNIT_ASSERT_NOT_NULL(test, f);
		v4l2_subdev_init(&f->sensor, &sensor_ops);
		v4l2_subdev_init(&f->receiver, &receiver_ops);
		v4l2_set_subdevdata(&f->sensor, f);
		f->sensor_pad.flags = f->receiver_pads[1].flags = MEDIA_PAD_FL_SOURCE;
		f->receiver_pads[0].flags = MEDIA_PAD_FL_SINK;
		KUNIT_ASSERT_EQ(test, media_entity_pads_init(&f->sensor.entity, 1, &f->sensor_pad), 0);
		KUNIT_ASSERT_EQ(test, media_entity_pads_init(&f->receiver.entity, 2, f->receiver_pads), 0);
		KUNIT_ASSERT_EQ(test, v4l2_subdev_init_finalize(&f->sensor), 0);
		KUNIT_ASSERT_EQ(test, v4l2_subdev_init_finalize(&f->receiver), 0);
		KUNIT_EXPECT_EQ(test, v4l2_subdev_enable_streams(&f->sensor, 0, 1), -EIO);
		KUNIT_EXPECT_EQ(test, v4l2_subdev_enable_streams(&f->receiver, 1, 1), -EIO);
		KUNIT_EXPECT_EQ(test, v4l2_subdev_disable_streams(&f->receiver, 1, 1), -EALREADY);
		f->cleanup_error = error;
		f->owner.bound = true;
		p = &f->owner.platform;
		p->native_capture = &f->owner;
		c = &f->owner.controller;
		mutex_init(&p->lifecycle);
		mutex_init(&c->core);
		mutex_init(&f->owner.direct.lock);
		p->receiver = &f->receiver;
		p->sensor = &f->sensor;
		p->direct = &f->owner.direct;
		c->capture = p;
		c->requested = 2;
		c->allocated = true;
		c->route.source_attempted = true;
		c->allocation = (struct mt6878_route_plan) {
			.outputs = { { 0, 0, 0, 1, 2 }, { 0, 0, 1, 0, 2 } },
			.cammux = { 0, 1 }, .tags = { 0, 1 }, .width = 4000, .height = 3000,
		};
		c->route.route.plan = c->allocation;
		c->route.route.attempted = c->route.route.configured = 1;
		c->route.backend.io = (struct mt6878_seninf_backend) {
			.read = read_fixture, .write = write_fixture,
			.check = check_fixture, .delay_us = delay_fixture,
			.context = f, .base_size = 0x18000, .analog_size = 0x30000,
		};
		f->owner.direct.first_error = -EIO;
		v4l2_set_subdev_hostdata(&f->receiver, c);
		mutex_lock(&p->lifecycle);
		KUNIT_EXPECT_EQ(test, mt6878_native_capture_receiver_stop(p), error);
		writes = f->writes;
		KUNIT_EXPECT_EQ(test, mt6878_native_capture_receiver_stop(p), error ? error : -EALREADY);
		mutex_unlock(&p->lifecycle);
		KUNIT_EXPECT_EQ(test, f->cleanup_calls, 1U);
		KUNIT_EXPECT_EQ(test, f->writes, writes);
		KUNIT_EXPECT_EQ(test, f->owner.direct.first_error, -EIO);
		KUNIT_EXPECT_EQ(test, c->route.source_stopped, !error);
		KUNIT_EXPECT_EQ(test, c->route.route.disconnected, error ? 0U : 1U);
		v4l2_subdev_cleanup(&f->receiver);
		v4l2_subdev_cleanup(&f->sensor);
		media_entity_cleanup(&f->receiver.entity);
		media_entity_cleanup(&f->sensor.entity);
	}
}

static struct kunit_case cases[] = { KUNIT_CASE(failed_start), { } };
static struct kunit_suite suite = { .name = "mt6878-native-failed-start", .test_cases = cases };
kunit_test_suite(suite);
MODULE_LICENSE("GPL");
