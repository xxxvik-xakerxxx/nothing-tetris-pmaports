/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_CCCI_IMAGE_UTIL_API_H
#define TETRIS_CCCI_IMAGE_UTIL_API_H
#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)
int ccci_tetris_log_init(void);
void ccci_tetris_log_exit(void);
int ccci_tetris_events_init(void);
void ccci_tetris_events_exit(void);
int ccci_tetris_pin_init(void);
void ccci_tetris_pin_exit(void);
void ccci_tetris_sysfs_exit(void);
#endif
#endif
