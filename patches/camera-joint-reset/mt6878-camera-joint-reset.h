/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_JOINT_RESET_H
#define MT6878_CAMERA_JOINT_RESET_H

#include "mt6878-camera-cold-reset.h"

struct mt6878_camera_joint_reset {
	bool attempted, completed, clamp_attempted;
	int first_error, lease_retire_error;
	struct mt6878_camera_cold_reset cold;
};

/* All entry points require persistent capture/transaction storage and parent
 * lifetime exclusion for the WHOLE call: prevent supplier unbind/unregister
 * and drain frame work before native retirement or storage destruction.
 * The temporary CAM_MAIN device pin is not a substitute for this ownership.
 * Negative READ_ONCE(bound) admission avoids an uninitialized owner mutex;
 * positive admission always requires protected native revalidation.
 */

/* One synchronous control-task transaction. Caller owns persistent native
 * capture storage/supplier PM leases, but must hold no queue/reset/core lock.
 * Requires the controller's actual prepared-and-disconnected STOPPED route;
 * never uses software stream masks alone or invents an initial route-off.
 * Error after clamp attempt retains native capture + SMI/DMA quarantine.
 */
int mt6878_camera_joint_reset(struct mt6878_camera_joint_reset *transaction,
	struct mt6878_native_capture *capture, const struct mt6878_camsv_job *layout);

/* Fresh native owner: real OFF-only cleanup precedes CAM_MAIN reset, then
 * ordinary frozen calibrated controller_prepare/submit/arm/stream sequence.
 * Transaction storage lives with capture, not on a worker stack; failure
 * retains its reservations and the existing native quarantine.
 */
int mt6878_camera_cold_frame(struct mt6878_camera_joint_reset *transaction,
	struct mt6878_native_capture *capture, struct vb2_v4l2_buffer *raw,
	struct vb2_v4l2_buffer *pdaf, const struct mt6878_camsv_job *layout,
	const struct mtkcam_ipi_config_param *config, unsigned int port,
	unsigned int pixel_mode);

/* Resource-only counterpart of native probe: no raw CAM_MAIN mapping input.
 * Actual clock provider supplies a synchronous regmap lease at frame time.
 */
int mt6878_camera_cold_probe(struct mt6878_native_capture *capture,
	struct platform_device *pdev, struct device *dma_owner, struct device *cam_main,
	struct device *smi, struct v4l2_subdev *receiver, struct v4l2_subdev *sensor,
	unsigned int sensor_pad);

#endif
