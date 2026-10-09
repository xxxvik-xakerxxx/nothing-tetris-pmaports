/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMSV_PLATFORM_H
#define MT6878_CAMSV_PLATFORM_H

#include <linux/completion.h>
#include <linux/atomic.h>
#include <linux/interrupt.h>
#include <linux/workqueue.h>
#include <media/v4l2-subdev.h>
#include "mt6878-camsv-direct.h"

struct mt6878_camsv_platform;
struct mt6878_camsv_platform_irq {
	struct mt6878_camsv_platform *platform;
	unsigned int index;
};

/* Parent capture controller owns storage and notifier-bound subdevices until
 * retire succeeds. No probe, PM callbacks, automatic DT or IRQ activation.
 */
struct mt6878_camsv_platform {
	struct mt6878_camsv_direct *direct;
	struct device *cam_main;
	struct v4l2_subdev *sensor, *receiver;
	struct media_pipeline pipeline;
	struct media_pad *origin;
	struct work_struct stop_work;
	struct completion stopped;
	struct mutex lifecycle;
	atomic_t stop_requested;
	struct mt6878_camsv_platform_irq lines[4];
	unsigned int requested, enabled;
	unsigned int status[4], channel_status;
	unsigned int last_tag, group_tags[4], tg_count;
	bool powered, drained, retired, media_owned;
	int stop_error;
};

/* Caller serializes controller lifecycle; sensor/receiver are bound by the
 * same native media owner. Validate their actual enabled link under graph lock.
 */
int mt6878_camsv_platform_bind(struct mt6878_camsv_platform *platform,
	struct mt6878_camsv_direct *direct, struct device *cam_main,
	struct v4l2_subdev *sensor, unsigned int source_pad,
	struct v4l2_subdev *receiver, unsigned int sink_pad);
int mt6878_camsv_platform_power_get(struct mt6878_camsv_platform *platform);
/* Only after real CAMSYS reset/route and direct submission prerequisites.
 * Does not fabricate the frozen backend's ROUTE, IRQ or STOPPED verification.
 */
int mt6878_camsv_platform_arm(struct mt6878_camsv_platform *platform);
/* Safe from a threaded IRQ: schedules task-context sensor/receiver stop and
 * IRQ drain. Never wait under direct.lock or from an IRQ callback.
 */
void mt6878_camsv_platform_stop_async(struct mt6878_camsv_platform *platform);
/* Controller only, outside queue lock; bounded wait, failure retains all refs.
 * The parent's hardware STOPPED verifier still must prove TG/VF/CAMMUX off.
 */
int mt6878_camsv_platform_retire(struct mt6878_camsv_platform *platform,
	unsigned long timeout_jiffies);

#endif
