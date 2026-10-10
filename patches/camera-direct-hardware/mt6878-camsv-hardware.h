/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMSV_HARDWARE_H
#define MT6878_CAMSV_HARDWARE_H

#include <linux/regmap.h>
#include "mt6878-camsv-platform.h"
#include "mt6878-seninf-phy.h"

/* Mappings/regmap belong to their existing native providers, not remapped
 * here. Parent capture controller holds provider lifetime and shared reset
 * serialization for the entire reset transaction, including failed reset.
 */
struct mt6878_camsv_hardware {
	struct mt6878_camsv_platform *platform;
	struct device *smi_device;
	struct regmap *smi_regmap;
	struct mutex *reset_lock;
	void __iomem *cam_main;
	unsigned long cam_main_size;
	void __iomem *seninf_base;
	unsigned long seninf_size;
};

int mt6878_camsv_hardware_backend(struct mt6878_camsv_hardware *hardware,
	struct mt6878_camsv_backend *backend);
int mt6878_camsv_cam_main_reset(struct mt6878_camsv_hardware *hardware);
int mt6878_camsv_tg_off(struct mt6878_camsv_hardware *hardware);
/* Reads matching receiver's cell and actual CSI clock. Does not supply module
 * timing/mode/trio values: these must come from negotiated IMX882 endpoint.
 */
int mt6878_seninf_calibration_read(struct device *receiver,
	struct clk *csi_clock, unsigned int port, struct mt6878_phy_inputs *inputs);

#endif
