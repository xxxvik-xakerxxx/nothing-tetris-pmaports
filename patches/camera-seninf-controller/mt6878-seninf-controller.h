/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_SENINF_CONTROLLER_H
#define MT6878_SENINF_CONTROLLER_H

#include <linux/clk.h>
#include <linux/regulator/consumer.h>
#include "mt6878-camsv-platform.h"
#include "mt6878-seninf-route.h"
#include "mt6878-seninf-events.h"

/* Embedded in the actual receiver; mappings/suppliers are borrowed from its
 * probe, not remapped by a second consumer. Keep devres/modules until retire.
 */
struct mt6878_seninf_controller {
	struct mutex core;
	struct platform_device *pdev;
	struct mt6878_camsv_platform *capture;
	struct mt6878_seninf_route route;
	void __iomem *base, *analog;
	struct clk_bulk_data *clocks;
	unsigned int num_clocks;
	u32 dvfs[7];
	struct device **domains;
	struct regulator *vcore;
	struct mt6878_route_plan allocation;
	unsigned long intfs, muxes, cammuxes;
	struct mt6878_seninf_transaction tsrec, events;
	struct mt6878_seninf_events observed;
	int irq, tsrec_irq;
	unsigned int requested;
	bool allocated, tsrec_disabled, irq_enabled, irq_drained;
	int first_error;
};

/* Call from native media owner, before first prepare; receiver already bound
 * to the capture pipeline. No clock/rail activation or MMIO at bind.
 */
int mt6878_seninf_controller_bind(struct mt6878_seninf_controller *c,
	struct platform_device *pdev, struct mt6878_camsv_platform *capture,
	void __iomem *base, void __iomem *analog, struct clk_bulk_data *clocks,
	unsigned int num_clocks, struct device **domains, struct regulator *vcore,
	struct clk *csi_clock, const struct v4l2_mbus_config_mipi_csi2 *endpoint,
	unsigned int sensor_pad);
int mt6878_seninf_controller_prepare(struct mt6878_seninf_controller *c,
	const struct mt6878_camsv_job *layout, unsigned int port, unsigned int pixel_mode);
/* CAMSV backend calls under direct queue lock, never acquires core/state.
 * STOPPED proves route/IRQ shutdown before reset, not post-reset quiescence.
 */
int mt6878_seninf_controller_gate(struct mt6878_seninf_controller *c,
	enum mt6878_camsv_owner gate, const struct mt6878_camsv_job *job);
/* Called via graph's native pad stream ops after direct CQ submit. */
int mt6878_seninf_controller_enable(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask);
int mt6878_seninf_controller_disable(struct v4l2_subdev *sd,
	struct v4l2_subdev_state *state, u32 pad, u64 mask);
/* Outside queue/core locks and IRQ context. Retains allocations on failure. */
int mt6878_seninf_controller_drain(struct mt6878_seninf_controller *c);
int mt6878_seninf_controller_release(struct mt6878_seninf_controller *c);

#endif
