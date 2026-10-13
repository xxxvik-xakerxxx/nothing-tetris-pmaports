// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/property.h>
#include <linux/slab.h>
#include <soc/mediatek/camera-vmm-consumer.h>
#include "mt6878-cold-board.h"

struct mt6878_cold_board {
	struct mutex lock;
	struct mt6878_native_video_suppliers suppliers;
	struct mt6878_native_video *video;
	int first_error;
};

static struct platform_driver mt6878_cold_board_driver;

static void board_put_supplier(void *data)
{
	put_device(data);
}

static void board_put_receiver(void *data)
{
	fwnode_handle_put(data);
}

static struct device *board_supplier(struct device *dev, const char *property,
	const char *compatible)
{
	struct platform_device *supplier;
	struct device_node *node;
	int ret;

	if (of_count_phandle_with_args(dev->of_node, property, NULL) != 1)
		return ERR_PTR(-EINVAL);
	node = of_parse_phandle(dev->of_node, property, 0);
	if (!node)
		return ERR_PTR(-EINVAL);
	if (node == dev->of_node || !of_device_is_compatible(node, compatible)) {
		of_node_put(node);
		return ERR_PTR(-EINVAL);
	}
	if (!of_device_is_available(node) || of_node_check_flag(node, OF_DYNAMIC)) {
		of_node_put(node);
		return ERR_PTR(-ENODEV);
	}
	supplier = of_find_device_by_node(node);
	of_node_put(node);
	if (!supplier)
		return ERR_PTR(-EPROBE_DEFER);
	if (!device_is_bound(&supplier->dev)) {
		put_device(&supplier->dev);
		return ERR_PTR(-EPROBE_DEFER);
	}
	/* The actual constructor pins supplier drivers before media publication.
	 * Probe retains device lifetime only, without a PM/rail request.
	 */
	ret = devm_add_action_or_reset(dev, board_put_supplier, &supplier->dev);
	return ret ? ERR_PTR(ret) : &supplier->dev;
}

/* Validate the real bound driver BEFORE interpreting its private storage.
 * Drop device_lock before constructor pin_supplier() locks this same device.
 * This built-in static root has no remove path or manual bind attributes.
 */
static struct mt6878_cold_board *board_bound(struct platform_device *pdev)
{
	struct mt6878_cold_board *board;

	if (!pdev)
		return ERR_PTR(-EINVAL);
	device_lock(&pdev->dev);
	if (pdev->dev.driver != &mt6878_cold_board_driver.driver ||
	    !device_is_bound(&pdev->dev))
		board = ERR_PTR(-EPROBE_DEFER);
	else
		board = platform_get_drvdata(pdev);
	device_unlock(&pdev->dev);
	return board ? board : ERR_PTR(-ENODEV);
}

