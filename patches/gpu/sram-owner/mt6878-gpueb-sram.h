/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_SRAM_H
#define MT6878_GPUEB_SRAM_H
#include "mt6878-gpueb-sram-core.h"
struct device;
struct resource;
struct mt6878_gpueb_sram;
struct mt6878_gpueb_window;

/* Explicit lifetime, no devm or standalone platform driver. DT stays disabled.
 * Parent owns resources before any partial start. Typed leases and bounded
 * read/fixed-slot send transactions are exposed: no raw mapping, reset, clear,
 * arbitrary-offset write, firmware upload or BOOT API.
 */
struct mt6878_gpueb_sram *mt6878_gpueb_sram_create(struct device *parent,
					       const struct resource *resource);
/* Compare the retained actual parent, not a caller permission/physical address. */
int mt6878_gpueb_sram_check_parent(struct mt6878_gpueb_sram *sram, struct device *parent);
struct mt6878_gpueb_window *mt6878_gpueb_sram_get_window(
		struct mt6878_gpueb_sram *sram, enum gpueb_sram_window type);
int mt6878_gpueb_sram_describe(struct mt6878_gpueb_window *window,
		u64 offset, u64 size, struct gpueb_sram_range *range);
/* Process/threaded-IRQ context only. The synchronous callback borrows a
 * read-only accessor while the owner mutex excludes quarantine. It must not
 * retain the reader or call any other SRAM API. No mapping/write accessor.
 * Both typed leases must belong to this same owner. Caller also serializes
 * external mailbox controls and drains the IRQ before any future SRAM clear.
 */
struct mt6878_gpueb_reader;
int mt6878_gpueb_sram_read_transaction(struct mt6878_gpueb_window *gpr,
		struct mt6878_gpueb_window *mbox,
		int (*consume)(struct mt6878_gpueb_reader *, void *), void *context);
int mt6878_gpueb_sram_reader_words(struct mt6878_gpueb_reader *reader,
		enum gpueb_sram_window type, u64 offset, u32 *words, unsigned int count);
/* Only the controller holding BOTH exclusive leases may send. No mapping or
 * write accessor is returned. Exact full ee2 TX slot only; before/commit borrow
 * the read-only reader under the SRAM mutex and may not call other SRAM APIs.
 * before must reject an inactive owner/busy doorbell; commit orders and rings
 * the controller's already-owned doorbell. Any commit failure is post-write:
 * caller must preserve its first fault and quarantine, never retry this send.
 */
int mt6878_gpueb_sram_send_transaction(struct mt6878_gpueb_window *gpr,
		struct mt6878_gpueb_window *mbox, unsigned int channel,
		const u32 *words, unsigned int count,
		int (*before)(struct mt6878_gpueb_reader *, void *),
		int (*commit)(struct mt6878_gpueb_reader *, void *), void *context);
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
