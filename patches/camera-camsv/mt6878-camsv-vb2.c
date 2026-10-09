// SPDX-License-Identifier: GPL-2.0-only
/* Buffer bridge only: no platform/video registration, DT or live MMIO adapter. */
#include "mt6878-camsv-vb2.h"
#include <linux/io.h>
#include <linux/of.h>

int mt6878_camsv_get_resources(struct platform_device *pdev,
	struct device *port_owner, struct mt6878_camsv_resources *resources)
{
	static const char * const banks[] = {
		"base", "base_DMA", "base_SCQ", "inner_base", "inner_base_DMA", "inner_base_SCQ"
	};
	static const char * const clocks[] = {
		"cam_main_cam_cgpdn", NULL, "cam_main_camsv_top_con",
		"cam_main_cam2mm0_gals_con", "cam_main_cam2mm1_gals_con", NULL,
		"topckgen_top_cam_sel", "topckgen_top_camtm_sel"
	};
	struct of_phandle_args args[2] = { 0 };
	struct device *dev;
	struct resource *resource;
	u32 sv_id, cammux, larb;
	unsigned int i, j;
	int ret;

	if (!pdev || !port_owner || !resources || !port_owner->of_node)
		return -EINVAL;
	dev = &pdev->dev;
	ret = device_property_read_u32(dev, "mediatek,camsv-id", &sv_id);
	if (!ret)
		ret = device_property_read_u32(dev, "mediatek,cammux-id", &cammux);
	if (ret || sv_id > 1 || cammux != sv_id * 8)
		return -EINVAL;
	if (!of_device_is_compatible(port_owner->of_node, "mediatek,camisp-larb") ||
	    device_property_read_u32(port_owner, "mediatek,larb-id", &larb) ||
	    larb != (sv_id ? 13 : 14) ||
	    of_count_phandle_with_args(port_owner->of_node, "iommus", "#iommu-cells") != 2)
		return -EINVAL;
	for (i = 0; i < 2; i++) {
		ret = of_parse_phandle_with_args(port_owner->of_node, "iommus",
			"#iommu-cells", i, &args[i]);
		if (ret)
			goto put_iommus;
		/* Exact NORMAL_DOM/MM_TAB CQI port0 + WDMA port1 encoding. */
		if (args[i].args_count != 1 || args[i].args[0] != ((larb << 5) | i)) {
			ret = -EINVAL;
			goto put_iommus;
		}
	}
	ret = args[0].np == args[1].np ? 0 : -EINVAL;
put_iommus:
	for (i = 0; i < 2; i++)
		of_node_put(args[i].np);
	if (ret)
		return ret;
	if (!device_is_bound(port_owner))
		return -EPROBE_DEFER;
	resources->domain = iommu_get_domain_for_dev(port_owner);
	if (!resources->domain)
		return -EPROBE_DEFER;
	/* Managed supplier lifetime only; deliberately no runtime-PM link flag. */
	if (!device_link_add(dev, port_owner, DL_FLAG_AUTOREMOVE_CONSUMER))
		return -ENOMEM;
	if (of_count_phandle_with_args(dev->of_node, "clocks", "#clock-cells") != 8 ||
	    device_property_string_array_count(dev, "clock-names") != 8 ||
	    of_count_phandle_with_args(dev->of_node, "power-domains", "#power-domain-cells") != 1)
		return -EINVAL;
	for (i = 0; i < 6; i++) {
		resource = platform_get_resource_byname(pdev, IORESOURCE_MEM, banks[i]);
		if (!resource || resource_size(resource) != 0x1000)
			return -EINVAL;
		resources->banks[i] = devm_ioremap_resource(dev, resource);
		if (IS_ERR(resources->banks[i]))
			return PTR_ERR(resources->banks[i]);
	}
	for (i = 0; i < 4; i++) {
		resources->irqs[i] = platform_get_irq(pdev, i);
		if (resources->irqs[i] < 0)
			return resources->irqs[i];
		for (j = 0; j < i; j++)
			if (resources->irqs[i] == resources->irqs[j])
				return -EINVAL;
	}
	for (i = 0; i < 8; i++)
		resources->clocks[i].id = clocks[i];
	resources->clocks[1].id = sv_id ? "cam_main_larb13_con" : "cam_main_larb14_con";
	resources->clocks[5].id = sv_id ? "cam_main_camsv_b_con" : "cam_main_camsv_a_con";
	ret = devm_clk_bulk_get(dev, 8, resources->clocks);
	if (ret)
		return ret;
	resources->port_owner = port_owner;
	resources->sv_id = sv_id;
	return 0;
}

static int mt6878_camsv_vb2_map(struct vb2_v4l2_buffer *buffer,
	struct device *owner, struct mt6878_camsv_buffer *mapped)
{
	struct vb2_buffer *vb;
	unsigned long size;

