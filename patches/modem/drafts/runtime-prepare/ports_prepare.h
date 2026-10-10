/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after proxy_register_char_dev; exact configured port_get_cfg table. */
static struct port_proxy *tetris_prepared_proxy;
static unsigned int tetris_prepared_ports;

void ccci_tetris_ports_abort(void)
{
	struct port_proxy *proxy = tetris_prepared_proxy;
	struct port_t *port;

	if (!proxy || port_proxyp == proxy)
		return;
	while (tetris_prepared_ports) {
		port = &proxy->ports[--tetris_prepared_ports];
		if (port->owned_worker) {
			kthread_stop(port->owned_worker);
			port->owned_worker = NULL;
		}
		wakeup_source_unregister(port->rx_wakelock);
		port->rx_wakelock = NULL;
		port->port_proxy = NULL;
	}
	unregister_chrdev_region(MKDEV(proxy->major, proxy->minor_base), 120);
	kfree(proxy);
	tetris_prepared_proxy = NULL;
}

int ccci_tetris_ports_prepare(struct platform_device *pdev)
{
	struct port_proxy *proxy;
	struct port_t *port;
	int i, ret;

	if (tetris_prepared_proxy || port_proxyp)
		return -EALREADY;
	ret = of_property_read_u32(pdev->dev.of_node, "mediatek,md-generation", &port_md_gen);
	if (ret)
		return ret;
	proxy = kzalloc(sizeof(*proxy), GFP_KERNEL);
	if (!proxy)
		return -ENOMEM;
	proxy->port_number = port_get_cfg(&proxy->ports);
	if (proxy->port_number <= 0 || !proxy->ports) {
		kfree(proxy);
		return -EINVAL;
	}
	ret = proxy_register_char_dev(proxy);
	if (ret) {
		kfree(proxy);
		return ret;
	}
	tetris_prepared_proxy = proxy;
	for (i = 0; i < (int)ARRAY_SIZE(proxy->rx_ch_ports); i++)
		INIT_LIST_HEAD(&proxy->rx_ch_ports[i]);
	for (i = 0; i < proxy->port_number; i++) {
		port = &proxy->ports[i];
		if (!port->ops || !port->ops->init) {
			ret = -EINVAL;
			goto fail;
		}
		ret = port_struct_init(port, proxy);
		if (ret) {
			/* The failing initializer has not acquired a wake source. */
			port->port_proxy = NULL;
			goto fail;
		}
		tetris_prepared_ports++;
		spin_lock_init(&port->flag_lock);
		port->major = proxy->major;
		port->minor_base = proxy->minor_base;
		port->owned_worker = NULL;
		if (port->tx_ch == CCCI_SYSTEM_TX)
			proxy->sys_port = port;
		if (port->tx_ch == CCCI_CONTROL_TX)
			proxy->ctl_port = port;
	}
	return 0;
fail:
	ccci_tetris_ports_abort();
	return ret;
}

struct task_struct *ccci_tetris_port_worker(struct port_t *port, int (*body)(void *))
{
	struct task_struct *worker;

	if (port->owned_worker)
		return ERR_PTR(-EALREADY);
	worker = kthread_create(body, port, "%s", port->name);
	if (!IS_ERR(worker))
		port->owned_worker = worker;
	return worker;
}

int ccci_tetris_ports_commit(void)
{
	struct port_proxy *proxy = tetris_prepared_proxy;
	int i, ret;

	if (!proxy || port_proxyp)
		return -EINVAL;
	/* Actual ops may register netdev/cdev/SWTP/IPC callbacks: retain on failure. */
	port_proxyp = proxy;
	for (i = 0; i < proxy->port_number; i++) {
		ret = proxy->ports[i].ops->init(&proxy->ports[i]);
		if (ret)
			return ret < 0 ? ret : -EPROTO;
	}
	proxy_setup_channel_mapping(proxy);
	return ccci_tetris_proc_publish();
}

void ccci_tetris_ports_run(void)
{
	int i;

	for (i = 0; i < tetris_prepared_proxy->port_number; i++)
		if (tetris_prepared_proxy->ports[i].owned_worker)
			wake_up_process(tetris_prepared_proxy->ports[i].owned_worker);
}
