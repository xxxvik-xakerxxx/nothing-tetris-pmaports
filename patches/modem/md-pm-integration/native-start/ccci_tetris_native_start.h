/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef CCCI_TETRIS_NATIVE_START_H
#define CCCI_TETRIS_NATIVE_START_H
struct device;
struct platform_device;
struct ccci_modem;
struct ccci_hif_ops;
int ccci_tetris_native_probe(struct ccci_modem *md);
int ccci_tetris_native_admit(struct ccci_modem *md);
/* Explicit post-bind caller; success means command queued, never READY. */
int ccci_tetris_native_first_start(struct platform_device *pdev);
int ccci_tetris_native_queue_start(void);
int ccci_tetris_hif_claim(struct platform_device *pdev, unsigned char id);
int ccci_tetris_hif_register(unsigned char id, void *data,
			     struct ccci_hif_ops *ops, struct device *dev);
int ccci_tetris_hif_lock(void);
void ccci_tetris_hif_unlock(void);
int ccci_tetris_hif_start(void);
#endif
