// SPDX-License-Identifier: GPL-2.0-only
#include <linux/pm_runtime.h>
#include "mt6878-camera-joint-reset.h"

/* Same real resource/bind/unwind APIs as frozen native_capture_probe, without
 * its raw CAM_MAIN mapping contract. CAM_MAIN is leased by cold_frame only.
 */
int mt6878_camera_cold_probe(struct mt6878_native_capture *n,
	struct platform_device *pdev, struct device *dma_owner, struct device *cam_main,
	struct device *smi, struct v4l2_subdev *receiver, struct v4l2_subdev *sensor,
	unsigned int sensor_pad)
{
	struct mt6878_camsv_backend backend;
	int ret, cleanup;

	if (!n || !pdev || !dma_owner || !cam_main || !smi || !receiver || !sensor ||
	    !receiver->dev || !sensor->dev || n->bound || receiver == sensor)
		return -EINVAL;
	if (!device_is_bound(dma_owner) || !device_is_bound(cam_main) ||
	    !device_is_bound(smi) || !pm_runtime_enabled(receiver->dev) ||
	    !pm_runtime_enabled(cam_main) || !pm_runtime_enabled(&pdev->dev) ||
	    !pm_runtime_enabled(smi))
		return -EPROBE_DEFER;
	mutex_init(&n->lock);
	mutex_init(&n->reset_lock);
	n->hardware = (struct mt6878_camsv_hardware) {
		.platform = &n->platform, .smi_device = smi, .reset_lock = &n->reset_lock,
		.seninf_base = mt6878_seninf_native_base(receiver), .seninf_size = 0x18000,
	};
	ret = mt6878_camsv_native_smi_backend(&n->hardware, &backend);
	if (ret)
		return ret;
	ret = mt6878_camsv_direct_init(&n->direct, pdev, dma_owner, &backend);
	if (ret)
		return ret;
	ret = mt6878_camsv_platform_bind(&n->platform, &n->direct, cam_main,
		sensor, sensor_pad, receiver, 0);
	if (ret)
		goto release_direct;
	ret = mt6878_seninf_native_bind(&n->controller, &n->platform);
	if (ret) {
		cleanup = mt6878_camsv_platform_retire(&n->platform, msecs_to_jiffies(1000));
		if (cleanup) {
			n->first_error = ret;
			return cleanup; /* Owner retains live storage/work/suppliers. */
		}
		goto release_direct;
	}
	n->smi = get_device(smi);
	n->platform.native_capture = n;
	n->bound = true;
	return 0;
release_direct:
	mutex_lock(&n->direct.lock);
	cleanup = mt6878_camsv_direct_release(&n->direct);
	mutex_unlock(&n->direct.lock);
	return cleanup ? cleanup : ret;
}
