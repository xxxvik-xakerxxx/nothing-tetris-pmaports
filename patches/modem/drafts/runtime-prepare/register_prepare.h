/* SPDX-License-Identifier: GPL-2.0-only */
/* Included in modem_sys1.c; all publication is marked before vendor callbacks. */
#include "ccci_hif_internal.h"
#include <linux/mutex.h>
static bool tetris_registration_attempted;
static bool tetris_registration_exposed;
static bool tetris_registration_done;
static bool tetris_commit_attempted;
static struct ccci_modem *tetris_prepared_md;
static int tetris_registration_error;
static DEFINE_MUTEX(tetris_registration_lock);
static struct module *tetris_registration_hif_modules[2];

static int tetris_pin_hif_modules(void)
{
	static const unsigned int ids[] = { CCIF_HIF_ID, DPMAIF_HIF_ID };
	struct ccci_hif_ops *ops;
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(ids); i++) {
		ops = READ_ONCE(ccci_hif_op[ids[i]]);
		if (!READ_ONCE(ccci_hif[ids[i]]) || !ops || !ops->owner ||
		    !try_module_get(ops->owner)) {
			while (i) {
				i--;
				module_put(tetris_registration_hif_modules[i]);
				tetris_registration_hif_modules[i] = NULL;
			}
			return -ENODEV;
		}
		tetris_registration_hif_modules[i] = ops->owner;
	}
	return 0;
}

int ccci_tetris_registration_quarantine(int error)
{
	int failure = error < 0 ? error : -EPROTO;

	cmpxchg(&tetris_registration_error, 0, failure);
	smp_store_release(&tetris_registration_done, false);
	return READ_ONCE(tetris_registration_error);
}

bool ccci_tetris_registration_complete(void)
{
	return smp_load_acquire(&tetris_registration_done);
}

bool ccci_tetris_registration_retained(void)
{
	return READ_ONCE(tetris_registration_exposed);
}

static int tetris_sysfs_register(struct ccci_modem *md)
{
	struct ccci_md_attribute * const attrs[] = {
		&ccci_md_attr_debug, &ccci_md_attr_dump,
		&ccci_md_attr_net_speed, &ccci_md_attr_parameter,
	};
	unsigned int i;
	int ret;

	ret = ccci_sysfs_add_modem(&md->kobj, &ccci_md_ktype, boot_md_show, boot_md_store);
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(attrs); i++) {
		attrs[i]->modem = md;
		ret = sysfs_create_file(&md->kobj, &attrs[i]->attr);
		if (ret)
			return ret;
	}
	return 0;
}

static int tetris_common_prepare_locked(struct platform_device *pdev,
		struct ccci_dev_cfg *cfg, struct md_hw_info *hw)
{
	struct ccci_modem *md;
	struct md_sys1_info *info;
	int ret;

