/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_COLD_RESET_H
#define MT6878_CAMERA_COLD_RESET_H

#include "mt6878-native-capture.h"

struct mt6878_camera_cold_reset {
	struct mt6878_seninf_controller *controller;
	struct mt6878_route_plan plan;
	struct mt6878_seninf_transaction off, tsrec;
	bool attempted, allocated, sensor_cleaned, irq_drained, disconnected;
	int first_error;
};

/* Caller holds native lock + lifecycle, but NOT core/queue/subdev-state locks.
 * Only owns reserved initially-INACTIVE endpoints: never steals a live route.
 * No PHY ON/setup, no forged frozen route transaction or readiness fields.
 */
int mt6878_camera_cold_prepare(struct mt6878_camera_cold_reset *cold,
	struct mt6878_native_capture *capture, const struct mt6878_camsv_job *layout,
	unsigned int port, unsigned int pixel_mode);
/* Caller holds native/lifecycle + controller core. Rechecks actual readbacks. */
int mt6878_camera_cold_verify(struct mt6878_camera_cold_reset *cold,
	struct mt6878_native_capture *capture, const struct mt6878_camsv_job *layout);
/* After successful joint reset + mapping-lease retirement, native lock held. */
int mt6878_camera_cold_release(struct mt6878_camera_cold_reset *cold,
	struct mt6878_native_capture *capture);

#endif
