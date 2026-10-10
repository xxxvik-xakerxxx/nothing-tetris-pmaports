// SPDX-License-Identifier: GPL-2.0-only
#include <linux/clk-provider.h>
#include <linux/delay.h>
#include <linux/iopoll.h>
#include <linux/irq.h>
#include <linux/nvmem-consumer.h>
#include <linux/pm_runtime.h>
#include <linux/property.h>
#include <linux/slab.h>
#include <linux/unaligned.h>
#include "mt6878-camsv-hardware.h"

/* Pinned e96 mtk_cam-sv-regs.h and ee2 drivers/memory/mtk-smi.c. */
#define CAM_MAIN_RESET 0x0058
#define SMI_CLAMP_STATE 0x03c0
#define SMI_CLAMP_SET 0x03c4
#define SMI_CLAMP_CLEAR 0x03c8
#define SV_SENSOR_MODE 0x0140
#define SV_VF_CONTROL 0x0148
#define SV_PATH_CONFIG 0x014c
#define SV_DONE_ENABLE 0x0344
#define SV_ERR_ENABLE 0x034c
#define SV_SOF_ENABLE 0x035c
#define SV_GRAB_PIXEL 0x0548
#define SV_GRAB_LINE 0x054c

static int resources(struct mt6878_camsv_hardware *h)
{
	struct mt6878_camsv_platform *p;
	struct mt6878_camsv_direct *d;
	unsigned int i;

	if (!h)
		return -EINVAL;
	p = h->platform;
	if (!p || !p->direct || !p->powered || p->retired)
		return -ENODEV;
	d = p->direct;
	if (!d->cq_cpu || !d->resources.domain)
		return -ENODEV;
	if (!pm_runtime_active(d->consumer) || !pm_runtime_active(p->cam_main) ||
	    !device_is_bound(d->dma_owner))
		return -EHOSTDOWN;
	for (i = 0; i < 8; i++)
		if (!__clk_is_enabled(d->resources.clocks[i].clk))
			return -EHOSTDOWN;
	for (i = 0; i < 6; i++)
		if (IS_ERR_OR_NULL(d->resources.banks[i]))
			return -ENODEV;
	return iommu_get_domain_for_dev(d->dma_owner) == d->resources.domain ? 0 : -ESTALE;
}

static int hardware_verify(void *context, enum mt6878_camsv_owner gate,
	const struct mt6878_camsv_job *job)
{
	struct mt6878_camsv_hardware *h = context;
	struct mt6878_camsv_platform *p = h->platform;
	unsigned int i;
	int ret = resources(h);

	if (ret)
		return ret;
	if (!job || job->sv_id != p->direct->resources.sv_id)
		return -EINVAL;
	switch (gate) {
	case MT6878_SV_RESOURCES:
	case MT6878_SV_IOMMU:
		return 0;
	case MT6878_SV_IRQ:
		if (p->requested != 4 || p->drained)
			return -ENXIO;
		for (i = 0; i < 4; i++)
			if (!irq_has_action(p->direct->resources.irqs[i]) ||
			    p->lines[i].platform != p || p->lines[i].index != i)
				return -ENXIO;
		return 0;
	case MT6878_SV_ROUTE:
		/* Graph-only SENINF has no native stream/VC/CAMMUX programming owner.
		 * A PHY transaction alone cannot prove those distinct destinations.
		 */
		return -ENOLINK;
	case MT6878_SV_STOPPED:
		/* No standard legacy s_stream getter proves sensor/CAMMUX OFF. Do not
		 * translate platform.drained or TG readback into complete route-off.
		 */
		return -ENOLINK;
	case MT6878_SV_COMPOSER:
		return -EOPNOTSUPP; /* Frozen direct supplies its actual CQ producer. */
	}
	return -EINVAL;
}

static int hardware_read(void *context, enum mt6878_camsv_region region,
	unsigned int offset, unsigned int *value)
{
	struct mt6878_camsv_hardware *h = context;
	int ret = resources(h);

	if (ret)
		return ret;
	if (!value || (unsigned int)region > MT6878_SV_SENINF || offset & 3)
		return -EINVAL;
	if (region == MT6878_SV_SENINF) {
		if (!h->seninf_base || h->seninf_size < 4 || offset > h->seninf_size - 4 ||
		    !pm_runtime_active(h->platform->receiver->dev))
			return -EHOSTDOWN;
		*value = readl(h->seninf_base + offset);
	} else {
		if (offset > 0xffc)
			return -ERANGE;
		*value = readl(h->platform->direct->resources.banks[region] + offset);
	}
	return 0;
}

