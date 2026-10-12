/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_RESET_H
#define MT6878_GPUEB_RESET_H
#ifdef GPUEB_RESET_HOST_TEST
#include "mt6878-gpueb-sram-core.h"
#else
#include <linux/types.h>
#endif
struct device;
struct platform_device;
struct mt6878_gpueb_sram;
struct mt6878_gpueb_reset;
/* Require an available mediatek,gpueb node and all eight ee2 memory resources
 * without claiming or accessing them. No chip identity is inferred from the
 * generic compatible alone: endpoints and attached MFG0 profile remain required.
 * The bound parent calls this before its first runtime-PM resume.
 */
int mt6878_gpueb_reset_validate_resources(struct platform_device *parent);
/* Parent has an attached domain and a real, in-use runtime-PM reference.
 * This helper never powers/resumes a supplier and never registers a provider.
 * Caller serializes prepare/use/destroy and keeps the SRAM owner alive.
 */
struct mt6878_gpueb_reset *mt6878_gpueb_reset_prepare(
	struct platform_device *parent, struct mt6878_gpueb_sram *sram);
/* Source-backed reset latch checkpoint only. Not DMA drain or physical OFF. */
int mt6878_gpueb_reset_hold(struct mt6878_gpueb_reset *scope);
/* A fixed bound client is pinned until scope destruction. Callback runs in the
 * threaded IRQ, after payload snapshot and ACK; it must synchronously consume
 * the words and must not call reset/drain/destroy/bind on this scope. No async
 * use of the payload pointer. It must not acquire a parent/client lock that
 * a lifecycle caller holds while draining this IRQ. Channel 1 is GPUFREQ,
 * not a ready session. The consumer performs its actual response completion.
 * Binding does not enable the IRQ or authorize a firmware start.
 */
typedef void (*mt6878_gpueb_receive_t)(void *context, unsigned int channel,
		const u32 *words, unsigned int count);
int mt6878_gpueb_reset_bind_channel(struct mt6878_gpueb_reset *scope,
		struct device *client, unsigned int channel,
		mt6878_gpueb_receive_t receive, void *context);
/* Process context, one nonblocking full-slot submission by the pinned client.
 * Zero means doorbell submitted, NOT firmware ACK/command completion. Reply
 * channels remain in flight until an actual copied/ACKed RX callback returns.
 * No timeout/retry or caller readiness flag. The current candidate has no owned
 * IRQ activation transition: valid calls return -EOPNOTSUPP without MMIO.
 * Caller serializes final destruction and supplies stable words for this call;
 * callbacks must not send recursively or hold a lock a drain caller needs.
 */
int mt6878_gpueb_reset_trysend(struct mt6878_gpueb_reset *scope,
		struct device *client, unsigned int channel,
		const u32 *words, unsigned int count);
/* Irreversibly closes dispatch and drains handlers/callbacks before reset.
 * Linux quiescence never establishes DMA idle or physical OFF.
 */
int mt6878_gpueb_reset_drain_irq(struct mt6878_gpueb_reset *scope);
/* After any reset write destroy refuses: full OFF remains unproven. */
int mt6878_gpueb_reset_destroy(struct mt6878_gpueb_reset *scope);
#endif
