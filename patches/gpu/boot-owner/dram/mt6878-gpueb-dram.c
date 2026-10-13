// SPDX-License-Identifier: GPL-2.0-only
#ifdef GPUEB_DRAM_HOST_TEST
#include "dram-host.h"
#else
#include <linux/cma.h>
#include <linux/device.h>
#include <linux/dma-map-ops.h>
#include <linux/err.h>
#include <linux/mm.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#endif
#include "mt6878-gpueb-dram.h"

#define GPUEB_DRAM_BYTES 0x600000UL
#define GPUEB_DRAM_ALIGN 0x10000UL
#define GPUEB_DRAM_MIN 0x40000000ULL
#define GPUEB_DRAM_LIMIT 0x80000000ULL
#define GPUEB_DRAM_PAGES (GPUEB_DRAM_BYTES / PAGE_SIZE)

struct mt6878_gpueb_dram {
	struct device *parent;
	struct cma *area;
	struct page *pages;
	struct mutex lock;
	phys_addr_t physical;
	struct mt6878_gpueb_dram_loan *loan;
	int first_error;
};

struct mt6878_gpueb_dram_loan {
	struct mt6878_gpueb_dram *dram;
};

/* The bounds select the actual low-memory LK route, not its unused >4GB arm.
 * Recheck physical alignment/range independently of CMA bitmap geometry.
 */
static int validate_allocation(phys_addr_t physical)
{
	if (physical < GPUEB_DRAM_MIN ||
	    physical > GPUEB_DRAM_LIMIT - GPUEB_DRAM_BYTES ||
	    (physical & (GPUEB_DRAM_ALIGN - 1)))
		return -ERANGE;
	return 0;
}

int mt6878_gpueb_dram_create(struct device *parent, struct mt6878_gpueb_dram **result)
{
	struct mt6878_gpueb_dram *dram;
	unsigned int alignment = 0;
	int ret;

	if (!parent || !result || *result)
		return -EINVAL;
	if (PAGE_SIZE > GPUEB_DRAM_ALIGN || GPUEB_DRAM_BYTES % PAGE_SIZE)
		return -EOPNOTSUPP;
	dram = kzalloc(sizeof(*dram), GFP_KERNEL);
	if (!dram)
		return -ENOMEM;
	mutex_init(&dram->lock);
	dram->parent = get_device(parent);
	dram->area = dev_get_cma_area(parent);
	if (!dram->area) {
		ret = -ENODEV;
		goto free;
	}
	while ((PAGE_SIZE << alignment) < GPUEB_DRAM_ALIGN)
		alignment++;
	/* Unlike a six-MiB buddy allocation, this does not need order 11 when
	 * the packaged ARM64 kernel limits buddy orders to 10. No retry loop or
	 * fallback to scattered pages / a different source address is permitted.
	 */
	dram->pages = cma_alloc(dram->area, GPUEB_DRAM_PAGES, alignment, false);
	if (!dram->pages) {
		ret = -ENOMEM;
		goto free;
	}
	dram->physical = page_to_phys(dram->pages);
	ret = validate_allocation(dram->physical);
	if (ret) {
		/* No address has escaped or been published. Release the actual area
		 * used for allocation, not a potentially changed device CMA selector.
		 */
		if (!cma_release(dram->area, dram->pages, GPUEB_DRAM_PAGES)) {
			dram->first_error = ret;
			*result = dram;
			return -EIO;
		}
		goto free;
	}
	*result = dram;
	return 0;
free:
	put_device(dram->parent);
	kfree(dram);
	return ret;
}

struct mt6878_gpueb_dram_loan *mt6878_gpueb_dram_acquire(
		struct mt6878_gpueb_dram *dram, struct device *parent)
{
	struct mt6878_gpueb_dram_loan *loan = NULL;
	int ret;

	if (IS_ERR_OR_NULL(dram) || !parent)
		return ERR_PTR(-EINVAL);
	mutex_lock(&dram->lock);
	if (dram->first_error)
		ret = dram->first_error;
	else if (parent != dram->parent)
		ret = -ENODEV;
	else if (dram->loan)
		ret = -EBUSY;
	else if (page_to_phys(dram->pages) != dram->physical)
		ret = -ESTALE;
	else
		ret = validate_allocation(page_to_phys(dram->pages));
	if (!ret) {
		loan = kzalloc(sizeof(*loan), GFP_KERNEL);
		if (!loan)
			ret = -ENOMEM;
		else {
			loan->dram = dram;
			dram->loan = loan;
		}
	}
	mutex_unlock(&dram->lock);
	return ret ? ERR_PTR(ret) : loan;
}

int mt6878_gpueb_dram_candidate_gpr6(struct mt6878_gpueb_dram_loan *loan, u32 *word)
{
	struct mt6878_gpueb_dram *dram;
	int ret;

	if (IS_ERR_OR_NULL(loan) || !word)
		return -EINVAL;
	dram = loan->dram;
	mutex_lock(&dram->lock);
	ret = dram->loan != loan ? -ENODEV :
		page_to_phys(dram->pages) != dram->physical ? -ESTALE :
		validate_allocation(dram->physical);
	if (!ret)
		*word = dram->physical >> 12;
	mutex_unlock(&dram->lock);
	return ret;
}

void mt6878_gpueb_dram_put(struct mt6878_gpueb_dram_loan *loan)
{
	struct mt6878_gpueb_dram *dram;

	if (IS_ERR_OR_NULL(loan))
		return;
	dram = loan->dram;
	mutex_lock(&dram->lock);
	dram->loan = NULL;
	mutex_unlock(&dram->lock);
	kfree(loan);
}

int mt6878_gpueb_dram_destroy(struct mt6878_gpueb_dram *dram)
{
	int ret = 0;

	if (IS_ERR_OR_NULL(dram))
		return -EINVAL;
	mutex_lock(&dram->lock);
	if (dram->loan)
		ret = -EBUSY;
	else if (!cma_release(dram->area, dram->pages, GPUEB_DRAM_PAGES)) {
		if (!dram->first_error)
			dram->first_error = -EIO;
		ret = -EIO;
	}
	mutex_unlock(&dram->lock);
	if (ret)
		return ret;
	put_device(dram->parent);
	kfree(dram);
	return 0;
}

/* No EXPORT_SYMBOL: pinned cma_alloc/cma_release are built-in kernel APIs,
 * not module exports. This source has NO shipping or reset/GPR call site.
 * No workspace bytes are initialized here: the algorithm is not resolved.
 * Before any future hardware publication, the real owner must retain the
 * loan through retirement, close cache/secure visibility, and supply genuine
 * region-12 protection. Dropping a loan is never an OFF or DMA-idle proof.
 * Parent must serialize handle destruction, as with the SRAM/reset owners.
 */
