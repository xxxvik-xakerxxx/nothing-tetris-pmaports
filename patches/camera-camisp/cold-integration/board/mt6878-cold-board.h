/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_COLD_BOARD_H
#define MT6878_COLD_BOARD_H
#include "../cold-capture.h"

/* The producer must own a pdev reference, run AFTER this root is bound, and
 * keep its negotiated data stable during publication. Do not hold the root
 * device lock or native capture locks. No platform-data or DT
 * fallback format; no producer memory/DMA addresses are adopted by the root.
 */
int mt6878_cold_board_publish(struct platform_device *pdev,
	const struct mt6878_camsv_job *layout,
	const struct mtkcam_ipi_config_param *config);
/* Actual notifier completion, not resource binding or firmware readiness. */
int mt6878_cold_board_wait(struct platform_device *pdev, unsigned long timeout);
/* Checked one-shot retirement; failure retains the root and all suppliers. */
int mt6878_cold_board_retire(struct platform_device *pdev);
#endif
