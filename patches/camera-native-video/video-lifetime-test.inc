// SPDX-License-Identifier: GPL-2.0-only
/* Included in the owner TU so tests exercise its real private callbacks. */
#include <kunit/test.h>
#include <linux/kthread.h>

static void native_video_queue_bounds(struct kunit *test)
{
	struct mt6878_native_video *v = kunit_kzalloc(test, sizeof(*v), GFP_KERNEL);
	struct native_node *node;
	unsigned int sizes[1] = { 0 }, count = 8, planes = 0;

	KUNIT_ASSERT_NOT_NULL(test, v);
	node = &v->nodes[1];
	node->owner = v;
	node->index = 1;
	/* Explicit emitted DMA stride; not RAW10 wire length / four. */
	v->suppliers.layout.pdaf_layout.sizeimage = 3000000;
	KUNIT_EXPECT_EQ(test, queue_setup(&node->queue, &count, &planes, sizes, NULL), 0);
	KUNIT_EXPECT_EQ(test, count, 1U);
	KUNIT_EXPECT_EQ(test, planes, 1U);
	KUNIT_EXPECT_EQ(test, sizes[0], 3000000U);
	sizes[0]--;
	KUNIT_EXPECT_EQ(test, queue_setup(&node->queue, &count, &planes, sizes, NULL), -EINVAL);
	planes = 2;
	KUNIT_EXPECT_EQ(test, queue_setup(&node->queue, &count, &planes, sizes, NULL), -EINVAL);
}

static void native_video_quarantine_no_reentry(struct kunit *test)
{
	struct mt6878_native_video *v = kunit_kzalloc(test, sizeof(*v), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, v);
	v->quarantined = true;
	/* No initialized queue/work/PM fields: any hardware/cleanup reentry would
	 * fail this test rather than being represented by an always-success mock.
	 */
	KUNIT_EXPECT_EQ(test, retire(v), -EBUSY);
	KUNIT_EXPECT_FALSE(test, v->retired);
	KUNIT_EXPECT_FALSE(test, v->stopping);
	v->quarantined = false;
	v->retired = true;
	KUNIT_EXPECT_EQ(test, retire(v), 0);
}

static void native_video_register_reject(struct kunit *test)
{
	struct mt6878_native_video *owner = (void *)1;

	KUNIT_EXPECT_EQ(test, mt6878_native_video_register(NULL, &owner), -EINVAL);
	KUNIT_EXPECT_PTR_EQ(test, owner, NULL);
	KUNIT_EXPECT_EQ(test, mt6878_native_video_unregister(NULL), -EINVAL);
	KUNIT_EXPECT_EQ(test, mt6878_native_video_wait_ready(NULL, 1), -EINVAL);
}

static void native_video_registration_result(struct kunit *test)
{
	struct mt6878_native_video *v = kunit_kzalloc(test, sizeof(*v), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, v);
	mutex_init(&v->registration);
	init_completion(&v->registration_done);
	KUNIT_EXPECT_EQ(test, mt6878_native_video_wait_ready(v, 0), -EINVAL);
	KUNIT_EXPECT_EQ(test, mt6878_native_video_wait_ready(v, 1), -ETIMEDOUT);
	/* Registration failure is independent of a later frame/cleanup error.
	 * No subdevice/provider is mocked or marked hardware-ready in this test.
	 */
	v->registration_error = -ENOLINK;
	v->first_error = -EIO;
	complete_all(&v->registration_done);
	KUNIT_EXPECT_EQ(test, mt6878_native_video_wait_ready(v, 1), -ENOLINK);
}

static void native_video_preflight_reject(struct kunit *test)
{
	struct mt6878_native_video *v = kunit_kzalloc(test, sizeof(*v), GFP_KERNEL);
	struct vb2_v4l2_buffer buffer = { 0 };
	struct mt6878_camsv_buffer mapped = { 0 };

	KUNIT_ASSERT_NOT_NULL(test, v);
	KUNIT_EXPECT_EQ(test, preflight_buffer(v, NULL, 0, &mapped), -EINVAL);
	buffer.vb2_buf.vb2_queue = &v->nodes[0].queue;
	buffer.vb2_buf.num_planes = 1;
	buffer.vb2_buf.state = VB2_BUF_STATE_QUEUED;
	KUNIT_EXPECT_EQ(test, preflight_buffer(v, &buffer, 0, &mapped), -EINVAL);
	buffer.vb2_buf.state = VB2_BUF_STATE_ACTIVE;
	/* Wrong allocator / absent cookie must fail before interpreting mem_priv. */
	KUNIT_EXPECT_EQ(test, preflight_buffer(v, &buffer, 0, &mapped), -EINVAL);
	KUNIT_EXPECT_FALSE(test, v->capture.direct.pair.tx.hw_attempted);
}

