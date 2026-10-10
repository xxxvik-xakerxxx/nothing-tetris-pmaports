/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_CONTROL_H
#define MT6878_GPUEB_CONTROL_H
struct platform_device;
struct mt6878_gpueb_control;
/* Fixed bound parent's single serialized control task, never its probe/remove
 * or PM callback. *result must be NULL initially and stored by the parent for
 * the whole boot. All work completes on this task; no lock survives return.
 * Non-NULL result on error is quarantined, not permission to free/retry.
 * Forced unregistration, domain detachment and DT overlays are prohibited.
 * Successful result means resource/provider registration ONLY, not boot/OFF.
 */
int mt6878_gpueb_control_prepare(struct platform_device *parent,
	struct mt6878_gpueb_control **result);
#endif