	/* Platform singleton probe owns this transaction; no retry after exposure. */
	if (tetris_registration_attempted)
		return tetris_registration_error ? tetris_registration_error : -EALREADY;
	tetris_registration_attempted = true;
#if IS_ENABLED(CONFIG_MTK_SLBC)
	/* Its void registration wrapper discards callback failures; no safe inverse. */
	ret = -EOPNOTSUPP;
	goto fault;
#endif
#if !defined(CCCI_KMODULE_ENABLE) && defined(FEATURE_SCP_CCCI_SUPPORT)
	/* fsm_scp_init is outside this bounded ownership graph. */
	ret = -EOPNOTSUPP;
	goto fault;
#endif
	md = ccci_md_alloc(sizeof(*info));
	if (!md) {
		ret = -ENOMEM;
		goto fault;
	}
	if (!md->private_data) {
		ret = -ENOMEM;
		goto free_md;
	}
	info = md->private_data;
	md->per_md_data.md_capability = cfg->capability;
	md->hw_info = hw;
	md->plat_dev = pdev;
	pdev->dev.dma_mask = &mddriver_dmamask;
	pdev->dev.coherent_dma_mask = mddriver_dmamask;
	md->ops = &md_cd_ops;
	md->md_wdt_irq_id = hw->md_wdt_irq_id;
	atomic_set(&md->reset_on_going, 1);
	atomic_set(&md->wdt_enabled, 0);
	ret = of_property_read_u32(pdev->dev.of_node, "mediatek,mdhif-type", &md->hif_flag);
	if (ret)
		md->hif_flag = hw->plat_val->md_gen < 6295 ?
			(1 << CLDMA_HIF_ID | 1 << MD1_NORMAL_HIF) :
			(1 << DPMAIF_HIF_ID | 1 << MD1_NORMAL_HIF);
	scnprintf(md->trm_wakelock_name, sizeof(md->trm_wakelock_name), "md_cldma_trm");
	md->trm_wake_lock = wakeup_source_register(NULL, md->trm_wakelock_name);
	if (!md->trm_wake_lock) {
		ret = -ENOMEM;
		goto free_private;
	}
	scnprintf(info->peer_wakelock_name, sizeof(info->peer_wakelock_name), "md_cldma_peer");
	info->peer_wake_lock = wakeup_source_register(NULL, info->peer_wakelock_name);
	if (!info->peer_wake_lock) {
		ret = -ENOMEM;
		goto free_trm;
	}
	ret = ccci_tetris_fsm_prepare();
	if (ret)
		goto free_peer;
	ret = ccci_tetris_ports_prepare(pdev);
	if (ret)
		goto abort_fsm;
	/* Never call the legacy ccci_md_register publication/unchecked init body. */
	ret = md->ops->init(md);
	if (ret)
		goto abort_ports;
	ret = tetris_pin_hif_modules();
	if (ret)
		goto abort_ports;
	/* Empty vendor module exits cannot safely release published callbacks. */
	__module_get(THIS_MODULE);
	/* Successful probe means ONLY privately prepared resources. No publication.
	 * No subsequent fallible operation may run in this probe path. */
	tetris_prepared_md = md;
	return 0;
abort_ports:
	ccci_tetris_ports_abort();
abort_fsm:
	ccci_tetris_fsm_abort();
free_peer:
	wakeup_source_unregister(info->peer_wake_lock);
free_trm:
	wakeup_source_unregister(md->trm_wake_lock);
free_private:
	kfree(md->private_data);
free_md:
	kfree(md);
fault:
	return ccci_tetris_registration_quarantine(ret);
}

static int tetris_common_prepare(struct platform_device *pdev,
		struct ccci_dev_cfg *cfg, struct md_hw_info *hw)
{
	int ret;

	mutex_lock(&tetris_registration_lock);
	ret = tetris_common_prepare_locked(pdev, cfg, hw);
	mutex_unlock(&tetris_registration_lock);
	return ret;
}

int ccci_tetris_register_prepared(struct platform_device *pdev)
{
	struct ccci_modem *md;
	int ret;

	if (!pdev)
		return -EINVAL;
	/* Same order as driver core probe: device lock, then private transaction lock.
	 * Bind/unbind stays excluded throughout commit and its failure quarantine. */
	/* A mistaken in-probe caller must fail rather than recursively deadlock. */
	if (!device_trylock(&pdev->dev))
		return -EBUSY;
	mutex_lock(&tetris_registration_lock);
	md = tetris_prepared_md;
	if (!md || md->plat_dev != pdev) {
		ret = -ENODEV;
		goto out;
	}
	if (!device_is_bound(&pdev->dev)) {
		ret = -EPROBE_DEFER;
		goto out;
	}
	if (tetris_commit_attempted) {
		ret = tetris_registration_error ? tetris_registration_error : -EALREADY;
		goto out;
	}
	tetris_commit_attempted = true;
	/* This is NOT a probe return path. Failure leaves the already-bound device
	 * and its devres/clocks intact, with the original error returned to caller. */
	WRITE_ONCE(tetris_registration_exposed, true);
#ifdef CCCI_KMODULE_ENABLE
	ret = ccci_init();
	if (ret)
		goto fault;
#endif
	ccci_md_config(md);
	modem_sys = md;
	pdev->dev.platform_data = md;
	ret = ccci_tetris_fsm_commit();
	if (ret)
		goto fault;
	ret = ccci_tetris_ports_commit();
	if (ret)
		goto fault;
	port_kernel_user_interface_init(pdev->dev.of_node);
	ret = tetris_sysfs_register(md);
	if (ret)
		goto fault;
	register_syscore_ops(&ccci_modem_sysops);
	smp_store_release(&tetris_registration_done, true);
	ccci_tetris_ports_run();
	ccci_tetris_fsm_run();
	ret = 0;
	goto out;
fault:
	ret = ccci_tetris_registration_quarantine(ret);
out:
	mutex_unlock(&tetris_registration_lock);
	device_unlock(&pdev->dev);
	return ret;
}
EXPORT_SYMBOL_GPL(ccci_tetris_register_prepared);
