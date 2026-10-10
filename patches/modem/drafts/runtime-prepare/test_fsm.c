/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#define GFP_KERNEL 0
#define CCCI_FSM_INVALID 0
#define CCCI_FSM_GATED 1
#define CCCI_KMODULE_ENABLE
#define INIT_LIST_HEAD(p) ((void)(p))
#define init_waitqueue_head(p) ((void)(p))
#define spin_lock_init(p) ((void)(p))
#define atomic_set(p, n) (*(p) = (n))
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
struct task_struct { bool running; };
struct ccci_fsm_ctl {
	int last_state, curr_state, command_queue, event_queue, command_wq;
	int event_lock, command_lock, cmd_complete_lock, fs_ongoing;
	int poller_ctl, ee_ctl, monitor_ctl;
	char wakelock_name[32];
	void *wakelock;
	struct task_struct *fsm_thread;
};
static struct ccci_fsm_ctl *ccci_fsm_entries;
static int state_broadcase_lock, fault, allocations, wakes, tasks, starts, stops;
static void *kzalloc(size_t size, int flags)
{
	(void)flags;
	if (fault == 1)
		return NULL;
	allocations++;
	return calloc(1, size);
}
static void kfree(void *p) { allocations--; free(p); }
static void *wakeup_source_register(void *p, const char *name)
{
	assert(!p && name);
	if (fault == 2)
		return NULL;
	wakes++;
	return malloc(1);
}
static void wakeup_source_unregister(void *p) { wakes--; free(p); }
static int fsm_main_thread(void *p) { (void)p; return 0; }
static struct task_struct *kthread_create(int (*body)(void *), void *p, const char *name)
{
	assert(body == fsm_main_thread && p && name);
	if (fault == 3)
		return (void *)(intptr_t)-EAGAIN;
	tasks++;
	return calloc(1, sizeof(struct task_struct));
}
static void kthread_stop(struct task_struct *p)
{
	assert(!p->running);
	stops++;
	tasks--;
	free(p);
}
static void wake_up_process(struct task_struct *p) { p->running = true; starts++; }
static int fsm_poller_init(int *p) { assert(p); return fault == 4 ? -ENOSPC : 0; }
static int fsm_ee_init(int *p) { assert(p); return fault == 5 ? -EIO : 0; }
static int fsm_monitor_init(int *p) { assert(p); return fault == 6 ? -ENOMEM : 0; }
static int fsm_sys_init(void) { return fault == 7 ? -EINVAL : 0; }
/* PRODUCTION */
static void cold_fixture_reset(void)
{
	if (ccci_fsm_entries) {
		/* Fixture-only destruction of retained mock allocations, no live device. */
		free(ccci_fsm_entries->fsm_thread);
		free(ccci_fsm_entries->wakelock);
		free(ccci_fsm_entries);
	}
	ccci_fsm_entries = tetris_prepared_fsm = NULL;
	allocations = wakes = tasks = starts = stops = 0;
}
int main(void)
{
	int i, ret;
	for (i = 1; i <= 7; i++) {
		fault = i;
		ret = ccci_tetris_fsm_prepare();
		if (i <= 3) {
			assert(ret == (i == 3 ? -EAGAIN : -ENOMEM));
			assert(!allocations && !wakes && !tasks && !tetris_prepared_fsm);
		} else {
			assert(!ret && !starts);
			assert(ccci_tetris_fsm_prepare() == -EALREADY);
			assert(ccci_tetris_fsm_commit() ==
			       (i == 4 ? -ENOSPC : i == 5 ? -EIO : i == 6 ? -ENOMEM : -EINVAL));
			ccci_tetris_fsm_abort();
			assert(allocations == 1 && wakes == 1 && tasks == 1 && !starts && !stops);
		}
		cold_fixture_reset();
	}
	fault = 0;
	assert(!ccci_tetris_fsm_prepare());
	ccci_tetris_fsm_abort();
	assert(!allocations && !wakes && !tasks && stops == 1);
	assert(!ccci_tetris_fsm_prepare());
	assert(!ccci_tetris_fsm_commit());
	ccci_tetris_fsm_run();
	assert(starts == 1);
	cold_fixture_reset();
	return 0;
}
