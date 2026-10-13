// SPDX-License-Identifier: GPL-2.0-only
#include <linux/arm-smccc.h>
#include <linux/device.h>
#include <linux/delay.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/suspend.h>
#include <linux/soc/mediatek/mt6878_md_native_on.h>
#include "ccci_config.h"
#include "ccci_core.h"
#include "ccci_modem.h"
#include "modem_sys.h"
#include "ccci_hif.h"
#include "ccci_tetris_owner.h"
#include "ccci_tetris_prepare.h"
#include "ccci_tetris_native_start.h"
#include "md_sys1_platform.h"
#include "modem_secure_base.h"
#include "mt-plat/tetris_ccci_smem.h"

static DEFINE_MUTEX(native_start_lock);
static struct {
	struct ccci_modem *md;
	struct device *dev;
	int first_error;
	unsigned int step;
	struct arm_smccc_res power0;
	struct arm_smccc_res brom_done, brom_flags;
} native_start;

static int native_fault(int error)
{
	if (!native_start.first_error)
		native_start.first_error = error < 0 ? error : -EPROTO;
	if (native_start.dev)
		mt6878_md_native_on_latch(native_start.dev, native_start.first_error);
	return native_start.first_error;
}

/* Both providers own their live state. No caller supplies a verify callback. */
int ccci_tetris_native_admit(struct ccci_modem *md)
{
	if (!md || !md->plat_dev || !md->hw_info || !md->hw_info->plat_val ||
	    !md->tetris_smem || !md->tetris_smem->provider)
		return -ENODATA;
	if (md->hw_info->plat_val->md_gen != 6299 ||
	    md->hw_info->plat_val->power_flow_config ||
	    md->hif_flag != (BIT(CCIF_HIF_ID) | BIT(DPMAIF_HIF_ID)) ||
	    md->mem_layout.md_bank4_noncacheable != md->tetris_smem->nc ||
	    md->mem_layout.md_bank4_cacheable != md->tetris_smem->cache)
		return -EXDEV;
	return mt6878_md_native_on_validate(&md->plat_dev->dev);
}

/* Last fallible unpublished prepare operation, not START or registration. */
int ccci_tetris_native_probe(struct ccci_modem *md)
{
	struct device *dev;
	int ret;

	if (!md || !md->plat_dev)
		return -EINVAL;
	dev = &md->plat_dev->dev;
	mutex_lock(&native_start_lock);
	if (native_start.md || native_start.first_error) {
		ret = native_start.first_error ? native_start.first_error : -EALREADY;
		goto out;
	}
	ret = ccci_tetris_native_admit(md);
	if (ret)
		goto out;
	/* Platform attach already performed genuine ON. Set only PM accounting,
	 * while runtime PM is disabled; pin before enable so idle cannot race. */
	if (pm_runtime_enabled(dev)) {
		ret = -EBUSY;
		goto out;
	}
	ret = pm_runtime_set_active(dev);
	if (ret)
		goto out;
	pm_runtime_get_noresume(dev);
	pm_runtime_enable(dev);
	native_start.dev = get_device(dev);
	native_start.md = md;
	__module_get(THIS_MODULE);
out:
	mutex_unlock(&native_start_lock);
	return ret;
}

int ccci_tetris_owner_entry(void)
{
	int ret;

	mutex_lock(&native_start_lock);
	ret = native_start.first_error;
	if (!ret && (!native_start.md || !ccci_tetris_registration_complete()))
		ret = -ENODEV;
	if (!ret && native_start.step)
		ret = -EALREADY;
	mutex_unlock(&native_start_lock);
	return ret;
}

int ccci_tetris_owner_latch(int error)
{
	int ret;

	mutex_lock(&native_start_lock);
	ret = native_fault(error);
	mutex_unlock(&native_start_lock);
	return ret;
}

/* Preserve md_start_platform's bounded BROM queries, not its legacy OFF tail.
 * SHA05a247 POWER/3 is a predicate, NOT status=error: 1 means not done.
 * POWER/2 defines all four flag cells; each must actually equal one. */
static int native_brom_check(void)
{
	unsigned int remaining;

	for (remaining = 100; remaining; remaining--) {
		arm_smccc_smc(MTK_SIP_KERNEL_CCCI_CONTROL, MD_POWER_CONFIG,
			      MD_CHECK_DONE, 0, 0, 0, 0, 0, &native_start.brom_done);
		if (!native_start.brom_done.a0)
			break;
		if (native_start.brom_done.a0 != 1)
			return -EIO;
		msleep(20);
	}
	if (!remaining)
		return -ETIMEDOUT;
	arm_smccc_smc(MTK_SIP_KERNEL_CCCI_CONTROL, MD_POWER_CONFIG,
		      MD_CHECK_FLAG, 0, 0, 0, 0, 0, &native_start.brom_flags);
	if (native_start.brom_flags.a0 != 1 || native_start.brom_flags.a1 != 1 ||
	    native_start.brom_flags.a2 != 1 || native_start.brom_flags.a3 != 1)
		return -EPROTO;
	return 0;
}

