/* SPDX-License-Identifier: GPL-2.0-only */
/* Included in ccci_hif.c after the real registry arrays. */
#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)
#include <linux/device.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include "ccci_tetris_native_start.h"

static DEFINE_MUTEX(native_hif_lock);
static struct {
	struct device *dev;
	struct device_driver *driver;
	struct ccci_hif_ops *ops;
	void *data;
	struct resource *claims[4];
	unsigned int claim_count;
} native_hif[CCCI_HIF_NUM];
static const unsigned char native_hif_ids[] = { CCIF_HIF_ID, DPMAIF_HIF_ID };
static unsigned int native_hif_start_step;
static int native_hif_error;

int ccci_tetris_hif_claim(struct platform_device *pdev, unsigned char id)
{
	struct resource res;
	unsigned int i, count;
	int ret = 0;

	if (id != CCIF_HIF_ID && id != DPMAIF_HIF_ID)
		return -EOPNOTSUPP;
	/* Exact B4.1 of_iomap inventory: CCIF AP/MD, DPMAIF AO/PD/MD-misc/SRAM.
	 * Shared infracfg/syscon ownership is not duplicated by this transaction. */
	count = id == CCIF_HIF_ID ? 2 : 4;
	mutex_lock(&native_hif_lock);
	if (native_hif_error) {
		ret = native_hif_error;
		goto out;
	}
	if (native_hif[id].dev) {
		ret = -EALREADY;
		goto out;
	}
	for (i = 0; i < count; i++) {
		ret = of_address_to_resource(pdev->dev.of_node, i, &res);
		if (ret)
			goto out;
		if (resource_type(&res) != IORESOURCE_MEM || !resource_size(&res)) {
			ret = -EINVAL;
			goto out;
		}
		/* Non-devm claims survive a failed probe after a physical mutation.
		 * Failed profiles require cold recovery; no retry/unowned release API. */
		native_hif[id].claims[i] = request_mem_region(res.start,
			resource_size(&res), "tetris-native-hif");
		if (!native_hif[id].claims[i]) {
			ret = -EBUSY;
			goto out;
		}
		native_hif[id].claim_count++;
	}
	native_hif[id].dev = get_device(&pdev->dev);
out:
	if (ret && !native_hif_error)
		native_hif_error = ret;
	mutex_unlock(&native_hif_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(ccci_tetris_hif_claim);

int ccci_tetris_hif_register(unsigned char id, void *data,
			     struct ccci_hif_ops *ops, struct device *dev)
{
	int ret = 0;

	if (id != CCIF_HIF_ID && id != DPMAIF_HIF_ID)
		return -EOPNOTSUPP;
	mutex_lock(&native_hif_lock);
	if (native_hif_error) {
		ret = native_hif_error;
		goto out;
	}
	if (native_hif[id].dev != dev || !data || !ops || !ops->start ||
	    !ops->owner || !dev->driver || native_hif[id].ops ||
	    ccci_hif[id] || ccci_hif_op[id]) {
		ret = -EBUSY;
		goto out;
	}
	if (!try_module_get(ops->owner)) {
		ret = -ENODEV;
		goto out;
	}
	/* Seal the real registration under the same mutex as all registry writers.
	 * Preserve module/device/data/ops identity for the whole boot. */
	native_hif[id].driver = dev->driver;
	native_hif[id].ops = ops;
	native_hif[id].data = data;
	ccci_hif[id] = data;
	ccci_hif_op[id] = ops;
out:
	if (ret && !native_hif_error)
		native_hif_error = ret;
	mutex_unlock(&native_hif_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(ccci_tetris_hif_register);

int ccci_tetris_hif_lock(void)
{
	unsigned int i;
	int ret;

	/* Singleton START holds its own lock. trylock avoids driver-core inversion.
	 * No driver probe is allowed to overwrite a sealed registry entry. */
	for (i = 0; i < ARRAY_SIZE(native_hif_ids); i++) {
		struct device *dev = native_hif[native_hif_ids[i]].dev;

		if (!dev || !device_trylock(dev)) {
			ret = -EBUSY;
			goto unwind;
		}
	}
	mutex_lock(&native_hif_lock);
	ret = native_hif_error;
	for (i = 0; !ret && i < ARRAY_SIZE(native_hif_ids); i++) {
		unsigned char id = native_hif_ids[i];

		if (!device_is_bound(native_hif[id].dev) ||
		    native_hif[id].dev->driver != native_hif[id].driver ||
		    !native_hif[id].ops || !native_hif[id].ops->start ||
		    native_hif[id].data != ccci_hif[id] || native_hif[id].ops != ccci_hif_op[id] ||
		    native_hif[id].claim_count != (id == CCIF_HIF_ID ? 2 : 4))
			ret = -ESTALE;
	}
	mutex_unlock(&native_hif_lock);
	if (!ret)
		return 0;
	i = ARRAY_SIZE(native_hif_ids);
unwind:
	while (i)
		device_unlock(native_hif[native_hif_ids[--i]].dev);
	return ret;
}

void ccci_tetris_hif_unlock(void)
{
	unsigned int i = ARRAY_SIZE(native_hif_ids);

	while (i)
		device_unlock(native_hif[native_hif_ids[--i]].dev);
}

int ccci_tetris_hif_start(void)
{
	unsigned int i;
	int ret;

	if (native_hif_start_step)
		return native_hif_error ? native_hif_error : -EALREADY;
	for (i = 0; i < ARRAY_SIZE(native_hif_ids); i++) {
		unsigned char id = native_hif_ids[i];

		native_hif_start_step = i + 1;
		ret = native_hif[id].ops->start(id);
		if (ret) {
			native_hif_error = ret < 0 ? ret : -EPROTO;
			return native_hif_error;
		}
	}
	return 0;
}
#endif
