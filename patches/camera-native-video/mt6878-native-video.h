/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_NATIVE_VIDEO_H
#define MT6878_NATIVE_VIDEO_H

#include "mt6878-native-capture.h"

struct mt6878_native_video;

/* Called by the bound, static platform resource owner, NOT from its probe.
 * Mapping and supplier devres remain owned until unregister returns zero.
 * No self-bound IOMMU device, guessed CAM_MAIN mapping or private firmware.
 */
struct mt6878_native_video_suppliers {
	struct platform_device *pdev;
	struct device *dma, *cam_main, *smi;
	struct fwnode_handle *receiver;
	void __iomem *cam_main_base;
	unsigned long cam_main_size;
	struct mt6878_camsv_job layout;
	struct mtkcam_ipi_config_param config;
	unsigned int port;
};

int mt6878_native_video_register(const struct mt6878_native_video_suppliers *suppliers,
	struct mt6878_native_video **result);
/* An error may return a non-NULL result if partial publication cannot drain.
 * That handle still owns its suppliers and must be passed to unregister.
 */
/* Observe actual notifier completion/error, bounded. Caller owns the handle
 * and serializes this call against unregister/free, like registration itself.
 * Timeout does not cancel notifier or release borrowed suppliers.
 */
int mt6878_native_video_wait_ready(struct mt6878_native_video *video,
	unsigned long timeout);
/* Zero consumes the handle only AFTER both actual video_device releases.
 * -EBUSY/timeout means keep the owner AND every supplier/mapping alive.
 * A ref-drain timeout (unlike HW quarantine) can be retried after callbacks end.
 * There is deliberately no void platform-remove/devm cleanup adapter.
 */
int mt6878_native_video_unregister(struct mt6878_native_video *video);

#endif
