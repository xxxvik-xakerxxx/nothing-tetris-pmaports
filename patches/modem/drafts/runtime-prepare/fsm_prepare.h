/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after fsm_main_thread; prepare has no externally published ctl. */
static struct ccci_fsm_ctl *tetris_prepared_fsm;

int ccci_tetris_fsm_prepare(void)
{
	struct ccci_fsm_ctl *ctl;
	int ret;

	if (tetris_prepared_fsm || ccci_fsm_entries)
		return -EALREADY;
	ctl = kzalloc(sizeof(*ctl), GFP_KERNEL);
	if (!ctl)
		return -ENOMEM;
	ctl->last_state = CCCI_FSM_INVALID;
	ctl->curr_state = CCCI_FSM_GATED;
	INIT_LIST_HEAD(&ctl->command_queue);
	INIT_LIST_HEAD(&ctl->event_queue);
	init_waitqueue_head(&ctl->command_wq);
	spin_lock_init(&ctl->event_lock);
	spin_lock_init(&ctl->command_lock);
	spin_lock_init(&ctl->cmd_complete_lock);
	spin_lock_init(&state_broadcase_lock);
	atomic_set(&ctl->fs_ongoing, 0);
	ret = snprintf(ctl->wakelock_name, sizeof(ctl->wakelock_name), "md_wakelock");
	if (ret <= 0 || ret >= (int)sizeof(ctl->wakelock_name)) {
		ret = -EINVAL;
		goto free_ctl;
	}
	ctl->wakelock = wakeup_source_register(NULL, ctl->wakelock_name);
	if (!ctl->wakelock) {
		ret = -ENOMEM;
		goto free_ctl;
	}
	/* A never-woken kthread can be stopped without entering its body. */
	ctl->fsm_thread = kthread_create(fsm_main_thread, ctl, "ccci_fsm");
	if (IS_ERR(ctl->fsm_thread)) {
		ret = PTR_ERR(ctl->fsm_thread);
		wakeup_source_unregister(ctl->wakelock);
		goto free_ctl;
	}
	tetris_prepared_fsm = ctl;
	return 0;
free_ctl:
	kfree(ctl);
	return ret;
}

void ccci_tetris_fsm_abort(void)
{
	struct ccci_fsm_ctl *ctl = tetris_prepared_fsm;

	if (!ctl || ccci_fsm_entries == ctl)
		return;
	kthread_stop(ctl->fsm_thread);
	wakeup_source_unregister(ctl->wakelock);
	kfree(ctl);
	tetris_prepared_fsm = NULL;
}

int ccci_tetris_fsm_commit(void)
{
	struct ccci_fsm_ctl *ctl = tetris_prepared_fsm;
	int ret;

	if (!ctl || ccci_fsm_entries)
		return -EINVAL;
	/* Subordinate vendor initializers expose callbacks. From here retain ctl. */
	ccci_fsm_entries = ctl;
#ifndef CCCI_KMODULE_ENABLE
#ifdef FEATURE_SCP_CCCI_SUPPORT
	fsm_scp_init(&ctl->scp_ctl);
#endif
#endif
	ret = fsm_poller_init(&ctl->poller_ctl);
	if (ret)
		return ret;
	ret = fsm_ee_init(&ctl->ee_ctl);
	if (ret)
		return ret;
	ret = fsm_monitor_init(&ctl->monitor_ctl);
	if (ret)
		return ret;
	return fsm_sys_init();
}

void ccci_tetris_fsm_run(void)
{
	wake_up_process(tetris_prepared_fsm->fsm_thread);
}
