// SPDX-License-Identifier: GPL-2.0-only
#include <linux/build_bug.h>
#include "mt6878-capture-epoch.h"

static_assert(sizeof(((struct mt6878_capture_epoch *)0)->dma_receipt) ==
	      sizeof(struct mt6878_camsv_transaction));

int mt6878_epoch_smoke(struct mt6878_capture_epoch *e);
int mt6878_epoch_smoke(struct mt6878_capture_epoch *e)
{
	return e ? e->first_error : -EINVAL;
}
