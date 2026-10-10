// SPDX-License-Identifier: GPL-2.0-only
#ifndef GPUEB_CONTROL_HOST_TEST
#include <linux/device.h>
#include <linux/err.h>
#include <linux/irq.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include "mt6878-gpueb-sram.h"
#include "mt6878-gpueb-reset-provider.h"
#include "mt6878-gpueb-mfg0.h"
#endif
#include "mt6878-gpueb-control.h"

struct mt6878_gpueb_control {
	struct mt6878_gpueb_mfg0 *power;
	struct mt6878_gpueb_sram *sram;
	struct mt6878_gpueb_reset_provider *reset;
	int first_error;
};

static int retain_failure(struct mt6878_gpueb_control *control, int error)
{
	if (!control->first_error)
		control->first_error = error < 0 ? error : -EPROTO;
	/* No physical OFF inferred even if provider registration returned error.
	 * Frozen provider can retain a partial IRQ/window scope on cleanup fault.
	 */
	mt6878_gpueb_sram_unknown_start(control->sram);
	mt6878_gpueb_mfg0_quarantine(control->power, control->first_error);
	return control->first_error;
}

int mt6878_gpueb_control_prepare(struct platform_device *parent,
	struct mt6878_gpueb_control **result)
{
	struct mt6878_gpueb_control *control;
	struct resource *sram, *registers;
	u32 cells;
	int ret, irq, cleanup;

	if (!parent || !result)
		return -EINVAL;
	if (*result)
		return -EALREADY;
	control = kzalloc(sizeof(*control), GFP_KERNEL);
	if (!control)
		return -ENOMEM;
	ret = mt6878_gpueb_mfg0_prepare(parent, &control->power);
	if (ret)
		goto free;
	/* Preflight the exact ee2 DT bank/IRQ/profile while the bound parent is
	 * locked. The frozen reset owner makes the single register/IRQ claim;
	 * this caller must not create overlapping claims or IRQF_SHARED users.
	 */
	sram = platform_get_resource_byname(parent, IORESOURCE_MEM, "gpueb_base");
	registers = platform_get_resource_byname(parent, IORESOURCE_MEM, "gpueb_reg_base");
	if (!sram || sram->start != GPUEB_SRAM_BASE ||
	    sram->end != GPUEB_SRAM_BASE + GPUEB_SRAM_SIZE - 1 ||
	    !registers || registers->start != 0x13c60000 || registers->end != 0x13c61fff) {
		ret = -ERANGE;
		goto finish;
	}
	ret = of_property_read_u32(parent->dev.of_node, "#reset-cells", &cells);
	if (ret || cells != 1) {
		ret = ret ?: -EINVAL;
		goto finish;
	}
	irq = platform_get_irq_byname(parent, "mbox0");
	if (irq < 0) {
		ret = irq;
		goto finish;
	}
	if (irq_get_trigger_type(irq) != IRQ_TYPE_LEVEL_HIGH) {
		ret = -EINVAL;
		goto finish;
	}
	/* SRAM mapping has no MMIO access. Claim BEFORE native genpd resume. */
	control->sram = mt6878_gpueb_sram_create(&parent->dev, sram);
	if (IS_ERR(control->sram)) {
		ret = PTR_ERR(control->sram);
		control->sram = NULL;
		goto finish;
	}
	*result = control;
	ret = mt6878_gpueb_mfg0_resume(control->power);
	if (ret)
		return retain_failure(control, ret);
	control->reset = mt6878_gpueb_reset_provider_register(parent, control->sram);
	if (IS_ERR(control->reset)) {
		ret = PTR_ERR(control->reset);
		control->reset = NULL;
		return retain_failure(control, ret);
	}
	ret = mt6878_gpueb_mfg0_finish(&control->power);
	if (ret)
		return retain_failure(control, ret);
	/* SRAM/IRQ/GPR/reset provider and its independent PM pins stay owned.
	 * No assert/deassert, firmware, mailbox send, rail or nested RPC write.
	 */
	return 0;
finish:
	cleanup = mt6878_gpueb_mfg0_finish(&control->power);
	if (cleanup) {
		/* No PM transition was attempted. Unexpected lock/lifetime failure
		 * still cannot authorize dropping an unresolved owner object.
		 */
		control->first_error = ret;
		*result = control;
		mt6878_gpueb_mfg0_quarantine(control->power, ret);
		return ret;
	}
free:
	kfree(control);
	return ret;
}
EXPORT_SYMBOL_GPL(mt6878_gpueb_control_prepare);
MODULE_DESCRIPTION("MT6878 GPUEB bound-parent SRAM/MFG0/reset ownership transaction");
MODULE_LICENSE("GPL");
