/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, v) (*(p) = (v))
#define cmpxchg(p, old, value) ((*(p) == (old)) ? (*(p) = (value)) : *(p))
#define DEFINE_MUTEX(n) int n
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define atomic_set(p, v) (*(p) = (v))
#define scnprintf snprintf
#define CCIF_HIF_ID 1
#define DPMAIF_HIF_ID 2
#define CLDMA_HIF_ID 0
#define MD1_NORMAL_HIF 1
struct module { int pins; };
static struct module self, providers[2];
#define THIS_MODULE (&self)
#define IS_ENABLED(config) 0
#define EPROBE_DEFER 517
#define EXPORT_SYMBOL_GPL(name)
#define CCCI_KMODULE_ENABLE
struct ccci_hif_ops { struct module *owner; };
static struct ccci_hif_ops hif_ops[2];
static void *ccci_hif[3];
static struct ccci_hif_ops *ccci_hif_op[3];
struct platform_device {
	struct device { void *of_node, *platform_data; uint64_t *dma_mask, coherent_dma_mask;
		bool bound; int lock, devres; } dev;
};
struct ccci_dev_cfg { int capability; };
struct plat_val { int md_gen; };
struct md_hw_info { int md_wdt_irq_id; struct plat_val *plat_val; };
struct md_sys1_info { char peer_wakelock_name[32]; void *peer_wake_lock; };
struct ccci_modem;
struct md_ops { int (*init)(struct ccci_modem *); };
struct ccci_modem {
	unsigned char *private_data;
	struct { int md_capability; } per_md_data;
	struct md_hw_info *hw_info;
	struct platform_device *plat_dev;
	struct md_ops *ops;
	int md_wdt_irq_id, reset_on_going, wdt_enabled;
	unsigned int hif_flag;
	char trm_wakelock_name[32];
	void *trm_wake_lock;
	int kobj;
};
static struct ccci_modem *modem_sys;
static uint64_t mddriver_dmamask;
static int ccci_modem_sysops, fault, allocations, wakes, wake_calls, abort_ports, abort_fsm;
static int fsm_running, ports_running, config_calls, pin_calls, exposed_fault;
static int sysfs_calls;
struct ccci_md_attribute { struct ccci_modem *modem; int attr; };
static struct ccci_md_attribute ccci_md_attr_debug, ccci_md_attr_dump;
static struct ccci_md_attribute ccci_md_attr_net_speed, ccci_md_attr_parameter;
static int ccci_md_ktype;
static int boot_md_show(void) { return 0; }
static int boot_md_store(void) { return 0; }
static int ccci_sysfs_add_modem(void *kobj, void *type, int (*show)(void), int (*store)(void))
{
	assert(kobj && type && show && store);
	return fault == 11 ? -ENODEV : 0;
}
static int sysfs_create_file(void *kobj, void *attr)
{
	assert(kobj && attr);
	sysfs_calls++;
	return fault == 12 && sysfs_calls == 3 ? -ENOSPC : 0;
}
static void mutex_lock(int *lock) { assert(!*lock); *lock = 1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock = 0; }
static int device_trylock(struct device *dev)
{
	if (dev->lock)
		return 0;
	dev->lock = 1;
	return 1;
}
static void device_unlock(struct device *dev) { assert(dev->lock); dev->lock = 0; }
static bool device_is_bound(struct device *dev) { return dev->bound; }
static struct ccci_modem *ccci_md_alloc(int size)
{
	struct ccci_modem *md;
	assert(size == (int)sizeof(struct md_sys1_info));
	if (fault == 1)
		return NULL;
	md = calloc(1, sizeof(*md));
	allocations++;
	if (fault != 2) {
		md->private_data = calloc(1, (size_t)size);
		allocations++;
	}
	return md;
}
static void kfree(void *p) { assert(p); allocations--; free(p); }
static void *wakeup_source_register(void *parent, const char *name)
{
	assert(!parent && name);
	wake_calls++;
	if (fault == wake_calls + 2)
		return NULL;
	wakes++;
	return malloc(1);
}
static void wakeup_source_unregister(void *p) { assert(p); wakes--; free(p); }
static int of_property_read_u32(void *node, const char *name, unsigned int *v)
{
	assert(node && name);
	*v = 6;
	return 0;
}
static int md_init(struct ccci_modem *md) { assert(md); return fault == 7 ? -EIO : 0; }
static struct md_ops md_cd_ops = { .init = md_init };
static int ccci_tetris_fsm_prepare(void) { return fault == 5 ? -EAGAIN : 0; }
static int ccci_tetris_ports_prepare(struct platform_device *p)
{
	assert(p);
	return fault == 6 ? -ENOSPC : 0;
}
static void ccci_tetris_ports_abort(void) { abort_ports++; }
static void ccci_tetris_fsm_abort(void) { abort_fsm++; }
static int ccci_tetris_fsm_commit(void) { return fault == 8 ? -EBADMSG : 0; }
static int ccci_tetris_ports_commit(void) { return fault == 9 ? -ENOSPC : 0; }
static void ccci_tetris_fsm_run(void) { fsm_running++; }
static void ccci_tetris_ports_run(void) { ports_running++; }
static void ccci_md_config(struct ccci_modem *md) { assert(md); config_calls++; }
static void port_kernel_user_interface_init(void *node) { assert(node); }
static int ccci_init(void) { return fault == 13 ? -EIO : 0; }
static void register_syscore_ops(int *ops) { assert(ops); }
static bool try_module_get(struct module *m)
{
	pin_calls++;
	if (fault == 10 && pin_calls == 2)
		return false;
	m->pins++;
	return true;
}
static void module_put(struct module *m) { assert(m->pins); m->pins--; }
static void __module_get(struct module *m) { m->pins++; }
/* PRODUCTION */
static void cold_reset(void)
{
	if (tetris_prepared_md) {
		struct md_sys1_info *info = (struct md_sys1_info *)tetris_prepared_md->private_data;
		free(info->peer_wake_lock);
		free(tetris_prepared_md->trm_wake_lock);
		free(info);
		free(tetris_prepared_md);
	}
	modem_sys = tetris_prepared_md = NULL;
	tetris_commit_attempted = false;
	tetris_registration_attempted = tetris_registration_exposed = tetris_registration_done = false;
	tetris_registration_error = 0;
	allocations = wakes = wake_calls = abort_ports = abort_fsm = 0;
	fsm_running = ports_running = config_calls = pin_calls = 0;
	sysfs_calls = 0;
	self.pins = providers[0].pins = providers[1].pins = 0;
	hif_ops[0].owner = &providers[0];
	hif_ops[1].owner = &providers[1];
	ccci_hif[1] = &providers[0]; ccci_hif[2] = &providers[1];
	ccci_hif_op[1] = &hif_ops[0]; ccci_hif_op[2] = &hif_ops[1];
}
int main(void)
{
	struct platform_device pdev = { .dev = { .of_node = &pdev } };
	struct ccci_dev_cfg cfg = { .capability = 1 };
	struct plat_val generation = { .md_gen = 6297 };
	struct md_hw_info hw = { .md_wdt_irq_id = 4 };
	int i, ret, expected;
	hw.plat_val = &generation;
	cold_reset();
	assert(ccci_tetris_register_prepared(NULL) == -EINVAL);
	assert(ccci_tetris_register_prepared(&pdev) == -ENODEV);
	for (i = 1; i <= 13; i++) {
		cold_reset();
		fault = i;
		pdev.dev.bound = false;
		pdev.dev.platform_data = NULL;
		pdev.dev.devres = 1;
		ret = tetris_common_prepare(&pdev, &cfg, &hw);
		expected = i <= 4 ? -ENOMEM : i == 5 ? -EAGAIN : i == 6 ? -ENOSPC :
			i == 7 || i == 13 ? -EIO : i == 8 ? -EBADMSG : i == 9 || i == 12 ? -ENOSPC : -ENODEV;
		exposed_fault = i == 8 || i == 9 || i == 11 || i == 12 || i == 13;
		if (exposed_fault) {
			/* Successful probe is ONLY private resource preparation. */
			assert(!ret && !modem_sys && !config_calls && !pdev.dev.platform_data);
			assert(!ccci_tetris_registration_retained() && !ccci_tetris_registration_complete());
			assert(ccci_tetris_register_prepared(&pdev) == -EPROBE_DEFER);
			pdev.dev.lock = 1;
			assert(ccci_tetris_register_prepared(&pdev) == -EBUSY);
			pdev.dev.lock = 0;
			pdev.dev.bound = true;
			ret = ccci_tetris_register_prepared(&pdev);
			assert(pdev.dev.bound && pdev.dev.devres == 1);
			assert(ccci_tetris_register_prepared(&pdev) == expected);
		}
		assert(ret == expected && !fsm_running && !ports_running);
		assert(ccci_tetris_registration_retained() == (bool)exposed_fault);
		assert(!ccci_tetris_registration_complete());
		assert(allocations == (exposed_fault ? 2 : 0));
		assert(wakes == (exposed_fault ? 2 : 0));
		assert(config_calls == (exposed_fault && i != 13 ? 1 : 0));
		if (exposed_fault)
			assert(tetris_prepared_md->hw_info == &hw && self.pins == 1);
		assert(tetris_common_prepare(&pdev, &cfg, &hw) == expected);
		assert(ccci_tetris_registration_quarantine(-ETIMEDOUT) == expected);
	}
	cold_reset();
	fault = 0;
	assert(!tetris_common_prepare(&pdev, &cfg, &hw));
	assert(!modem_sys && !config_calls && !ccci_tetris_registration_complete());
	{
		struct platform_device wrong = { .dev = { .bound = true } };
		assert(ccci_tetris_register_prepared(&wrong) == -ENODEV);
		assert(!wrong.dev.lock);
	}
	pdev.dev.bound = true;
	assert(!ccci_tetris_register_prepared(&pdev));
	assert(ccci_tetris_registration_complete() && fsm_running == 1 && ports_running == 1);
	assert(ccci_tetris_registration_retained());
	assert(ccci_tetris_register_prepared(&pdev) == -EALREADY);
	assert(tetris_common_prepare(&pdev, &cfg, &hw) == -EALREADY);
	assert(ccci_tetris_registration_quarantine(-EOPNOTSUPP) == -EOPNOTSUPP);
	assert(!ccci_tetris_registration_complete());
	assert(ccci_tetris_registration_quarantine(-EIO) == -EOPNOTSUPP);
	cold_reset();
	return 0;
}
