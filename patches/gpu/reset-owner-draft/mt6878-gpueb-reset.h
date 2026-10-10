/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_RESET_H
#define MT6878_GPUEB_RESET_H
struct platform_device;
struct mt6878_gpueb_sram;
struct mt6878_gpueb_reset;
/* Parent has an attached domain and a real, in-use runtime-PM reference.
 * This helper never powers/resumes a supplier and never registers a provider.
 * Caller serializes prepare/use/destroy and keeps the SRAM owner alive.
 */
struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(
	struct platform_device *parent, struct mt6878_gpueb_sram *sram);
/* Source-backed reset latch checkpoint only. Not DMA drain or physical OFF. */
int mt6878_gpueb_reset_hold(struct mt6878_gpueb_reset *scope);
/* Drains our disabled, exclusively claimed Linux IRQ. Never ACKs firmware bits. */
int mt6878_gpueb_reset_drain_irq(struct mt6878_gpueb_reset *scope);
/* After any reset write destroy refuses: full OFF remains unproven. */
int mt6878_gpueb_reset_destroy(struct mt6878_gpueb_reset *scope);
#endif