static int hardware_write(void *context, enum mt6878_camsv_region region,
	unsigned int offset, unsigned int value)
{
	struct mt6878_camsv_hardware *h = context;
	int ret = resources(h);

	if (ret)
		return ret;
	if ((unsigned int)region > MT6878_SV_SENINF || offset & 3)
		return -EINVAL;
	if (region == MT6878_SV_SENINF) {
		if (!h->seninf_base || h->seninf_size < 4 || offset > h->seninf_size - 4 ||
		    !pm_runtime_active(h->platform->receiver->dev))
			return -EHOSTDOWN;
		writel(value, h->seninf_base + offset);
	} else {
		if (offset > 0xffc)
			return -ERANGE;
		writel(value, h->platform->direct->resources.banks[region] + offset);
	}
	return 0;
}

static int hardware_barrier(void *context)
{
	wmb(); /* Commit preceding CQ/register writes before the next phase. */
	return 0;
}

static int hardware_delay(void *context, unsigned int us)
{
	if (!us || us > 200)
		return -EINVAL;
	udelay(us);
	return 0;
}

static int hardware_clamp(void *context, unsigned int common, unsigned int enable)
{
	struct mt6878_camsv_hardware *h = context;
	u32 id, ports[32], value;
	int count, i, ret, valid = 0;

	if (common != 31 || enable > 1 || !h->smi_device || !h->reset_lock)
		return -EINVAL;
	lockdep_assert_held(h->reset_lock);
	if (!h->smi_regmap || dev_get_regmap(h->smi_device, NULL) != h->smi_regmap)
		return -EOPNOTSUPP;
	if (!pm_runtime_active(h->smi_device))
		return -EHOSTDOWN;
	ret = device_property_read_u32(h->smi_device, "mediatek,common-id", &id);
	if (ret || id != common)
		return ret ? ret : -EINVAL;
	count = device_property_count_u32(h->smi_device, "mediatek,comm-port-id");
	if (count <= 0 || count > (int)ARRAY_SIZE(ports))
		return -EINVAL;
	ret = device_property_read_u32_array(h->smi_device, "mediatek,comm-port-id", ports, count);
	if (ret)
		return ret;
	/* Validate the full property before the first write; -1 means unused. */
	for (i = 0; i < count; i++) {
		if (ports[i] == U32_MAX)
			continue;
		if (ports[i] >= 32)
			return -EINVAL;
		valid++;
	}
	if (!valid)
		return -EINVAL;
	for (i = 0; i < count; i++) {
		if (ports[i] == U32_MAX)
			continue;
		ret = regmap_write(h->smi_regmap, enable ? SMI_CLAMP_SET : SMI_CLAMP_CLEAR, BIT(ports[i]));
		if (!ret)
			ret = regmap_read_bypassed(h->smi_regmap, SMI_CLAMP_STATE, &value);
		if (ret)
			return ret;
		if (!!(value & BIT(ports[i])) != enable)
			return -EIO;
	}
	return 0;
}

int mt6878_camsv_cam_main_reset(struct mt6878_camsv_hardware *h)
{
	void __iomem *cq;
	u32 value;
	int ret;

	if (!h || !h->reset_lock || !h->cam_main || h->cam_main_size < CAM_MAIN_RESET + 4)
		return -EINVAL;
	lockdep_assert_held(h->reset_lock);
	ret = resources(h);
	if (ret)
		return ret;
	/* CAM_MAIN pulse is the vendor resume reset, not a live-frame recovery.
	 * Parent serializes submission/arm; never pulse a shared engine mid-DMA.
	 */
	if (h->platform->enabled || h->platform->direct->pair.tx.hw_attempted)
		return -EBUSY;
	ret = hardware_clamp(h, 31, 1);
	if (ret)
		return ret;
	cq = h->platform->direct->resources.banks[2];
	writel(0, cq + SV_CQ_RESET);
	writel(1, cq + SV_CQ_RESET);
	wmb(); /* Commit SCQ reset request before the vendor ready-bit poll. */
	ret = readl_poll_timeout(cq + SV_CQ_RESET, value, value & BIT(1), 1, 100000);
	if (ret)
		return ret; /* Preserve clamp on reset timeout, matching vendor failure. */
	writel(0, cq + SV_CQ_RESET);
	writel(0, h->cam_main + CAM_MAIN_RESET);
	writel(3U << (h->platform->direct->resources.sv_id * 2), h->cam_main + CAM_MAIN_RESET);
	writel(0, h->cam_main + CAM_MAIN_RESET);
	wmb(); /* Commit CAM_MAIN reset pulse before releasing the common clamp. */
	return hardware_clamp(h, 31, 0);
}

