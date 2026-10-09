// SPDX-License-Identifier: GPL-2.0-only
#include <linux/device.h>
#include <linux/err.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/pm_runtime.h>
#include <linux/string.h>
#include "ccci_config.h"
#include "ccci_core.h"
#include "ccci_modem.h"
#include "modem_sys.h"
#include "md_sys1_platform.h"
#include "ccci_hif.h"
#include "ccci_tetris_owner.h"

static DEFINE_MUTEX(tetris_owner_lock);
static struct {
	struct ccci_modem *md;
	struct device *runtime_dev;
	struct ccci_tetris_proofs proofs;
	void *proof_owner;
	struct mt6878_ccci_start *backend;
	struct ccci_tetris_owner_result result;
	bool attempted;
} tetris_owner;

static int tetris_verify(struct device *dev, void *owner,
			 enum mt6878_ccci_start_gate gate)
{
	if (owner != &tetris_owner || dev != tetris_owner.runtime_dev)
		return -EINVAL;
	return tetris_owner.proofs.verify(dev, tetris_owner.proof_owner, gate);
}

static int tetris_transport(struct device *dev, void *owner)
{
	int ret;

	if (owner != &tetris_owner || dev != tetris_owner.runtime_dev)
		return -EINVAL;
	/* The backend calls this only after actual provider ON/readback. */
	tetris_owner.result.transport_stage = 1;
	ret = tetris_owner.proofs.transport_access(dev, tetris_owner.proof_owner);
	if (ret)
		return ret < 0 ? ret : -EPROTO;
	tetris_owner.result.transport_attempted = true;
	tetris_owner.result.transport_stage = 2;
	ret = ccci_tetris_wdt_init_owned(tetris_owner.md);
	if (ret)
		return ret < 0 ? ret : -EPROTO;
	tetris_owner.result.transport_stage = 3;
	ret = ccci_hif_start_owned();
	if (ret)
		return ret < 0 ? ret : -EPROTO;
	tetris_owner.result.transport_stage = 4;
	return ccci_tetris_publish_hs1();
}

int ccci_tetris_owner_bind(struct ccci_modem *md, struct device *runtime_dev,
			 void *proof_owner, const struct ccci_tetris_proofs *proofs)
{
	const struct mt6878_ccci_start_callbacks callbacks = {
		.verify = tetris_verify, .prepare_transport = tetris_transport,
	};
	struct mt6878_ccci_start *backend;
	int ret = 0;

	if (!md || !md->plat_dev || !md->hw_info || !md->hw_info->plat_val ||
	    !runtime_dev || !proofs || !proofs->verify || !proofs->transport_access)
		return -EINVAL;
	/* A normal platform-domain attach already powers ON before driver probe. */
	if (runtime_dev == &md->plat_dev->dev || md->plat_dev->dev.pm_domain ||
	    !runtime_dev->pm_domain || !runtime_dev->bus ||
	    strcmp(runtime_dev->bus->name, "genpd") || !runtime_dev->of_node ||
	    runtime_dev->of_node != md->plat_dev->dev.of_node)
		return -EBUSY;
	if (md->hw_info->plat_val->md_gen != 6299 ||
	    md->hif_flag != (BIT(CCIF_HIF_ID) | BIT(DPMAIF_HIF_ID)) ||
	    !(md->per_md_data.config.setting & MD_SETTING_FIRST_BOOT))
		return -EOPNOTSUPP;
	mutex_lock(&tetris_owner_lock);
	if (tetris_owner.md || tetris_owner.attempted) {
		ret = -EBUSY;
		goto out;
	}
	/* Retain owner modules for the whole boot; no unsafe hot-unbind API. */
	if (!try_module_get(proofs->module)) {
		ret = -ENODEV;
		goto out;
	}
	if (!try_module_get(THIS_MODULE)) {
		module_put(proofs->module);
		ret = -ENODEV;
		goto out;
	}
	backend = mt6878_ccci_start_alloc(runtime_dev, &tetris_owner, &callbacks);
	if (IS_ERR(backend)) {
		module_put(THIS_MODULE);
		module_put(proofs->module);
		ret = PTR_ERR(backend);
		goto out;
	}
	tetris_owner.md = md;
	tetris_owner.runtime_dev = runtime_dev;
	tetris_owner.proofs = *proofs;
	tetris_owner.proof_owner = proof_owner;
	tetris_owner.backend = backend;
out:
	mutex_unlock(&tetris_owner_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(ccci_tetris_owner_bind);

int ccci_tetris_owner_entry(void)
{
	int ret;

	mutex_lock(&tetris_owner_lock);
	ret = tetris_owner.result.first_error;
	if (!ret && !tetris_owner.md)
		ret = -ENOKEY;
	if (!ret && tetris_owner.attempted)
		ret = -EALREADY;
	mutex_unlock(&tetris_owner_lock);
	return ret;
}

int ccci_tetris_owner_start(struct ccci_modem *md)
{
	int ret;

	mutex_lock(&tetris_owner_lock);
	if (tetris_owner.result.first_error) {
		ret = tetris_owner.result.first_error;
		goto out;
	}
	if (!tetris_owner.md || tetris_owner.md != md) {
		ret = -ENOKEY;
		goto fault;
	}
	if (tetris_owner.attempted) {
		ret = -EALREADY;
		goto out;
	}
	tetris_owner.attempted = true;
	ret = mt6878_ccci_first_start(tetris_owner.backend);
	mt6878_ccci_start_result(tetris_owner.backend, &tetris_owner.result.backend);
	if (ret)
		goto fault;
	/* No READY/HS1/HS2 fabrication: the existing IRQ/port FSM receives them. */
	md->per_md_data.config.setting &= ~MD_SETTING_FIRST_BOOT;
	atomic_set(&md->reset_on_going, 0); /* Host bookkeeping, not MD reset_b. */
	md->per_md_data.is_in_ee_dump = 0;
	md->is_force_asserted = 0;
	wdt_enable_irq(md);
	goto out;
fault:
	tetris_owner.attempted = true;
	tetris_owner.result.first_error = ret;
out:
	mutex_unlock(&tetris_owner_lock);
	return ret;
}

int ccci_tetris_owner_latch(int error)
{
	int ret;

	mutex_lock(&tetris_owner_lock);
	if (!tetris_owner.result.first_error)
		tetris_owner.result.first_error = error < 0 ? error : -EPROTO;
	tetris_owner.attempted = true;
	ret = tetris_owner.result.first_error;
	mutex_unlock(&tetris_owner_lock);
	return ret;
}

void ccci_tetris_owner_result(struct ccci_tetris_owner_result *result)
{
	if (!result)
		return;
	mutex_lock(&tetris_owner_lock);
	*result = tetris_owner.result;
	mutex_unlock(&tetris_owner_lock);
}
EXPORT_SYMBOL_GPL(ccci_tetris_owner_result);
