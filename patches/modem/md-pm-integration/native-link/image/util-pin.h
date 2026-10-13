/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the B4.1 pin broadcaster; allocate its genuine event object. */
#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)
void ccci_tetris_pin_exit(void)
{
	kfree(pin_event);
	pin_event = NULL;
}

int ccci_tetris_pin_init(void)
{
	spin_lock_init(&pin_event_update_lock);
	init_waitqueue_head(&pin_event_wait);
	INIT_LIST_HEAD(&user_list);
	pin_event = kzalloc(sizeof(*pin_event), GFP_KERNEL);
	return pin_event ? 0 : -ENOMEM;
}
#endif
