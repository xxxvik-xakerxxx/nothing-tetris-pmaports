/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef CCCI_TETRIS_PREPARE_H
#define CCCI_TETRIS_PREPARE_H
struct platform_device;
struct port_t;
int ccci_tetris_fsm_prepare(void);
void ccci_tetris_fsm_abort(void);
int ccci_tetris_fsm_commit(void);
void ccci_tetris_fsm_run(void);
int ccci_tetris_ports_prepare(struct platform_device *);
void ccci_tetris_ports_abort(void);
int ccci_tetris_ports_commit(void);
int ccci_tetris_proc_publish(void);
void ccci_tetris_ports_run(void);
struct task_struct *ccci_tetris_port_worker(struct port_t *, int (*)(void *));
bool ccci_tetris_registration_complete(void);
bool ccci_tetris_registration_retained(void);
int ccci_tetris_registration_quarantine(int);
/* Explicit post-bind operation; never call from probe or an init callback. */
int ccci_tetris_register_prepared(struct platform_device *);
#endif
