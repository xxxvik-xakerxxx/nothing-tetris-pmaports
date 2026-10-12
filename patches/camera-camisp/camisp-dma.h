/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMISP_DMA_H
#define MT6878_CAMISP_DMA_H

#include <linux/device.h>

/* Logical caller retains its real runtime-PM supplier reference. Parent must
 * exclude forced supplier withdrawal until consumer retirement completes.
 */
int mt6878_camisp_dma_idle(struct device *larb);

#endif
