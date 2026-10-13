/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_DRAM_H
#define MT6878_GPUEB_DRAM_H

#ifndef GPUEB_DRAM_HOST_TEST
#include <linux/types.h>
#endif

struct device;
struct mt6878_gpueb_dram;
struct mt6878_gpueb_dram_loan;

/* Built-in staging APIs only. No module registration or hardware publication.
 * The candidate GPR6 word is a physical address, NOT a DMA/IOMMU handle or a
 * secure permission. No CPU mapping or caller-supplied contents are exposed.
 */
/* *result must initially be NULL. On an allocator-release inconsistency it
 * receives the retained, faulted handle even though create returns -EIO.
 * That handle rejects loans; destroy is its only private cleanup operation.
 */
int mt6878_gpueb_dram_create(struct device *parent, struct mt6878_gpueb_dram **result);
struct mt6878_gpueb_dram_loan *mt6878_gpueb_dram_acquire(
		struct mt6878_gpueb_dram *dram, struct device *parent);
int mt6878_gpueb_dram_candidate_gpr6(struct mt6878_gpueb_dram_loan *loan, u32 *word);
void mt6878_gpueb_dram_put(struct mt6878_gpueb_dram_loan *loan);
int mt6878_gpueb_dram_destroy(struct mt6878_gpueb_dram *dram);

#endif