	if (!buffer || !owner)
		return -EINVAL;
	vb = &buffer->vb2_buf;
	if (!vb->vb2_queue || vb->vb2_queue->dev != owner || vb->num_planes != 1 ||
	    vb->vb2_queue->mem_ops != &vb2_dma_contig_memops ||
	    vb->state != VB2_BUF_STATE_ACTIVE || vb->planes[0].data_offset)
		return -EINVAL;
	size = vb2_plane_size(vb, 0);
	if (!size || size > 0xffffffffUL || !vb2_plane_cookie(vb, 0))
		return -EINVAL;
	mapped->dma = vb2_dma_contig_plane_dma_addr(vb, 0);
	mapped->size = size;
	mapped->mapped = 1;
	return 0;
}

int mt6878_camsv_vb2_submit(struct mt6878_camsv_vb2_pair *pair,
	struct vb2_v4l2_buffer *raw, struct vb2_v4l2_buffer *pdaf,
	struct device *dma_owner, struct iommu_domain *verified_domain,
	const struct mt6878_camsv_backend *io, const struct mt6878_camsv_job *job)
{
	struct mt6878_camsv_job mapped;
	int ret;

	if (!pair || !job || !raw || !pdaf || raw == pdaf ||
	    pair->raw || pair->pdaf || pair->tx.attempted || pair->completed ||
	    !dma_owner || !verified_domain ||
	    iommu_get_domain_for_dev(dma_owner) != verified_domain)
		return -EINVAL;
	if (raw->vb2_buf.vb2_queue == pdaf->vb2_buf.vb2_queue ||
	    !raw->vb2_buf.vb2_queue || !pdaf->vb2_buf.vb2_queue ||
	    raw->vb2_buf.vb2_queue->type != V4L2_BUF_TYPE_VIDEO_CAPTURE ||
	    pdaf->vb2_buf.vb2_queue->type != V4L2_BUF_TYPE_META_CAPTURE)
		return -EINVAL;
	mapped = *job;
	ret = mt6878_camsv_vb2_map(raw, dma_owner, &mapped.raw);
	if (!ret)
		ret = mt6878_camsv_vb2_map(pdaf, dma_owner, &mapped.pdaf);
	if (!ret)
		ret = mt6878_camsv_validate(io, &mapped);
	if (ret)
		return ret;
	/* Retain both buffers even if CQ submission fails after the START write.
	 * Never return DMA-owned memory before verified stop/reset completion.
	 */
	pair->raw = raw;
	pair->pdaf = pdaf;
	ret = mt6878_camsv_submit(io, &pair->tx, &mapped);
	if (ret && !pair->tx.hw_attempted) {
		/* No MMIO occurred: start_streaming may return these as QUEUED.
		 * Do not force a hardware reset for a rejected unsupported path.
		 */
		pair->raw = NULL;
		pair->pdaf = NULL;
	}
	return ret;
}

int mt6878_camsv_vb2_done(struct mt6878_camsv_vb2_pair *pair,
	unsigned int status, unsigned int inner_sequence, u64 timestamp_ns)
{
	int ret;

	if (!pair || !pair->raw || !pair->pdaf || pair->completed)
		return -EINVAL;
	if (mt6878_camsv_layout_validate(&pair->tx.job.raw_layout,
		vb2_plane_size(&pair->raw->vb2_buf, 0)) ||
	    mt6878_camsv_layout_validate(&pair->tx.job.pdaf_layout,
		vb2_plane_size(&pair->pdaf->vb2_buf, 0)))
		return -ERANGE;
	ret = mt6878_camsv_done(&pair->tx, status, inner_sequence);
	if (ret != 1)
		return ret;
	pair->completed = 1;
	pair->raw->sequence = inner_sequence;
	pair->pdaf->sequence = inner_sequence;
	pair->raw->vb2_buf.timestamp = timestamp_ns;
	pair->pdaf->vb2_buf.timestamp = timestamp_ns;
	vb2_set_plane_payload(&pair->raw->vb2_buf, 0, pair->tx.job.raw_layout.sizeimage);
	vb2_set_plane_payload(&pair->pdaf->vb2_buf, 0, pair->tx.job.pdaf_layout.sizeimage);
	vb2_buffer_done(&pair->raw->vb2_buf, VB2_BUF_STATE_DONE);
	vb2_buffer_done(&pair->pdaf->vb2_buf, VB2_BUF_STATE_DONE);
	return 1;
}

int mt6878_camsv_vb2_stop(struct mt6878_camsv_vb2_pair *pair,
	const struct mt6878_camsv_backend *io)
{
	int ret;

	if (!pair || !pair->raw || !pair->pdaf)
		return -EINVAL;
	ret = mt6878_camsv_stop(io, &pair->tx);
	if (!pair->tx.quiesced)
		return ret; /* Caller must retain mappings/queues and recover ownership. */
	if (!pair->completed) {
		pair->completed = 1;
		vb2_set_plane_payload(&pair->raw->vb2_buf, 0, 0);
		vb2_set_plane_payload(&pair->pdaf->vb2_buf, 0, 0);
		vb2_buffer_done(&pair->raw->vb2_buf, VB2_BUF_STATE_ERROR);
		vb2_buffer_done(&pair->pdaf->vb2_buf, VB2_BUF_STATE_ERROR);
	}
	return ret;
}
