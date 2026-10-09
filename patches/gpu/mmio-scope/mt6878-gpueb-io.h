/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_IO_H
#define MT6878_GPUEB_IO_H
#include "mt6878-gpueb-io-core.h"
struct platform_device;
struct mt6878_gpueb_adoption;
struct mt6878_gpueb_io;
/* Parent-only prepare: acquires BOTH parent-issued typed windows and four
 * exact named control resources. No register reads/writes, IRQ or power change.
 * Existing child adopters cannot coexist: duplicate leases fail closed.
 */
struct mt6878_gpueb_io *mt6878_gpueb_io_prepare(struct platform_device *parent,
					     struct mt6878_gpueb_adoption *owner);
/* Client/IRQ users acquire a reference before publishing an async pointer,
 * and release only after their callbacks/work are drained. get/put and bounded
 * transfers are IRQ-safe. Final pointer release is serialized by the parent.
 */
int mt6878_gpueb_io_get(struct mt6878_gpueb_io *scope);
int mt6878_gpueb_io_put(struct mt6878_gpueb_io *scope);
int mt6878_gpueb_io_tx(struct mt6878_gpueb_io *scope, const u32 *words, size_t count);
int mt6878_gpueb_io_rx(struct mt6878_gpueb_io *scope, u32 *words, size_t count);
int mt6878_gpueb_io_gpr_read(struct mt6878_gpueb_io *scope, u32 offset, u32 *value);
/* All hardware paths currently stop at power UNPROVEN. There is deliberately
 * no public activation setter, successful IO gate, or boot-ready callback.
 */
int mt6878_gpueb_io_request_irq(struct mt6878_gpueb_io *scope);
int mt6878_gpueb_io_quiesce(struct mt6878_gpueb_io *scope);
/* Process context only: latches scope error, then forwards quarantine to the
 * full SRAM parent. No OFF or freeing on a partial-start/fault assumption.
 */
int mt6878_gpueb_io_unknown_start(struct mt6878_gpueb_io *scope, int error);
int mt6878_gpueb_io_destroy(struct mt6878_gpueb_io *scope);
#endif
