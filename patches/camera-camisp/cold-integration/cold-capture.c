// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/of.h>
#include <linux/pm_runtime.h>
#include <linux/property.h>
#include "cold-capture.h"

int mt6878_cold_suppliers_check(const struct mt6878_native_video_suppliers *s)
{
	struct fwnode_handle *endpoint, *receiver;
	u32 id, larb, common;
	int ret;

	if (!s || !s->pdev || !s->dma || !s->cam_main || !s->smi || !s->receiver)
		return -EINVAL;
	if (s->dma == &s->pdev->dev || s->cam_main == &s->pdev->dev ||
	    s->smi == &s->pdev->dev || s->dma == s->cam_main ||
	    s->dma == s->smi || s->cam_main == s->smi)
		return -EINVAL;
	if (!device_is_bound(&s->pdev->dev) || !device_is_bound(s->dma) ||
	    !device_is_bound(s->cam_main) || !device_is_bound(s->smi))
		return -EPROBE_DEFER;
	if (!of_device_is_compatible(s->dma->of_node, "mediatek,camisp-larb") ||
	    !of_device_is_compatible(s->cam_main->of_node, "mediatek,mt6878-camsys") ||
	    !of_device_is_compatible(s->smi->of_node, "mediatek,mt6878-smi-common"))
		return -EINVAL;
	ret = device_property_read_u32(&s->pdev->dev, "mediatek,camsv-id", &id);
	if (!ret)
		ret = device_property_read_u32(s->dma, "mediatek,larb-id", &larb);
	if (!ret)
		ret = device_property_read_u32(s->smi, "mediatek,common-id", &common);
	if (ret)
		return ret;
	if (id > 1 || larb != (id ? 13 : 14) || common != 31 || s->layout.sv_id != id)
		return -EINVAL;
	endpoint = fwnode_graph_get_endpoint_by_id(dev_fwnode(&s->pdev->dev), 0, 0, 0);
	if (!endpoint)
		return -ENOLINK;
	receiver = fwnode_graph_get_remote_port_parent(endpoint);
	fwnode_handle_put(endpoint);
	ret = receiver && receiver == s->receiver ? 0 : -ENOLINK;
	fwnode_handle_put(receiver);
	if (ret)
		return ret;
	/* Real runtime-PM supplier links, not a second rail/domain owner. */
	if (!device_link_add(&s->pdev->dev, s->dma,
		DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER) ||
	    !device_link_add(&s->pdev->dev, s->cam_main,
		DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER) ||
	    !device_link_add(&s->pdev->dev, s->smi,
		DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER))
		return -ENOMEM;
	return 0;
}

int mt6878_cold_capture_register(const struct mt6878_native_video_suppliers *suppliers,
	struct mt6878_native_video **result)
{
	/* The actual video constructor performs supplier and negotiated-mode checks.
	 * A failed constructor can retain a non-NULL owner; caller must keep it.
	 */
	return mt6878_native_video_register(suppliers, result);
}
EXPORT_SYMBOL_GPL(mt6878_cold_capture_register);
