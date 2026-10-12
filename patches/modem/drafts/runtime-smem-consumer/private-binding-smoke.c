/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/slab.h>
#include "modem_sys.h"

#if !IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_OWNER)
#error "Private binding smoke requires the actual OWNER struct layout"
#endif
#if !defined(CONFIG_TETRIS_CCCI_SMEM_CONSUMER) || !CONFIG_TETRIS_CCCI_SMEM_CONSUMER
#error "Private binding smoke requires checked CONSUMER helpers"
#endif
#include "consumer.h"

static int __init tetris_private_binding_init(void)
{
	struct ccci_modem *md;
	int ret;

	/* Real vendor type and patched trailing field; no platform/probe or HIF. */
	md = kzalloc(sizeof(*md), GFP_KERNEL);
	if (!md)
		return -ENOMEM;
	ret = tetris_ccci_mem_prepare(md);
	if (ret)
		goto free_md;
	/* Neither logging nor teardown reads/writes mapped SMEM. The original
	 * provider boot pin keeps mappings/claims alive after this extra ref drops.
	 */
	tetris_ccci_mem_abort(md);
	pr_info("Tetris CCCI: private table copy boundary completed; provider retained; no transport\n");
free_md:
	kfree(md);
	return ret;
}

static void __exit tetris_private_binding_exit(void)
{
	/* Successful init retains no consumer data, mappings or provider lease. */
}

module_init(tetris_private_binding_init);
module_exit(tetris_private_binding_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Tetris checked private SMEM copy lifetime smoke; no modem start");