int mt6878_cold_board_publish(struct platform_device *pdev,
	const struct mt6878_camsv_job *layout,
	const struct mtkcam_ipi_config_param *config)
{
	struct mt6878_cold_board *board = board_bound(pdev);
	int ret;

	if (IS_ERR(board))
		return PTR_ERR(board);
	if (!layout || !config)
		return -ENODATA;
	/* Vendor INIT is not the restricted native recipe. Never clear its flags
	 * or synthesize tags, crop, stride, format or a PDAF unpacking policy.
	 */
	if (config->flags)
		return -EOPNOTSUPP;
	mutex_lock(&board->lock);
	if (board->first_error || board->video) {
		ret = board->first_error ? board->first_error : -EALREADY;
		goto out;
	}
	ret = mt6878_camera_vmm_validate_domain(board->suppliers.cam_main,
		MT6878_POWER_DOMAIN_CAM_MAIN);
	if (ret)
		goto out;
	board->suppliers.layout = *layout;
	board->suppliers.config = *config;
	/* Called only after a genuine driver-core bound point, NEVER from probe.
	 * Preserve non-NULL error results: partial publication can own live refs.
	 */
	ret = mt6878_cold_capture_register(&board->suppliers, &board->video);
	if (ret)
		board->first_error = ret;
out:
	mutex_unlock(&board->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_cold_board_publish);

int mt6878_cold_board_wait(struct platform_device *pdev, unsigned long timeout)
{
	struct mt6878_cold_board *board = board_bound(pdev);
	int ret;

	if (IS_ERR(board))
		return PTR_ERR(board);
	mutex_lock(&board->lock);
	ret = board->first_error;
	if (!ret)
		ret = board->video ? mt6878_native_video_wait_ready(board->video, timeout) : -ENODATA;
	mutex_unlock(&board->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_cold_board_wait);

int mt6878_cold_board_retire(struct platform_device *pdev)
{
	struct mt6878_cold_board *board = board_bound(pdev);
	int ret;

	if (IS_ERR(board))
		return PTR_ERR(board);
	mutex_lock(&board->lock);
	if (!board->video) {
		ret = board->first_error ? board->first_error : -ENODATA;
		goto out;
	}
	ret = mt6878_native_video_unregister(board->video);
	if (!ret) {
		board->video = NULL;
		/* Actual one-shot owner consumed; devm resource claims stay with root. */
		board->first_error = -ESHUTDOWN;
	}
out:
	mutex_unlock(&board->lock);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_cold_board_retire);

static int mt6878_cold_board_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct mt6878_cold_board *board;
	struct fwnode_handle *endpoint;
	const char *receiver_port;
	u32 id, port;
	int ret;

	if (!dev->of_node || of_node_check_flag(dev->of_node, OF_DYNAMIC) ||
	    device_property_present(dev, "iommus"))
		return -EOPNOTSUPP;
	ret = device_property_read_u32(dev, "mediatek,camsv-id", &id);
	if (!ret)
		ret = device_property_read_u32(dev, "nothing,csi-port", &port);
	if (ret || id != 0 || port != 1)
		return -EINVAL;
	board = devm_kzalloc(dev, sizeof(*board), GFP_KERNEL);
	if (!board)
		return -ENOMEM;
	mutex_init(&board->lock);
	board->suppliers.pdev = pdev;
	board->suppliers.port = port;
	board->suppliers.dma = board_supplier(dev, "nothing,dma-owner", "mediatek,camisp-larb");
	if (IS_ERR(board->suppliers.dma))
		return dev_err_probe(dev, PTR_ERR(board->suppliers.dma), "CAMISP owner unavailable\n");
	board->suppliers.cam_main = board_supplier(dev, "nothing,cam-main-owner", "mediatek,mt6878-camsys");
	if (IS_ERR(board->suppliers.cam_main))
		return dev_err_probe(dev, PTR_ERR(board->suppliers.cam_main), "CAM_MAIN owner unavailable\n");
	board->suppliers.smi = board_supplier(dev, "nothing,smi-reset-owner", "mediatek,mt6878-smi-common");
	if (IS_ERR(board->suppliers.smi))
		return dev_err_probe(dev, PTR_ERR(board->suppliers.smi), "SMI reset owner unavailable\n");
	endpoint = fwnode_graph_get_endpoint_by_id(dev_fwnode(dev), 0, 0, 0);
	if (!endpoint)
		return -ENOLINK;
	board->suppliers.receiver = fwnode_graph_get_remote_port_parent(endpoint);
	fwnode_handle_put(endpoint);
	if (!board->suppliers.receiver)
		return -ENOLINK;
	ret = devm_add_action_or_reset(dev, board_put_receiver, board->suppliers.receiver);
	if (ret)
		return ret;
	ret = fwnode_property_read_string(board->suppliers.receiver, "csi-port", &receiver_port);
	if (ret || strcmp(receiver_port, "1"))
		return -EINVAL;
	/* Probe establishes only resources and suspended runtime PM, not media
	 * readiness. A real producer publishes negotiated metadata after binding.
	 */
	ret = pm_runtime_set_suspended(dev);
	if (ret)
		return ret;
	platform_set_drvdata(pdev, board);
	pm_runtime_enable(dev);
	return 0;
}

static const struct of_device_id mt6878_cold_board_match[] = {
	{ .compatible = "nothing,tetris-cold-camsv0" },
	{ }
};
MODULE_DEVICE_TABLE(of, mt6878_cold_board_match);

static struct platform_driver mt6878_cold_board_driver = {
	.probe = mt6878_cold_board_probe,
	.driver = {
		.name = "mt6878-cold-board",
		.of_match_table = mt6878_cold_board_match,
		.suppress_bind_attrs = true,
	},
};
builtin_platform_driver(mt6878_cold_board_driver);
MODULE_LICENSE("GPL");