int mt6878_camsv_tg_off(struct mt6878_camsv_hardware *h)
{
	void __iomem *outer, *inner;
	u32 value;
	unsigned int i;
	int ret = resources(h);

	if (ret)
		return ret;
	/* Control task, after platform's real IRQ drain, never IRQ/queue context. */
	if (!h->platform->drained)
		return -EBUSY;
	lockdep_assert_not_held(&h->platform->direct->lock);
	for (i = 0; i < 4; i++) {
		struct irq_data *data = irq_get_irq_data(h->platform->direct->resources.irqs[i]);

		if (!data || !irqd_irq_disabled(data))
			return -EBUSY;
	}
	outer = h->platform->direct->resources.banks[0];
	inner = h->platform->direct->resources.banks[3];
	writel(1, outer + SV_DCM_DIS);
	writel(0, outer + SV_DONE_ENABLE);
	writel(0, outer + SV_ERR_ENABLE);
	writel(0, outer + SV_SOF_ENABLE);
	for (i = 0; i < 8; i++) {
		writel(0, inner + SV_GRAB_PIXEL + 0x40 * i);
		writel(0, inner + SV_GRAB_LINE + 0x40 * i);
	}
	value = readl(outer + SV_SENSOR_MODE);
	writel(value | BIT(11), outer + SV_SENSOR_MODE);
	value = readl(outer + SV_VF_CONTROL);
	writel(value & ~BIT(0), outer + SV_VF_CONTROL);
	readl(inner + SV_PATH_CONFIG);
	value = readl(outer + SV_PATH_CONFIG);
	writel(value | BIT(8), outer + SV_PATH_CONFIG);
	value = readl(outer + SV_PATH_CONFIG);
	writel(value & ~BIT(8), outer + SV_PATH_CONFIG);
	readl(inner + SV_PATH_CONFIG);
	value = readl(outer + SV_SENSOR_MODE);
	writel(value & ~BIT(0), outer + SV_SENSOR_MODE);
	wmb(); /* Commit TG/VF shutdown writes before checking their local state. */
	/* A local TG readback is NOT DMA, sensor or CAMMUX quiescence proof. */
	return (readl(outer + SV_SENSOR_MODE) & BIT(0)) ||
		(readl(outer + SV_VF_CONTROL) & BIT(0)) ? -EIO : 0;
}

int mt6878_seninf_calibration_read(struct device *receiver, struct clk *clock,
	unsigned int port, struct mt6878_phy_inputs *inputs)
{
	struct nvmem_cell *cell;
	void *data;
	size_t length;
	u32 word, sum, verify;
	unsigned long rate;
	unsigned int shift;

	if (!receiver || !clock || !inputs || port > 1)
		return -EINVAL;
	inputs->rg_csi_verified = 0;
	cell = nvmem_cell_get(receiver, "rg_csi");
	if (IS_ERR(cell))
		return PTR_ERR(cell);
	data = nvmem_cell_read(cell, &length);
	nvmem_cell_put(cell);
	if (IS_ERR(data))
		return PTR_ERR(data);
	if (length != sizeof(word)) {
		kfree(data);
		return -EMSGSIZE;
	}
	word = get_unaligned_le32(data);
	kfree(data);
	sum = port;
	for (shift = 7; shift <= 27; shift += 5)
		sum += (word >> shift) & 0x1f;
	verify = (((sum >> 4) & 0xf) + (sum & 0xf)) & 0x1f;
	if (sum != port && verify != (word & 0x1f))
		return -EBADMSG;
	if (!__clk_is_enabled(clock))
		return -EHOSTDOWN;
	rate = clk_get_rate(clock);
	if (rate != 312000000 && rate != 343000000 && rate != 416000000 && rate != 499000000)
		return -ERANGE;
	inputs->rg_csi = word;
	inputs->rg_csi_port = port;
	inputs->csi_clock_hz = rate;
	inputs->rg_csi_verified = 1;
	return 0;
}

int mt6878_camsv_hardware_backend(struct mt6878_camsv_hardware *h,
	struct mt6878_camsv_backend *backend)
{
	if (!h || !h->platform || !backend || !h->seninf_base || h->seninf_size != 0x18000)
		return -EINVAL;
	*backend = (struct mt6878_camsv_backend) {
		.verify = hardware_verify, .read = hardware_read, .write = hardware_write,
		.barrier = hardware_barrier, .delay_us = hardware_delay,
		.smi_clamp = hardware_clamp, .context = h,
		.sizes = { 0x1000, 0x1000, 0x1000, 0x18000 },
	};
	return 0;
}
