/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_RESET_PROVIDER_H
#define MT6878_GPUEB_RESET_PROVIDER_H
struct platform_device;
struct mt6878_gpueb_sram;
struct mt6878_gpueb_reset_provider;

/* Called by the fixed parent after its real power owner is already active.
 * Successful publication lasts the whole boot: no unregister/discard API.
 * Parent teardown/overlays must not dismantle the retained supplier domain.
 */
struct mt6878_gpueb_reset_provider *mt6878_gpueb_reset_provider_register(
	struct platform_device *parent, struct mt6878_gpueb_sram *sram);

/* Future remoteproc .stop must propagate this result, never substitute zero.
 * Asserts the source-backed reset latch and drains owned Linux IRQ handlers.
 * No known OFF/AXI-idle producer exists: retains resources and returns -EBUSY
 * or the first actual failure. This is containment, not successful shutdown.
 */
int mt6878_gpueb_reset_provider_stop(struct mt6878_gpueb_reset_provider *provider);
#endif
