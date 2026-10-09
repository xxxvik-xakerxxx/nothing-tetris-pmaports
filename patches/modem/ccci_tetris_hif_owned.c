// SPDX-License-Identifier: GPL-2.0-only
#include <linux/err.h>
#include <linux/module.h>
#include "ccci_hif.h"
#include "ccci_hif_internal.h"
#include "ccci_tetris_owner.h"

static bool tetris_hif_attempted;
static int tetris_hif_error;
static struct module *tetris_hif_modules[2];

int ccci_hif_start_owned(void)
{
	static const unsigned char ids[] = {CCIF_HIF_ID, DPMAIF_HIF_ID};
	struct ccci_hif_ops *providers[2];
	unsigned int i;
	int ret;

	/* Called under the sole transport owner's mutex, after powered-access proof. */
	if (tetris_hif_attempted)
		return tetris_hif_error ? tetris_hif_error : -EALREADY;
	tetris_hif_attempted = true;
	for (i = 0; i < ARRAY_SIZE(ids); i++) {
		providers[i] = ccci_hif_op[ids[i]];
		if (!ccci_hif[ids[i]] || !providers[i] || !providers[i]->start ||
		    !providers[i]->owner) {
			ret = -ENODEV;
			goto fault;
		}
	}
	/* Pin every provider before the first hardware operation. */
	for (i = 0; i < ARRAY_SIZE(ids); i++) {
		if (!try_module_get(providers[i]->owner)) {
			while (i)
				module_put(tetris_hif_modules[--i]);
			ret = -ENODEV;
			goto fault;
		}
		tetris_hif_modules[i] = providers[i]->owner;
	}
	for (i = 0; i < ARRAY_SIZE(ids); i++) {
		ret = providers[i]->start(ids[i]);
		if (ret) {
			ret = ret < 0 ? ret : -EPROTO;
			goto fault;
		}
	}
	return 0;
fault:
	tetris_hif_error = ret;
	return ret;
}