static void native_video_partial_guard(struct kunit *test)
{
	struct mt6878_native_video *v = kunit_kzalloc(test, sizeof(*v), GFP_KERNEL);

	KUNIT_ASSERT_NOT_NULL(test, v);
	mutex_init(&v->registration);
	mutex_lock(&v->registration);
	/* No resources/allocator/provider: the genuinely empty state is safe. */
	KUNIT_EXPECT_EQ(test, retire_partial(v), 0);
	v->capture.controller.requested = 1;
	KUNIT_EXPECT_EQ(test, retire_partial(v), -EBUSY);
	v->capture.controller.requested = 0;
	v->capture.reset_attempted = true;
	KUNIT_EXPECT_EQ(test, retire_partial(v), -EBUSY);
	v->capture.reset_attempted = false;
	v->capture.direct.pair.tx.attempted = 1;
	KUNIT_EXPECT_EQ(test, retire_partial(v), -EBUSY);
	mutex_unlock(&v->registration);
}

/* These fixtures register real V4L2 devices and use actual device krefs.
 * No camera probe, provider, buffer allocation, PM or MMIO is performed.
 */
static struct mt6878_native_video *lifetime_root(struct kunit *test, unsigned int count)
{
	struct mt6878_native_video *v = kzalloc(sizeof(*v), GFP_KERNEL);
	unsigned int i;
	int ret;

	if (!v)
		return NULL;
	mutex_init(&v->registration);
	mutex_init(&v->capture.direct.lock);
	init_completion(&v->registration_done);
	strscpy(v->v4l2.name, "mt6878-video-lifetime", sizeof(v->v4l2.name));
	ret = v4l2_device_register(NULL, &v->v4l2);
	if (ret) {
		kfree(v);
		return NULL;
	}
	for (i = 0; i < count; i++) {
		struct native_node *node = &v->nodes[i];

		node->owner = v;
		node->index = i;
		node->queue.type = i ? V4L2_BUF_TYPE_META_CAPTURE : V4L2_BUF_TYPE_VIDEO_CAPTURE;
		node->queue.io_modes = VB2_MMAP;
		node->queue.lock = &v->capture.direct.lock;
		node->queue.ops = &queue_ops;
		node->queue.mem_ops = &vb2_dma_contig_memops;
		node->queue.buf_struct_size = sizeof(struct vb2_v4l2_buffer);
		ret = vb2_queue_init(&node->queue);
		if (ret)
			goto fail;
		node->vdev = (struct video_device) {
			.v4l2_dev = &v->v4l2, .fops = &file_ops,
			.release = video_final_release, .queue = &node->queue,
			.lock = &v->registration, .vfl_dir = VFL_DIR_RX,
			.device_caps = V4L2_CAP_STREAMING |
				(i ? V4L2_CAP_META_CAPTURE : V4L2_CAP_VIDEO_CAPTURE),
		};
		strscpy(node->vdev.name, "mt6878 lifetime fixture", sizeof(node->vdev.name));
		node->pad.flags = MEDIA_PAD_FL_SINK;
		ret = media_entity_pads_init(&node->vdev.entity, 1, &node->pad);
		if (ret) {
			vb2_queue_release(&node->queue);
			goto fail;
		}
		node->initialized = true;
		ret = register_node(node);
		if (ret)
			goto fail;
	}
	return v;
fail:
	KUNIT_FAIL(test, "actual V4L2 fixture registration failed: %d", ret);
	detach_nodes(v);
	if (!drain_nodes(v, msecs_to_jiffies(2000))) {
		cleanup_nodes(v);
		v4l2_device_unregister(&v->v4l2);
		kfree(v);
	} /* Failed drain deliberately retains callback storage. */
	return NULL;
}

static void lifetime_root_free(struct kunit *test, struct mt6878_native_video *v)
{
	int ret;

	detach_nodes(v);
	ret = drain_nodes(v, msecs_to_jiffies(2000));
	KUNIT_EXPECT_EQ(test, ret, 0);
	if (ret)
		return;
	cleanup_nodes(v);
	v4l2_device_unregister(&v->v4l2);
	kfree(v);
}

struct pending_open {
	struct native_node *node;
	struct completion entered, callback_done, allow_put;
	int result;
};

static int pending_open_thread(void *context)
{
	struct pending_open *open = context;

	complete(&open->entered);
	open->result = node_open(open->node, NULL);
	complete(&open->callback_done);
	wait_for_completion_timeout(&open->allow_put, msecs_to_jiffies(2000));
	put_device(&open->node->vdev.dev); /* Actual V4L2 open tail reference. */
	return 0;
}

