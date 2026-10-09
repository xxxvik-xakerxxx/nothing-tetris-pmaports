/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_CAMERA_PIPELINE_OWNER_H
#define MT6878_CAMERA_PIPELINE_OWNER_H

#include <linux/dma-buf.h>
#include <linux/iosys-map.h>
#include <linux/sched.h>
#include <media/v4l2-subdev.h>
#include "mt6878-camera-ccd-owner.h"
#include "mt6878-camera-capture-owner.h"
#include "mt6878-camera-camsv-recipe.h"

struct mt6878_pipeline_mapping {
	struct dma_buf *buffer;
	struct dma_buf_attachment *attachment;
	struct sg_table *sgt;
	struct iosys_map va;
	struct mt6878_camsv_buffer range;
	bool cpu_active, vmap_acquired;
};

struct mt6878_pipeline_owner {
	struct mutex lock;
	struct task_struct *consumer;
	struct device *dma_owner;
	struct iommu_domain *domain;
	struct mt6878_pipeline_mapping work, message;
	struct mt6878_camera_ccd_owner ccd;
	struct mt6878_camera_capture_owner *capture;
	struct v4l2_subdev *sensor, *receiver;
	unsigned int sensor_pad, width, height;
	struct mt6878_camsv_job job;
	struct rpmsg_endpoint *endpoint;
	spinlock_t callback_lock;
	unsigned int callback_users;
	bool callback_closed;
	bool published, callbacks_detached;
	int first_error;
};

/* Real dma-buf attachment to the actual CAMSV DMA owner, never sg_phys(). */
int mt6878_pipeline_map(struct mt6878_pipeline_mapping *mapping,
	struct dma_buf *buffer, struct device *device, unsigned int minimum);
void mt6878_pipeline_unmap(struct mt6878_pipeline_mapping *mapping);
int mt6878_pipeline_init(struct mt6878_pipeline_owner *owner,
	struct device *dma_owner, struct iommu_domain *domain, unsigned int session);
/* Invoke from the registered CCD consumer's ioctl task; no remote fd install. */
int mt6878_pipeline_import(struct mt6878_pipeline_owner *owner, int work_fd, int message_fd);
int mt6878_pipeline_export(struct mt6878_pipeline_owner *owner, bool message);
/* Bus driver serializes client->ept and remove across all owner operations. */
int mt6878_pipeline_endpoint(struct mt6878_pipeline_owner *owner, struct rpmsg_device *client);
int mt6878_pipeline_bind(struct mt6878_pipeline_owner *owner,
	struct v4l2_subdev *sensor, unsigned int sensor_pad,
	struct v4l2_subdev *receiver, struct mt6878_camera_capture_owner *capture);
int mt6878_pipeline_publish(struct mt6878_pipeline_owner *owner,
	const struct mtkcam_ipi_config_param *config, const struct mt6878_camsv_job *job,
	const struct mt6878_camsv_recipe_resources *resources, int work_fd, int message_fd,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf);
/* Compose/validate transport reply only, never submit CAMSV DMA on an ACK. */
int mt6878_pipeline_compose(struct mt6878_pipeline_owner *owner,
	unsigned int timeout_ms, struct mt6878_camsv_buffer *cq);
int mt6878_pipeline_rx(struct rpmsg_device *client, void *data, int length, void *priv, u32 src);
/* Bounded logical gate/drain. Endpoint/owner remain pinned even after success. */
int mt6878_pipeline_close_callback_gate(struct mt6878_pipeline_owner *owner);
/* Concrete callback exclusion; no endpoint destruction or guessed DMA idle. */
int mt6878_pipeline_detach_callbacks(struct mt6878_pipeline_owner *owner);
int mt6878_pipeline_release(struct mt6878_pipeline_owner *owner);
/* No runtime activation provider exists in this compile-only candidate. */
int mt6878_pipeline_start(struct mt6878_pipeline_owner *owner);

#endif
