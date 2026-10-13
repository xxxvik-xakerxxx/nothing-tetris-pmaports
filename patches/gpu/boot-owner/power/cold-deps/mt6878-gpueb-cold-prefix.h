/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_COLD_PREFIX_H
#define MT6878_GPUEB_COLD_PREFIX_H
struct device;
struct platform_device;
struct mt6878_gpueb_cold_prefix;
/* Native SCPSYS implementation, called only with the bound parent locked. */
int mt6878_cold_mfg0_preflight(struct device *dev);
int mt6878_cold_mfg0_readback(struct device *dev);
/* One fixed-parent control work item after binding, never probe/remove/PM/IRQ.
 * *result starts NULL and remains parent-owned for the whole diagnostic boot.
 * Non-NULL error result must be retained; no retry or forced detach/overlays.
 * Success is MFG0/SRAM acquisition ONLY. There is deliberately no continuation
 * to RPC, firmware install, PLL/rail programming, reset or BOOTREADY here.
 */
int mt6878_gpueb_cold_prefix_prepare(struct platform_device *parent,
		struct mt6878_gpueb_cold_prefix **result);
#endif
