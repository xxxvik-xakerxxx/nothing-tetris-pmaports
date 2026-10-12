// SPDX-License-Identifier: GPL-2.0-only
#include <linux/dma-mapping.h>
#include <linux/iommu.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <soc/mediatek/camisp-dma.h>

struct mt6878_camisp_dma {
	struct device *larb;
	struct module *owner;
	struct iommu_domain *domain;
	struct device *dev;
	u64 old_dma_mask, old_coherent_mask;
	unsigned int old_segment;
};

static int camisp_ports(struct device *dev, unsigned int *larbid,
	struct device_node **iommu)
{
	struct iommu_fwspec *fwspec = dev_iommu_fwspec_get(dev);
	struct of_phandle_args port = { 0 };
	u32 id;
	unsigned int i;
	int ret;

	if (of_property_read_u32(dev->of_node, "mediatek,larb-id", &id) ||
	    (id != 13 && id != 14) ||
	    of_count_phandle_with_args(dev->of_node, "iommus", "#iommu-cells") != 2)
		return -EINVAL;
	/* driver-core DMA configure/attach must precede this probe. Never invent
	 * a domain, configure ports manually, or take private IOMMU driver data.
	 */
	if (!fwspec || fwspec->num_ids != 2)
		return -ENODEV;
	*iommu = NULL;
	for (i = 0; i < 2; i++) {
		ret = of_parse_phandle_with_args(dev->of_node, "iommus", "#iommu-cells", i, &port);
		if (ret)
			goto fail;
		if (port.args_count != 1 || port.args[0] != ((id << 5) | i) ||
		    fwspec->ids[i] != port.args[0] || (i && port.np != *iommu))
			ret = -EINVAL;
		if (!i && !ret)
			*iommu = of_node_get(port.np);
		of_node_put(port.np);
		if (ret)
			goto fail;
	}
	*larbid = id;
	return 0;
fail:
	of_node_put(*iommu);
	*iommu = NULL;
	return ret;
}

static struct device *camisp_physical_larb(struct device_node *iommu, unsigned int id)
{
	struct device_node *node;
	struct platform_device *pdev = NULL;
	unsigned int matches = 0;
	u32 larbid;
	int i, count = of_count_phandle_with_args(iommu, "mediatek,larbs", NULL);

	if (!of_device_is_compatible(iommu, "mediatek,mt6878-disp-iommu") ||
	    !of_device_is_available(iommu) || count <= 0)
		return ERR_PTR(-EINVAL);
	for (i = 0; i < count; i++) {
		node = of_parse_phandle(iommu, "mediatek,larbs", i);
		if (!node)
			goto invalid;
		if (!of_property_read_u32(node, "mediatek,larb-id", &larbid) && larbid == id) {
			matches++;
			if (matches != 1 || !of_device_is_available(node) ||
			    !of_device_is_compatible(node, "mediatek,mt6878-smi-larb") ||
			    of_node_check_flag(node, OF_DYNAMIC)) {
				of_node_put(node);
				goto invalid;
			}
			pdev = of_find_device_by_node(node);
		}
		of_node_put(node);
	}
	if (!pdev)
		return ERR_PTR(matches ? -EPROBE_DEFER : -ENODEV);
	return &pdev->dev;
invalid:
	if (pdev)
		put_device(&pdev->dev);
	return ERR_PTR(-EINVAL);
}

static void camisp_put_supplier(void *data)
{
	struct mt6878_camisp_dma *dma = data;

	put_device(dma->larb);
	module_put(dma->owner);
}

static void camisp_restore_dma(void *data)
{
	struct mt6878_camisp_dma *dma = data;

	*dma->dev->dma_mask = dma->old_dma_mask;
	dma->dev->coherent_dma_mask = dma->old_coherent_mask;
	dma_set_max_seg_size(dma->dev, dma->old_segment);
}

static int camisp_dma_resume(struct device *dev)
{
	struct mt6878_camisp_dma *dma = dev_get_drvdata(dev);

	/* PM core has resumed the linked physical larb, including its real SMI
	 * clock/translation restore. An active logical device alone proves nothing.
	 */
	if (!device_is_bound(dma->larb) || !pm_runtime_enabled(dma->larb) ||
	    !pm_runtime_active(dma->larb))
		return -EHOSTDOWN;
	if (iommu_get_domain_for_dev(dev) != dma->domain)
		return -ESTALE;
	return 0;
}