int ccci_tetris_owner_start(struct ccci_modem *md)
{
	struct device *dev;
	unsigned int sleep_flags;
	int ret;

	/* Device -> transaction -> HIF device locks. Never wait for the FSM while
	 * holding them; the explicit queue adapter below does not hold these locks. */
	if (!md || !md->plat_dev)
		return -EINVAL;
	dev = &md->plat_dev->dev;
	/* Public exported API; system_transition_mutex itself is NOT exported.
	 * Acquire before device locks to avoid inversion with system suspend. */
	sleep_flags = lock_system_sleep();
	if (!device_trylock(dev)) {
		unlock_system_sleep(sleep_flags);
		return -EBUSY;
	}
	mutex_lock(&native_start_lock);
	if (native_start.first_error) {
		ret = native_start.first_error;
		goto out;
	}
	if (native_start.md != md || native_start.dev != dev ||
	    !device_is_bound(dev) || !ccci_tetris_registration_complete()) {
		ret = -ENODEV;
		goto fault;
	}
	if (native_start.step) {
		ret = -EALREADY;
		goto out;
	}
	native_start.step = 1;
	ret = ccci_tetris_native_admit(md);
	if (ret)
		goto transition;
	/* A real reference to the real platform consumer, not a virtual OFF cycle.
	 * Positive runtime-PM success is valid; retain every acquired ref on failure. */
	native_start.step = 2;
	ret = pm_runtime_resume_and_get(dev);
	if (ret < 0)
		goto transition;
	ret = ccci_tetris_native_admit(md);
	if (ret)
		goto transition;
	native_start.step = 3;
	ret = native_brom_check();
	if (ret)
		goto transition;
	ret = ccci_tetris_hif_lock();
	if (ret)
		goto transition;
	native_start.step = 4;
	ret = ccci_tetris_wdt_init_owned(md);
	if (ret)
		goto hif;
	native_start.step = 5;
	ret = ccci_tetris_hif_start();
	if (ret)
		goto hif;
	native_start.step = 6;
	ret = ccci_tetris_publish_hs1();
	if (ret)
		goto hif;
	ret = ccci_tetris_native_admit(md);
	if (ret)
		goto hif;
	if (MD_IN_DEBUG(md)) {
		ret = -EBUSY;
		goto hif;
	}
	native_start.step = 7;
	arm_smccc_smc(MTK_SIP_KERNEL_CCCI_CONTROL, MD_POWER_CONFIG,
		      MD_KERNEL_BOOT_UP, 0, 0, 0, 0, 0, &native_start.power0);
	/* SHA05a247 POWER/0: a0=status, a1/a2=boot-status words, a3=boot-slave
	 * register readback. The status words are not four BROM completion flags. */
	dev_info(dev, "MD POWER/0: status=%#lx boot-status=%#lx/%#lx boot-slave=%#lx\n",
		 native_start.power0.a0, native_start.power0.a1,
		 native_start.power0.a2, native_start.power0.a3);
	ret = native_start.power0.a0 ? -EIO :
		(native_start.power0.a3 != 1 ? -EPROTO : 0);
	if (ret)
		goto hif;
	native_start.step = 8;
	md->per_md_data.config.setting &= ~MD_SETTING_FIRST_BOOT;
	atomic_set(&md->reset_on_going, 0);
	md->per_md_data.is_in_ee_dump = 0;
	md->is_force_asserted = 0;
	wdt_enable_irq(md);
	/* Genuine receive IRQ/port/FSM events still own HS1, HS2 and READY. */
hif:
	ccci_tetris_hif_unlock();
transition:
	if (ret)
		goto fault;
	goto out;
fault:
	ret = native_fault(ret);
out:
	mutex_unlock(&native_start_lock);
	device_unlock(dev);
	unlock_system_sleep(sleep_flags);
	return ret;
}

int ccci_tetris_native_first_start(struct platform_device *pdev)
{
	int ret;

	/* Never called by probe/module init. Existing prepared commit owns its
	 * device lock and error retention; only then enqueue the real FSM command. */
	ret = ccci_tetris_register_prepared(pdev);
	if (ret)
		return ret;
	ret = ccci_tetris_native_queue_start();
	return ret ? ccci_tetris_owner_latch(ret) : 0;
}
EXPORT_SYMBOL_GPL(ccci_tetris_native_first_start);
