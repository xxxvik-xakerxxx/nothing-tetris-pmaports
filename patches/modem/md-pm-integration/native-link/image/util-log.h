/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after the B4.1 private logger's real buffer definitions. */
#if IS_ENABLED(CONFIG_MTK_ECCCI_TETRIS_NATIVE_START)
void ccci_tetris_log_exit(void)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(node_array); i++) {
		struct ccci_dump_buffer *ptr = node_array[i].ctlb_ptr;

		if (!ptr)
			continue;
		kfree(ptr->buffer);
		ptr->buffer = NULL;
		ptr->buf_size = 0;
	}
	vfree(ccci_event_buffer.buffer);
	ccci_event_buffer.buffer = NULL;
	ccci_event_buffer.buf_size = 0;
	kfree(ccci_log_buf.buffer);
	ccci_log_buf.buffer = NULL;
}

int ccci_tetris_log_init(void)
{
	unsigned int i;

	/* Module init precedes all dependent modules. Do not publish vendor proc
	 * callbacks before their locks/buffers exist, or conceal allocation errors.
	 */
	spin_lock_init(&ccci_log_buf.write_lock);
	init_waitqueue_head(&ccci_log_buf.log_wq);
	atomic_set(&ccci_log_buf.reader_cnt, 0);
	spin_lock_init(&file_lock);
	spin_lock_init(&ccci_event_buffer.lock);
	ccci_log_buf.buffer = kzalloc(CCCI_LOG_BUF_SIZE, GFP_KERNEL);
	if (!ccci_log_buf.buffer)
		goto fail;
	ccci_event_buffer.buffer = vzalloc(CCCI_EVENT_BUF_SIZE);
	if (!ccci_event_buffer.buffer)
		goto fail;
	ccci_event_buffer.buf_size = CCCI_EVENT_BUF_SIZE;
	for (i = 0; i < ARRAY_SIZE(node_array); i++) {
		struct ccci_dump_buffer *ptr = node_array[i].ctlb_ptr;

		if (!ptr)
			continue;
		spin_lock_init(&ptr->lock);
		if (!node_array[i].init_size)
			continue;
		ptr->buffer = kzalloc(node_array[i].init_size, GFP_KERNEL);
		if (!ptr->buffer)
			goto fail;
		ptr->buf_size = node_array[i].init_size;
		ptr->attr = node_array[i].init_attr;
	}
	return 0;
fail:
	ccci_tetris_log_exit();
	return -ENOMEM;
}
#endif
