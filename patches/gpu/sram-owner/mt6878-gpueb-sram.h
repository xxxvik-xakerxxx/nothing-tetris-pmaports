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
 * read transactions are exposed: no raw mapping, reset, clear, upload or BOOT API.
 */
struct mt6878_gpueb_sram *mt6878_gpueb_sram_create(struct device *parent,
					       const struct resource *resource);
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
