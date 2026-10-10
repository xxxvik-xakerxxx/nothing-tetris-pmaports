/* SPDX-License-Identifier: GPL-2.0-only */
/* Included only inside drivers/memory/mtk-smi.c, after struct mtk_smi. Uses
 * that provider's actual base/clock/PM state, never consumer ioremap/regmap.
 */
#include <linux/mutex.h>
#include <linux/property.h>
#include <soc/mediatek/smi-camera-reset.h>

#define MT6878_CAMERA_CLAMP_STATE 0x03c0
#define MT6878_CAMERA_CLAMP_SET 0x03c4
#define MT6878_CAMERA_CLAMP_CLEAR 0x03c8

static struct platform_driver mtk_smi_common_driver;

static int mtk_smi_camera_ports(struct device *dev, u32 *ports, int *count, u32 *mask)
{
	u32 id;
	int ret, i;

	if (!of_device_is_compatible(dev->of_node, "mediatek,mt6878-smi-common"))
		return -EOPNOTSUPP;
	ret = device_property_read_u32(dev, "mediatek,common-id", &id);
	if (ret || id != 31)
		return ret ? ret : -EOPNOTSUPP;
	*count = device_property_count_u32(dev, "mediatek,comm-port-id");
	if (*count <= 0 || *count > 32)
		return -EINVAL;
	ret = device_property_read_u32_array(dev, "mediatek,comm-port-id", ports, *count);
	if (ret)
		return ret;
	*mask = 0;
	for (i = 0; i < *count; i++) {
		if (ports[i] == U32_MAX)
			continue;
		if (ports[i] >= 32 || (*mask & BIT(ports[i])))
			return -EINVAL;
		*mask |= BIT(ports[i]);
	}
	return *mask ? 0 : -EINVAL;
}

static int mtk_smi_camera_probe_prepare(struct platform_device *pdev,
	struct mtk_smi *common, int *required_clocks)
{
	struct device *dev = &pdev->dev;
	struct device_node *node;
	struct platform_device *parent;
	struct resource *resource;
	u32 id, ports[32], mask;
	const char *name;
	int count, ret;

	mutex_init(&common->camera_reset_lock);
	if (!of_device_is_compatible(dev->of_node, "mediatek,mt6878-smi-common") ||
	    device_property_read_u32(dev, "mediatek,common-id", &id) || id != 31)
		return 0; /* No changed behavior for DISP or other common providers. */
	ret = mtk_smi_camera_ports(dev, ports, &count, &mask);
	if (ret)
		return ret;
	resource = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!resource || resource_size(resource) != 0x1000 ||
	    of_count_phandle_with_args(dev->of_node, "clocks", "#clock-cells") != 1 ||
	    device_property_string_array_count(dev, "clock-names") != 1 ||
	    device_property_read_string(dev, "clock-names", &name) || strcmp(name, "apb") ||
	    of_count_phandle_with_args(dev->of_node, "power-domains", "#power-domain-cells") != 1)
		return -EINVAL;
	/* ee2 MT6878 common31 has one CAM_VCORE APB clock, not gen2 APB+SMI. */
	*required_clocks = 1;
	node = of_parse_phandle(dev->of_node, "mediatek,smi-supply", 0);
	if (!node)
		return -EINVAL;
	parent = of_find_device_by_node(node);
	of_node_put(node);
	if (!parent)
		return -EPROBE_DEFER;
	ret = device_is_bound(&parent->dev) ? 0 : -EPROBE_DEFER;
	if (!ret && !device_link_add(dev, &parent->dev,
		DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER))
		ret = -ENOMEM;
	put_device(&parent->dev);
	return ret;
}

int mtk_smi_camera_reset_clamp(struct device *dev, struct device *consumer, bool on)
{
	struct mtk_smi *common;
	u32 ports[32], mask, state;
	int count, i, ret;

	if (!dev || !consumer || dev == consumer || !dev->of_node)
		return -EINVAL;
	/* Provider binding/devres is stable during this operation. Never wait
	 * behind supplier remove while holding the camera's queue/reset mutex.
	 */
	if (!device_trylock(dev))
		return -EBUSY;
	if (dev->driver != &mtk_smi_common_driver.driver || !device_is_bound(dev)) {
		ret = -ENODEV;
		goto unlock_device;
	}
	common = dev_get_drvdata(dev);
	if (!common || common->dev != dev || IS_ERR_OR_NULL(common->base)) {
		ret = -ENODEV;
		goto unlock_device;
	}
	if (!mutex_trylock(&common->camera_reset_lock)) {
		ret = -EBUSY;
		goto unlock_device;
	}
	ret = mtk_smi_camera_ports(dev, ports, &count, &mask);
	if (ret)
		goto unlock_reset;
	if (on) {
		if (!pm_runtime_enabled(dev)) {
			ret = -EHOSTDOWN;
			goto unlock_reset;
		}
		if (common->camera_reset_consumer) {
			ret = common->camera_reset_consumer == consumer ? -EALREADY : -EBUSY;
			goto unlock_reset;
		}
		if (!device_is_bound(consumer) ||
		    !device_link_add(consumer, dev, DL_FLAG_AUTOREMOVE_CONSUMER)) {
			ret = -ENODEV;
			goto unlock_reset;
		}
		if (!try_module_get(THIS_MODULE)) {
			ret = -ENODEV;
			goto unlock_reset;
		}
		ret = pm_runtime_resume_and_get(dev);
		if (ret < 0) {
			module_put(THIS_MODULE);
			goto unlock_reset;
		}
		state = readl(common->base + MT6878_CAMERA_CLAMP_STATE);
		if (state & mask) {
			ret = -EBUSY; /* Never clear a pre-existing foreign clamp. */
			pm_runtime_put_sync(dev);
			module_put(THIS_MODULE);
			goto unlock_reset;
		}
		common->camera_reset_consumer = get_device(consumer);
		common->camera_reset_mask = mask;
		common->camera_reset_error = 0;
	} else if (common->camera_reset_consumer != consumer ||
		   common->camera_reset_mask != mask) {
		ret = -EPERM;
		goto unlock_reset;
	}
	if (common->camera_reset_error) {
		ret = common->camera_reset_error;
		goto unlock_reset;
	}
	if (!pm_runtime_active(dev)) {
		common->camera_reset_error = -EHOSTDOWN;
		ret = -EHOSTDOWN;
		goto unlock_reset;
	}
	/* Preserve vendor per-membership write/read order, not an all-port mask. */
	for (i = 0; i < count; i++) {
		if (ports[i] == U32_MAX)
			continue;
		writel(BIT(ports[i]), common->base +
			(on ? MT6878_CAMERA_CLAMP_SET : MT6878_CAMERA_CLAMP_CLEAR));
		state = readl(common->base + MT6878_CAMERA_CLAMP_STATE);
		if (!!(state & BIT(ports[i])) != on) {
			common->camera_reset_error = -EIO;
			ret = -EIO;
			goto unlock_reset; /* Retain PM/module/consumer and actual clamp. */
		}
	}
	ret = 0;
	if (!on) {
		put_device(common->camera_reset_consumer);
		common->camera_reset_consumer = NULL;
		common->camera_reset_mask = 0;
		ret = pm_runtime_put_sync(dev);
		module_put(THIS_MODULE);
		if (ret > 0)
			ret = 0;
	}
unlock_reset:
	mutex_unlock(&common->camera_reset_lock);
unlock_device:
	device_unlock(dev);
	return ret;
}
EXPORT_SYMBOL_GPL(mtk_smi_camera_reset_clamp);