static void native_video_pending_open_race(struct kunit *test)
{
	struct mt6878_native_video *v = lifetime_root(test, 2);
	struct pending_open open = { .result = -EINPROGRESS };
	struct task_struct *task;
	unsigned long done;

	KUNIT_ASSERT_NOT_NULL(test, v);
	open.node = &v->nodes[0];
	init_completion(&open.entered);
	init_completion(&open.callback_done);
	init_completion(&open.allow_put);
	mutex_lock(&v->registration);
	get_device(&open.node->vdev.dev); /* Same actual ref as core video_get. */
	task = kthread_run(pending_open_thread, &open, "mt6878-video-open-test");
	if (IS_ERR(task)) {
		put_device(&open.node->vdev.dev);
		mutex_unlock(&v->registration);
		KUNIT_FAIL(test, "pending-open thread creation failed");
		lifetime_root_free(test, v);
		return;
	}
	done = wait_for_completion_timeout(&open.entered, msecs_to_jiffies(1000));
	KUNIT_EXPECT_NE(test, done, 0UL);
	v->removing = true;
	detach_nodes(v);
	KUNIT_EXPECT_FALSE(test, completion_done(&open.node->released));
	KUNIT_EXPECT_EQ(test, v->opens, 0U);
	mutex_unlock(&v->registration);
	done = wait_for_completion_timeout(&open.callback_done, msecs_to_jiffies(1000));
	KUNIT_EXPECT_NE(test, done, 0UL);
	if (done)
		KUNIT_EXPECT_EQ(test, open.result, -ENODEV);
	KUNIT_EXPECT_EQ(test, drain_nodes(v, 1), -ETIMEDOUT);
	complete(&open.allow_put);
	kthread_stop(task);
	lifetime_root_free(test, v);
}

static void native_video_last_close_race(struct kunit *test)
{
	struct mt6878_native_video *v = lifetime_root(test, 2);
	struct v4l2_fh *fh;
	struct inode inode = { 0 };
	struct file file = { .f_inode = &inode };
	unsigned int i;

	KUNIT_ASSERT_NOT_NULL(test, v);
	fh = kzalloc(sizeof(*fh), GFP_KERNEL);
	if (!fh) {
		KUNIT_FAIL(test, "fh allocation failed");
		lifetime_root_free(test, v);
		return;
	}
	for (i = 0; i < 2; i++)
		get_device(&v->nodes[i].vdev.dev);
	v4l2_fh_init(fh, &v->nodes[0].vdev);
	v4l2_fh_add(fh, &file);
	file.private_data = fh;
	inode.i_rdev = MKDEV(VIDEO_MAJOR, v->nodes[0].vdev.minor);
	v->nodes[0].queue.owner = fh;
	v->opens = 1;
	v->retired = true; /* Post-retirement close: no hardware was created. */
	KUNIT_EXPECT_EQ(test, mt6878_native_video_unregister(v), -EBUSY);
	KUNIT_EXPECT_TRUE(test, v->nodes[0].registered);
	KUNIT_EXPECT_TRUE(test, v->nodes[1].registered);
	KUNIT_EXPECT_EQ(test, video_release(&file), 0); /* Actual native close callback. */
	KUNIT_EXPECT_EQ(test, v->opens, 0U);
	detach_nodes(v);
	KUNIT_EXPECT_EQ(test, drain_nodes(v, 1), -ETIMEDOUT);
	put_device(&v->nodes[0].vdev.dev); /* Core close tail, first node only. */
	KUNIT_EXPECT_TRUE(test, completion_done(&v->nodes[0].released));
	KUNIT_EXPECT_EQ(test, drain_nodes(v, 1), -ETIMEDOUT);
	put_device(&v->nodes[1].vdev.dev);
	lifetime_root_free(test, v);
}

static void native_video_partial_publication(struct kunit *test)
{
	struct mt6878_native_video *v = lifetime_root(test, 1);

	KUNIT_ASSERT_NOT_NULL(test, v);
	get_device(&v->nodes[0].vdev.dev);
	detach_nodes(v);
	KUNIT_EXPECT_FALSE(test, v->nodes[1].release_expected);
	KUNIT_EXPECT_EQ(test, drain_nodes(v, 1), -ETIMEDOUT);
	put_device(&v->nodes[0].vdev.dev);
	lifetime_root_free(test, v);
}

static struct kunit_case native_video_cases[] = {
	KUNIT_CASE(native_video_queue_bounds),
	KUNIT_CASE(native_video_quarantine_no_reentry),
	KUNIT_CASE(native_video_register_reject),
	KUNIT_CASE(native_video_registration_result),
	KUNIT_CASE(native_video_preflight_reject),
	KUNIT_CASE(native_video_partial_guard),
	KUNIT_CASE(native_video_pending_open_race),
	KUNIT_CASE(native_video_last_close_race),
	KUNIT_CASE(native_video_partial_publication),
	{}
};

static struct kunit_suite native_video_suite = {
	.name = "mt6878-native-video-lifetime",
	.test_cases = native_video_cases,
};
kunit_test_suite(native_video_suite);
