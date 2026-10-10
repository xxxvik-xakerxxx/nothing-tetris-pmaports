// SPDX-License-Identifier: GPL-2.0-only
#include <soc/mediatek/smi-camera-reset.h>
#include <linux/iopoll.h>
#include "smi-backend.h"

static int native_smi_clamp(void *context, unsigned int common, unsigned int enable)
{
	struct mt6878_camsv_hardware *h = context;

	if (common != 31 || enable > 1 || !h->smi_device || !h->reset_lock ||
	    !h->platform->direct)
		return -EINVAL;
	lockdep_assert_held(h->reset_lock);
	return mtk_smi_camera_reset_clamp(h->smi_device,
		h->platform->direct->consumer, enable);
}

int mt6878_camsv_native_smi_backend(struct mt6878_camsv_hardware *h,
	struct mt6878_camsv_backend *backend)
{
	int ret = mt6878_camsv_hardware_backend(h, backend);

	if (ret)
		return ret;
	backend->smi_clamp = native_smi_clamp;
	return 0;
}

int mt6878_camsv_native_cam_main_reset(struct mt6878_camsv_hardware *h)
{
	struct mt6878_camsv_backend backend;
	struct mt6878_camsv_job job = { 0 };
	struct mt6878_camsv_direct *d;
	void __iomem *cq;
	u32 value;
	int ret;

	ret = mt6878_camsv_native_smi_backend(h, &backend);
	if (ret)
		return ret;
	if (!h->reset_lock || !h->cam_main || h->cam_main_size < 0x5c || !h->platform->direct)
		return -EINVAL;
	lockdep_assert_held(h->reset_lock);
	d = h->platform->direct;
	if (h->platform->enabled || d->pair.tx.hw_attempted)
		return -EBUSY;
	job.sv_id = d->resources.sv_id;
	ret = backend.verify(h, MT6878_SV_RESOURCES, &job);
	if (!ret)
		ret = native_smi_clamp(h, 31, 1);
	if (ret)
		return ret;
	/* e96 sv_reset_by_camsys_top: same sequence, native SMI lease replaces
	 * vendor's global void debug dispatcher. Timeout keeps lease and clamp.
	 */
	cq = d->resources.banks[2];
	writel(0, cq + SV_CQ_RESET);
	writel(1, cq + SV_CQ_RESET);
	wmb(); /* Commit SCQ reset before the documented bit1 ready poll. */
	ret = readl_poll_timeout(cq + SV_CQ_RESET, value, value & BIT(1), 1, 100000);
	if (ret)
		return ret;
	writel(0, cq + SV_CQ_RESET);
	writel(0, h->cam_main + 0x58);
	writel(3U << (job.sv_id * 2), h->cam_main + 0x58);
	writel(0, h->cam_main + 0x58);
	wmb(); /* Commit CAM_MAIN pulse before releasing the common clamp. */
	return native_smi_clamp(h, 31, 0);
}
