/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the B4.1 broadcast implementation; no userspace reset API. */
#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)
void ccci_tetris_events_exit(void)
{
	unsigned int i;

	for (i = 0; i < MD_BC_MAX_NUM; i++) {
		kfree(s_bc_ctl_tbl[i]);
		s_bc_ctl_tbl[i] = NULL;
	}
}

int ccci_tetris_events_init(void)
{
	unsigned int i;

	spin_lock_init(&s_event_update_lock);
	spin_lock_init(&s_md1_user_lock_cnt_lock);
	spin_lock_init(&s_md3_user_lock_cnt_lock);
	for (i = 0; i < MD_BC_MAX_NUM; i++) {
		s_bc_ctl_tbl[i] = kzalloc(sizeof(*s_bc_ctl_tbl[i]), GFP_KERNEL);
		if (!s_bc_ctl_tbl[i]) {
			ccci_tetris_events_exit();
			return -ENOMEM;
		}
		INIT_LIST_HEAD(&s_bc_ctl_tbl[i]->user_list);
		init_waitqueue_head(&s_bc_ctl_tbl[i]->wait);
		s_bc_ctl_tbl[i]->md_bit_mask = i ? BIT(i - 1) : 0x7;
	}
	return 0;
}
#endif
