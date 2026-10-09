/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMSV_DIRECT_H
#define MT6878_CAMSV_DIRECT_H

#include <linux/mutex.h>
#include <linux/dma-mapping.h>
#include "mt6878-camsv-vb2.h"
#include "mt6878-camera-camsv-recipe.h"

/* Restricted one-frame controller; queue and threaded IRQ operations share
 * lock. No daemon, RPMSG endpoint, new ioctl, probe or automatic activation.
 */
struct mt6878_camsv_direct {
	struct mutex lock;
	struct device *consumer, *dma_owner;
	struct mt6878_camsv_resources resources;
	struct mt6878_camsv_recipe_resources recipe_resources;
	struct mt6878_camsv_backend hardware, io;
	struct mt6878_camsv_vb2_pair pair;
	struct mt6878_camsv_job job;
	struct mtkcam_ipi_config_param config;
	struct mt6878_ccd_cq encoder; /* Existing kernel-compatible memory encoder. */
	void *cq_cpu;
	dma_addr_t cq_dma;
	unsigned int cq_capacity, descriptor_bytes, values_start;
	u64 completion_timestamp;
	bool completion_observed;
	int first_error;
};

int mt6878_camsv_direct_init(struct mt6878_camsv_direct *owner,
	struct platform_device *pdev, struct device *port_owner,
	const struct mt6878_camsv_backend *hardware);
/* Existing video consumer provides real vb2_ops; buffers include its own list
 * linkage if needed. Both queues use this lock, allocator and DMA memops.
 */
int mt6878_camsv_direct_queue_init(struct mt6878_camsv_direct *owner,
	struct vb2_queue *queue, const struct vb2_ops *ops,
	enum v4l2_buf_type type, unsigned int buffer_bytes);

/* Caller holds lock, both queues own ACTIVE buffers. Config/layouts come
 * from negotiated sensor/receiver state; raw/pdaf/cq addresses are replaced
 * with actual vb2/coherent DMA addresses. No inferred PDAF byte ratio.
 */
int mt6878_camsv_direct_submit(struct mt6878_camsv_direct *owner,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	const struct mt6878_camsv_job *layout,
	const struct mtkcam_ipi_config_param *config);
/* Threaded DONE consumer only after real IRQ/power ownership. Reads exact
 * vendor status order. Return 1 records full tag completion, NOT buffer return.
 * Native consumer stops sensor/route/TG/VF and drains IRQ outside this mutex,
 * then calls stop under lock. No guessed W1C write or IRQ-side reset.
 */
int mt6878_camsv_direct_done(struct mt6878_camsv_direct *owner);
/* Controller-task only, never from the IRQ thread. Drain owned IRQs outside
 * lock before calling; the backend must verify actual STOPPED ownership.
 * Returns DONE for a fully completed, error-free frame only after reset has
 * proved quiescence; otherwise ERROR or retains buffers/CQ on failed stop.
 */
int mt6878_camsv_direct_stop(struct mt6878_camsv_direct *owner);
/* Refuses release after ANY MMIO attempt without tx.quiesced. Keep driver,
 * queues, suppliers, devres, clocks/IRQ and context alive on failure.
 */
int mt6878_camsv_direct_release(struct mt6878_camsv_direct *owner);

#endif
