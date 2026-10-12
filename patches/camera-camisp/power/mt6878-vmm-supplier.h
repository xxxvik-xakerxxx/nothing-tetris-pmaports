/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _MT6878_VMM_SUPPLIER_H
#define _MT6878_VMM_SUPPLIER_H

#include <linux/mutex.h>
#include <linux/pm_domain.h>
#include <linux/regulator/consumer.h>

#include "mt6878-cam-power.h"

/*
 * Research integration API, not a platform driver. Zero-initialize once.
 * Caller owns permanent storage, device and SPM lifetime, including on failure
 * after exclusive acquisition. No devm cleanup, unbind or retry is safe there.
 * Establish voltage/rate policy and exclusive firmware ownership BEFORE init.
 */
struct mt6878_vmm_supplier {
	struct generic_pm_domain genpd;
	struct mutex lock;
	struct device *dev;
	struct regulator *buck;
	struct regmap *spm;
	int first_error;
	bool initialized;
};

struct mt6878_vmm_guard {
	struct notifier_block nb;
	struct mt6878_vmm_supplier *supplier;
	unsigned long pending;
	bool transitioning;
	bool registered;
	bool linked;
};

int mt6878_vmm_supplier_init(struct mt6878_vmm_supplier *vmm,
			     struct device *dev, struct regmap *spm,
			     struct generic_pm_domain *mm_infra);
/* Check after acquiring a PM lease, even when genpd was already logically ON. */
int mt6878_vmm_check(struct mt6878_vmm_supplier *vmm);
/* Leaf callbacks must latch their original errno BEFORE genpd supplier unwind. */
int mt6878_vmm_fail_child(struct mt6878_vmm_supplier *vmm, int error);
/*
 * Checked CAM_MAIN/CAM_VCORE control phase for sleeping genpd callbacks.
 * Caller holds the guarded graph's parent references and serializes the leaf.
 * ON: basic/LP clocks ready; follow with subsystem clocks, SRAM, bus release.
 * OFF: buses protected, SRAM off and subsystem clocks disabled beforehand.
 * Uses this owner's SPM and lock; any I/O error is latched before returning.
 * Stop the callback on failure, retaining dependencies; no cleanup or retry.
 * Other callback phases must still report errors with mt6878_vmm_fail_child().
 */
int mt6878_vmm_cam_ctl_set(struct mt6878_vmm_supplier *vmm,
			   unsigned int domain, bool on);
/*
 * Call during quiescent provider construction, before publishing any children.
 * guard_dev must already be attached directly to child; both persist forever.
 * Every immediate child must use this function, including ISP and non-CAM users.
 * MM_INFRA parents VMM; existing direct MM_INFRA edges may remain. Children OFF.
 * Partial attach is retained on failure: inspect registered/linked; do not free.
 */
int mt6878_vmm_add_child(struct mt6878_vmm_supplier *vmm,
			 struct generic_pm_domain *child, struct device *guard_dev,
			 struct mt6878_vmm_guard *guard);

#endif