static int camisp_dma_suspend(struct device *dev)
{
	struct mt6878_camisp_dma *dma = dev_get_drvdata(dev);
	int ret = mt6878_camisp_dma_idle(dma->larb);

	/* Busy DMA retains the logical PM state and physical supplier reference. */
	if (ret)
		return ret;
	return 0;
}

static int camisp_dma_system_suspend(struct device *dev)
{
	return atomic_read(&dev->power.usage_count) ? -EBUSY : 0;
}

static int camisp_dma_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev, *larb;
	struct mt6878_camisp_dma *dma;
	struct device_node *iommu;
	struct iommu_domain *domain;
	unsigned int id;
	int ret;

	if (!dev->of_node || of_node_check_flag(dev->of_node, OF_DYNAMIC) ||
	    platform_get_resource(pdev, IORESOURCE_MEM, 0) || !dev->dma_mask ||
	    dev->dma_parms != &pdev->dma_parms ||
	    of_find_property(dev->of_node, "clocks", NULL) ||
	    of_find_property(dev->of_node, "power-domains", NULL) ||
	    of_find_property(dev->of_node, "resets", NULL))
		return -EINVAL; /* This logical port never owns/remaps physical resources. */
	ret = camisp_ports(dev, &id, &iommu);
	if (ret)
		return dev_err_probe(dev, ret, "CAMISP ports are not attached\n");
	larb = camisp_physical_larb(iommu, id);
	of_node_put(iommu);
	if (IS_ERR(larb))
		return dev_err_probe(dev, PTR_ERR(larb), "physical CAMSV larb unavailable\n");
	domain = iommu_get_domain_for_dev(dev);
	if (!domain || !iommu_is_dma_domain(domain)) {
		ret = -ENODEV;
		goto put_larb;
	}
	if (!device_is_bound(larb) || !pm_runtime_enabled(larb)) {
		ret = -EPROBE_DEFER;
		goto put_larb;
	}
	dma = devm_kzalloc(dev, sizeof(*dma), GFP_KERNEL);
	if (!dma) {
		ret = -ENOMEM;
		goto put_larb;
	}
	/* Parent must cooperatively exclude forced unbind during active DMA. */
	if (!device_trylock(larb)) {
		ret = -EBUSY;
		goto put_larb;
	}
	if (!device_is_bound(larb) || !larb->driver || !try_module_get(larb->driver->owner)) {
		device_unlock(larb);
		ret = -ENODEV;
		goto put_larb;
	}
	dma->owner = larb->driver->owner;
	device_unlock(larb);
	dma->larb = larb;
	dma->domain = domain;
	ret = devm_add_action_or_reset(dev, camisp_put_supplier, dma);
	if (ret)
		return ret;
	dma->dev = dev;
	dma->old_dma_mask = *dev->dma_mask;
	dma->old_coherent_mask = dev->coherent_dma_mask;
	dma->old_segment = dev->dma_parms->max_segment_size;
	ret = devm_add_action_or_reset(dev, camisp_restore_dma, dma);
	if (ret)
		return ret;
	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(34));
	if (ret)
		return ret;
	dma_set_max_seg_size(dev, UINT_MAX);
	/* Merge the IOMMU's existing PM link with managed removal ordering. */
	if (!device_link_add(dev, larb, DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER)) {
		return -ENOMEM;
	}
	platform_set_drvdata(pdev, dma);
	pm_runtime_enable(dev);
	return 0;
put_larb:
	put_device(larb);
	return ret;
}

static void camisp_dma_remove(struct platform_device *pdev)
{
	pm_runtime_disable(&pdev->dev);
}

static const struct dev_pm_ops camisp_dma_pm = {
	RUNTIME_PM_OPS(camisp_dma_suspend, camisp_dma_resume, NULL)
	SYSTEM_SLEEP_PM_OPS(camisp_dma_system_suspend, NULL)
};

static const struct of_device_id camisp_dma_match[] = {
	{ .compatible = "mediatek,camisp-larb" },
	{ }
};
MODULE_DEVICE_TABLE(of, camisp_dma_match);

static struct platform_driver camisp_dma_driver = {
	.probe = camisp_dma_probe,
	.remove = camisp_dma_remove,
	.driver = {
		.name = "mt6878-camisp-dma",
		.of_match_table = camisp_dma_match,
		.pm = pm_ptr(&camisp_dma_pm),
		.suppress_bind_attrs = true,
	},
};
module_platform_driver(camisp_dma_driver);
MODULE_DESCRIPTION("MT6878 CAMSV IOMMU-backed DMA supplier");
MODULE_LICENSE("GPL");
