/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _MT6878_NATIVE_VMM_H
#define _MT6878_NATIVE_VMM_H

#include "mt6878-vmm-supplier.h"

int mt6878_isp_vcore_ctl_set(struct regmap *spm, unsigned int domain, bool on);
int mt6878_vmm_isp_vcore_ctl_set(struct mt6878_vmm_supplier *vmm,
			       unsigned int domain, bool on);

#endif
