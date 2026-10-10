/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAM_MAIN_LEASE_H
#define MT6878_CAM_MAIN_LEASE_H

#include <linux/device.h>
#include <linux/regmap.h>

struct mt6878_cam_main_lease;

/* Synchronous control-task lease, NOT an asynchronous capture/DMA lease.
 * Prepare holds supplier device_lock until retire; all calls on one task.
 * Do not call under a queue/reset lock or inside IRQ/PM/provider callbacks.
 * Never retain the returned regmap beyond retire, or pass it to a worker.
 */
int mt6878_cam_main_prepare(struct device *supplier,
	struct mt6878_cam_main_lease **result);
struct regmap *mt6878_cam_main_regmap(struct mt6878_cam_main_lease *lease);
int mt6878_cam_main_retire(struct mt6878_cam_main_lease **lease);

/* Unavailable until joint SMI clamp + SCQ/route-off ownership is provable.
 * A mapping/PM lease alone is deliberately insufficient for shared reset.
 */
int mt6878_cam_main_reset_pulse(struct mt6878_cam_main_lease *lease,
	unsigned int sv_id);

#endif
