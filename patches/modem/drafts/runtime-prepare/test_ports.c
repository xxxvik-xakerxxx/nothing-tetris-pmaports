/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#define GFP_KERNEL 0
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define INIT_LIST_HEAD(p) ((void)(p))
#define spin_lock_init(p) ((void)(p))
#define MKDEV(major, minor) ((unsigned int)(major) * 256 + (minor))
#define CCCI_SYSTEM_TX 1
#define CCCI_CONTROL_TX 2
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
struct task_struct { bool running; };
struct port_t;
struct port_ops { int (*init)(struct port_t *); };
struct port_t {
	struct port_ops *ops;
	void *rx_wakelock, *port_proxy;
	unsigned int major, minor_base;
	int flag_lock, tx_ch;
	const char *name;
	struct task_struct *owned_worker;
};
struct port_proxy {
	unsigned int major, minor_base;
	int port_number, rx_ch_ports[4];
	struct port_t *ports, *sys_port, *ctl_port;
};
struct platform_device { struct { void *of_node; } dev; };
static struct port_proxy *port_proxyp;
static struct port_t configured[8];
static unsigned int port_md_gen;
static int fault, fail_index, prepared, allocations, wakes, regions, calls, mappings, starts;
static void *kzalloc(size_t size, int flags)
{
	(void)flags;
	if (fault == 1)
		return NULL;
	allocations++;
	return calloc(1, size);
}
static void kfree(void *p) { allocations--; free(p); }
static int of_property_read_u32(void *node, const char *name, unsigned int *value)
{
	assert(node && !strcmp(name, "mediatek,md-generation"));
	if (fault == 2)
		return -EINVAL;
	*value = 6297;
	return 0;
}
static int port_get_cfg(struct port_t **ports) { *ports = configured; return 8; }
static int proxy_register_char_dev(struct port_proxy *proxy)
{
	if (fault == 3)
		return -ENOSPC;
	proxy->major = 10;
	regions++;
	return 0;
}
static void unregister_chrdev_region(unsigned int number, unsigned int count)
{
	assert(number == 2560 && count == 120);
	regions--;
}
static int port_struct_init(struct port_t *port, struct port_proxy *proxy)
{
	port->port_proxy = proxy;
	if (fault == 4 && prepared == fail_index)
		return -ENOMEM;
	prepared++;
	wakes++;
	port->rx_wakelock = malloc(1);
	return 0;
}
static void wakeup_source_unregister(void *p) { wakes--; free(p); }
static void proxy_setup_channel_mapping(struct port_proxy *p) { assert(p); mappings++; }
static struct task_struct *kthread_create(int (*body)(void *), void *port,
		const char *format, const char *name)
{
	assert(body && port && format && name);
	if (fault == 6)
		return ERR_PTR(-EAGAIN);
	return calloc(1, sizeof(struct task_struct));
}
static void wake_up_process(struct task_struct *task) { task->running = true; starts++; }
static void kthread_stop(struct task_struct *task) { assert(!task->running); free(task); }
static int ccci_tetris_proc_publish(void) { return fault == 7 ? -ENOMEM : 0; }
/* PRODUCTION */
static int handler(void *p) { (void)p; return 0; }
static int actual_boundary_init(struct port_t *port)
{
	int index = (int)(port - configured);
	calls++;
	if (fault == 5 && index == fail_index)
		return -EIO;
	/* Boundary double, not a fabricated replacement channel/port algorithm. */
	return 0;
}
static struct port_ops ops = { .init = actual_boundary_init };
static void reset(void)
{
	int i;
	if (tetris_prepared_proxy) {
		for (i = 0; i < 8; i++) {
			free(configured[i].rx_wakelock);
			free(configured[i].owned_worker);
		}
		free(tetris_prepared_proxy);
	}
	memset(configured, 0, sizeof(configured));
	for (i = 0; i < 8; i++) {
		configured[i].ops = &ops;
		configured[i].name = "boundary";
	}
	configured[0].tx_ch = CCCI_SYSTEM_TX;
	configured[1].tx_ch = CCCI_CONTROL_TX;
	port_proxyp = tetris_prepared_proxy = NULL;
	tetris_prepared_ports = 0;
	fault = prepared = allocations = wakes = regions = calls = mappings = starts = 0;
}
int main(void)
{
	struct platform_device pdev = { .dev = { .of_node = &pdev } };
	int i, ret;
	reset();
	for (i = 1; i <= 4; i++) {
		fault = i;
		fail_index = 5;
		ret = ccci_tetris_ports_prepare(&pdev);
		assert(ret == (i == 1 || i == 4 ? -ENOMEM : i == 2 ? -EINVAL : -ENOSPC));
		assert(!allocations && !wakes && !regions && !calls);
		reset();
	}
	for (i = 0; i < 8; i++) {
		assert(!ccci_tetris_ports_prepare(&pdev));
		fault = 5;
		fail_index = i;
		assert(ccci_tetris_ports_commit() == -EIO);
		ccci_tetris_ports_abort();
		assert(allocations == 1 && wakes == 8 && regions == 1 && calls == i + 1);
		assert(!mappings && !starts);
		reset();
	}
	assert(!ccci_tetris_ports_prepare(&pdev));
	fault = 6;
	assert(IS_ERR(ccci_tetris_port_worker(&configured[0], handler)));
	assert(!configured[0].owned_worker);
	fault = 0;
	assert(!IS_ERR(ccci_tetris_port_worker(&configured[0], handler)));
	assert(IS_ERR(ccci_tetris_port_worker(&configured[0], handler)));
	assert(!starts);
	assert(!ccci_tetris_ports_commit());
	ccci_tetris_ports_run();
	assert(starts == 1 && mappings == 1);
	reset();
	assert(!ccci_tetris_ports_prepare(&pdev));
	fault = 7;
	assert(ccci_tetris_ports_commit() == -ENOMEM);
	ccci_tetris_ports_abort();
	assert(allocations == 1 && wakes == 8 && regions == 1 && !starts);
	reset();
	assert(!ccci_tetris_ports_prepare(&pdev));
	ccci_tetris_ports_abort();
	assert(!allocations && !wakes && !regions);
	reset();
	return 0;
}
