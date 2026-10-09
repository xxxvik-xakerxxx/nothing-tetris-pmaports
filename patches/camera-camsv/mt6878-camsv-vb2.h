/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMSV_VB2_H
#define MT6878_CAMSV_VB2_H

#include <linux/iommu.h>
#include <linux/clk.h>
#include <linux/platform_device.h>
#include <media/videobuf2-dma-contig.h>
#include <media/videobuf2-v4l2.h>
#include "mt6878-camsv-capture.h"

/* Owned by a future capture/video-device driver, not registered here.
 * RAW10 video and PDAF metadata use separate queues, never a fabricated
 * two-plane Bayer format. Call under the capture owner's queue mutex;
 * IRQ completion/stop must be serialized with buffer removal.
 */
struct mt6878_camsv_vb2_pair {
	struct vb2_v4l2_buffer *raw, *pdaf;
	struct mt6878_camsv_transaction tx;
	unsigned int completed;
};

struct mt6878_camsv_resources {
	void __iomem *banks[6];
	int irqs[4];
	struct clk_bulk_data clocks[8];
	struct device *port_owner; /* Port supplier, not necessarily the allocator. */
	struct iommu_domain *domain;
	unsigned int sv_id;
};

/* Resource-only acquisition; no clock/power enable or IRQ registration. */
int mt6878_camsv_get_resources(struct platform_device *pdev,
	struct device *port_owner, struct mt6878_camsv_resources *resources);

int mt6878_camsv_vb2_submit(struct mt6878_camsv_vb2_pair *pair,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	struct device *dma_owner, struct iommu_domain *verified_domain,
	const struct mt6878_camsv_backend *io, const struct mt6878_camsv_job *job);
int mt6878_camsv_vb2_done(struct mt6878_camsv_vb2_pair *pair,
	unsigned int status, unsigned int inner_sequence, u64 timestamp_ns);
int mt6878_camsv_vb2_stop(struct mt6878_camsv_vb2_pair *pair,
	const struct mt6878_camsv_backend *io);

#endif
