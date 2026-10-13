// SPDX-License-Identifier: GPL-2.0-only
#include <linux/device.h>
#include <linux/err.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include "mt6878-gpueb-mfg0.h"
#include "mt6878-gpueb-sram.h"
#include "mt6878-gpueb-reset.h"
#include "mt6878-gpueb-cold-prefix.h"

struct mt6878_gpueb_cold_prefix {
	struct mt6878_gpueb_mfg0 *power;
	struct mt6878_gpueb_sram *sram;
	int first_error;
};

int mt6878_gpueb_cold_prefix_prepare(struct platform_device *parent,
		struct mt6878_gpueb_cold_prefix **result)
{
	struct mt6878_gpueb_cold_prefix *prefix;
	struct resource *resource;
	int ret, cleanup;

	if (!parent || !result)
		return -EINVAL;
	if (*result)
		return -EALREADY;
	prefix = kzalloc(sizeof(*prefix), GFP_KERNEL);
	if (!prefix)
		return -ENOMEM;
	ret = mt6878_gpueb_mfg0_prepare(parent, &prefix->power);
	if (ret)
		goto free;
	ret = mt6878_gpueb_reset_validate_resources(parent);
	if (ret)
		goto finish;
	resource = platform_get_resource_byname(parent, IORESOURCE_MEM, "gpueb_base");
	/* Claim the one complete SRAM owner BEFORE native power writes. Mapping
	 * does not clear SRAM, manufacture OFF, or admit an inherited firmware.
	 */
	prefix->sram = mt6878_gpueb_sram_create(&parent->dev, resource);
	if (IS_ERR(prefix->sram)) {
		ret = PTR_ERR(prefix->sram);
		prefix->sram = NULL;
		goto finish;
	}
	*result = prefix;
	ret = mt6878_gpueb_mfg0_resume(prefix->power);
	if (ret) {
		prefix->first_error = ret;
		mt6878_gpueb_sram_unknown_start(prefix->sram);
		/* Resume already latched the failure and released the task mutex. */
		return ret;
	}
	ret = mt6878_gpueb_mfg0_finish(&prefix->power);
	if (ret) {
		prefix->first_error = ret;
		mt6878_gpueb_sram_unknown_start(prefix->sram);
		mt6878_gpueb_mfg0_quarantine(prefix->power, ret);
		return ret;
	}
	/* The existing MFG0 object retains real PM/module/device pins. No separate
	 * supplier, invented regulator/clock handles, RPC mapping or start API.
	 */
	return 0;
finish:
	cleanup = mt6878_gpueb_mfg0_finish(&prefix->power);
	if (cleanup) {
		prefix->first_error = ret;
		*result = prefix;
		mt6878_gpueb_mfg0_quarantine(prefix->power, ret);
		return ret;
	}
free:
	kfree(prefix);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_cold_prefix_prepare);
MODULE_DESCRIPTION("MT6878 source-backed native MFG0 acquisition prefix only");
MODULE_LICENSE("GPL");
