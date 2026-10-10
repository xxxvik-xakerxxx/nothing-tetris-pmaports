/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_NATIVE_CAPTURE_H
#define MT6878_NATIVE_CAPTURE_H

#include "mt6878-seninf-controller.h"
#include "smi-backend.h"

/* Lifetime is the native video driver's, never IRQ/work-stack storage.
 * Probe/bind is resource-only. Failed retirement forbids supplier/devres free.
 */
struct mt6878_native_capture {
	struct mutex lock, reset_lock;
	struct mt6878_camsv_direct direct;
	struct mt6878_camsv_platform platform;
	struct mt6878_camsv_hardware hardware;
	struct mt6878_seninf_controller controller;
	struct device *smi;
	bool receiver_ref, smi_ref, bound, abort_attempted;
	bool reset_attempted, reset_completed;
	int abort_error, first_error;
};

/* Implemented by new graph overlay using actual private receiver resources. */
int mt6878_seninf_native_bind(struct mt6878_seninf_controller *controller,
	struct mt6878_camsv_platform *capture);
void __iomem *mt6878_seninf_native_base(struct v4l2_subdev *receiver);

int mt6878_native_capture_probe(struct mt6878_native_capture *capture,
	struct platform_device *pdev, struct device *dma_owner, struct device *cam_main,
	struct device *smi, struct v4l2_subdev *receiver, struct v4l2_subdev *sensor,
	unsigned int sensor_pad, void __iomem *cam_main_base, unsigned long cam_main_size);
int mt6878_native_capture_frame(struct mt6878_native_capture *capture,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	const struct mt6878_camsv_job *layout, const struct mtkcam_ipi_config_param *config,
	unsigned int port, unsigned int pixel_mode);
/* Existing stop worker calls this under its lifecycle mutex, outside queue. */
int mt6878_native_capture_receiver_stop(struct mt6878_camsv_platform *platform);
int mt6878_native_capture_retire(struct mt6878_native_capture *capture,
	unsigned long timeout);

#endif
