/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_NATIVE_SMI_BACKEND_H
#define MT6878_CAMERA_NATIVE_SMI_BACKEND_H

#include "mt6878-camsv-hardware.h"

int mt6878_camsv_native_smi_backend(struct mt6878_camsv_hardware *hardware,
	struct mt6878_camsv_backend *backend);
int mt6878_camsv_native_cam_main_reset(struct mt6878_camsv_hardware *hardware);

#endif
