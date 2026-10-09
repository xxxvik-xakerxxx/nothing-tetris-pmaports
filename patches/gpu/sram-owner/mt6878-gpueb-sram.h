/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_SRAM_H
#define MT6878_GPUEB_SRAM_H
#include "mt6878-gpueb-sram-core.h"
struct device;
struct resource;
struct mt6878_gpueb_sram;
struct mt6878_gpueb_window;

/* Explicit lifetime, no devm or standalone platform driver. DT stays disabled.
 * Parent owns resources before any partial start. Only metadata leases are
 * exposed: NO raw mapping, MMIO access, reset, clear, upload or BOOT API yet.
 */
struct mt6878_gpueb_sram *mt6878_gpueb_sram_create(struct device *parent,
					       const struct resource *resource);
struct mt6878_gpueb_window *mt6878_gpueb_sram_get_window(
		struct mt6878_gpueb_sram *sram, enum gpueb_sram_window type);
int mt6878_gpueb_sram_describe(struct mt6878_gpueb_window *window,
		u64 offset, u64 size, struct gpueb_sram_range *range);
void mt6878_gpueb_sram_put_window(struct mt6878_gpueb_window *window);
/* Call BEFORE entering any future start procedure; irreversible until OFF is
 * independently proven by a future backend. Safe even on failed rproc_boot.
 */
int mt6878_gpueb_sram_unknown_start(struct mt6878_gpueb_sram *sram);
/* -EBUSY keeps claim, mapping and parent reference intact. Successful destroy
 * consumes the handle. Caller serializes destroy against new get/other calls;
 * a live window itself prevents destruction. Never free on failed destroy.
 */
int mt6878_gpueb_sram_destroy(struct mt6878_gpueb_sram *sram);
#endif
