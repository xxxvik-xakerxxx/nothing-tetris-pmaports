/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_SENINF_ROUTE_H
#define MT6878_SENINF_ROUTE_H

#include <media/v4l2-subdev.h>
#include "mt6878-camsv-direct.h"
#include "mt6878-seninf-phy.h"
#include "mt6878-seninf-route-program.h"

/* Embedded in the native receiver/controller, not a new platform driver.
 * Parent owns lifetime, core/page mutex, PM/clock refs, IRQ/TSREC providers
 * and exclusive allocated muxes. Never replace registered subdev ops live.
 */
struct mt6878_seninf_route {
	struct mutex *core_lock;
	struct v4l2_subdev *sensor, *receiver;
	unsigned int sensor_pad;
	struct clk *csi_clock;
	struct v4l2_mbus_config_mipi_csi2 endpoint;
	struct mt6878_phy_backend backend;
	struct mt6878_phy_transaction phy;
	struct mt6878_route_transaction route;
	bool source_attempted, source_stopped;
	int first_error;
};

/* All calls hold core_lock. prepare stops the real sensor, validates its
 * negotiated descriptor/endpoint, reads calibration and runs PHY/VC/CAMMUX.
 * Existing PHY provider checks are mandatory before the first write.
 */
int mt6878_seninf_route_prepare(struct mt6878_seninf_route *route,
	const struct mt6878_route_plan *plan);
/* Also hold direct.lock. Sensor starts only after actual CQ submit. */
int mt6878_seninf_route_source_on(struct mt6878_seninf_route *route,
	struct mt6878_camsv_direct *capture);
/* Native receiver s_stream(0) target: stop sensor/disconnect route, NOT DMA
 * retirement. On failure retain PHY/power/resources; do not return buffers.
 */
int mt6878_seninf_route_source_off(struct mt6878_seninf_route *route);
/* Control task, after CAMSV reset and IRQ drain; never IRQ callback. */
int mt6878_seninf_route_retire(struct mt6878_seninf_route *route,
	struct mt6878_camsv_direct *capture);
/* Read cached successful programming, no receiver MMIO during gate checks. */
int mt6878_seninf_route_matches(struct mt6878_seninf_route *route,
	const struct mt6878_camsv_job *job);

#endif
