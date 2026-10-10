/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_SENINF_NATIVE_PM_H
#define MT6878_SENINF_NATIVE_PM_H

#include <linux/clk.h>
#include <linux/mutex.h>
#include <linux/regulator/consumer.h>

struct mt6878_seninf_pm {
	struct mutex lock;
	struct device *dev, **domains;
	struct clk_bulk_data *clocks;
	struct regulator *vcore;
	struct clk *old_parent;
	u32 step[7];
	unsigned int port, domain_refs;
	unsigned long clock_refs;
	bool voltage_vote, parent_changed, rate_owned;
	int first_error;
};

int mt6878_seninf_pm_init(struct mt6878_seninf_pm *pm, struct device *dev,
	struct device **domains, struct clk_bulk_data *clocks,
	unsigned int count, struct regulator *vcore, unsigned int port);
int mt6878_seninf_pm_resume(struct mt6878_seninf_pm *pm);
int mt6878_seninf_pm_suspend(struct mt6878_seninf_pm *pm);
bool mt6878_seninf_pm_busy(struct mt6878_seninf_pm *pm);

#endif
