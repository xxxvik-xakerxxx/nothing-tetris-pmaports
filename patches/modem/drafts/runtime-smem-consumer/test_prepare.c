/* SPDX-License-Identifier: GPL-2.0-only */
/* Insert after the existing native registration fixture's kernel boundaries.
 * The actual modified register_prepare.h and consumer.h bodies follow below.
 */
static struct module mem_provider = { .pins = 1 };
static void *kzalloc(size_t size, int flags)
{
	(void)flags;
	assert(size == sizeof(struct tetris_ccci_smem_copy));
	if (fault == 15)
		return NULL;
	allocations++;
	return calloc(1, size);
}
int mtk_ccci_owned_mapped_copy(struct tetris_ccci_smem_copy *copy)
{
	assert(copy && !copy->provider);
	if (fault == 16)
		return -ERANGE;
	if (fault == 18)
		return -ENODEV;
	/* Export is a mocked provider boundary HERE; the separate binding fixture
	 * executes the real provider/export bodies with first-error/ref faults.
	 */
	mem_provider.pins++;
	copy->provider = &mem_provider;
	copy->layout.md_bank0.base_ap_view_phy = 0x80000000;
	copy->layout.md_bank0.size = 0x1000000;
	copy->layout.md_bank4_noncacheable_total.base_ap_view_vir = (void *)0x20000000;
	copy->layout.md_bank4_noncacheable = copy->nc;
	copy->layout.md_bank4_cacheable = copy->cache;
	copy->nc[25].id = copy->cache[10].id = SMEM_USER_MAX;
	copy->cache[0].id = SMEM_USER_RAW_MD_CONSYS;
	copy->cache[0].flag = SMF_NO_REMAP;
	if (fault == 17)
		copy->layout.md_bank0.base_ap_view_vir = (void *)1;
	return 0;
}
#include "consumer.h"
/* ACTUAL_REGISTRATION */

static void boot_end(void)
{
	/* Fixture-only boot lifetime reset, not a successful driver unload. */
	if (tetris_prepared_md) {
		struct ccci_modem *md = tetris_prepared_md;
		struct md_sys1_info *info = (void *)md->private_data;

		tetris_ccci_mem_abort(md);
		wakeup_source_unregister(info->peer_wake_lock);
		wakeup_source_unregister(md->trm_wake_lock);
		kfree(md->private_data);
		kfree(md);
	}
	assert(mem_provider.pins == 1 && !allocations && !wakes);
	tetris_prepared_md = NULL;
	tetris_registration_attempted = tetris_registration_exposed = tetris_registration_done = false;
	tetris_registration_error = 0;
	self.pins = providers[0].pins = providers[1].pins = 0;
	wake_calls = abort_ports = abort_fsm = pin_calls = 0;
	hif_ops[0].owner = &providers[0];
	hif_ops[1].owner = &providers[1];
	ccci_hif[1] = &providers[0]; ccci_hif[2] = &providers[1];
	ccci_hif_op[1] = &hif_ops[0]; ccci_hif_op[2] = &hif_ops[1];
}

int main(void)
{
	struct platform_device pdev = { .dev = { .of_node = &pdev } };
	struct ccci_dev_cfg cfg = { .capability = 1 };
	struct plat_val generation = { .md_gen = 6299 };
	struct md_hw_info hw = { .md_wdt_irq_id = 4, .plat_val = &generation };
	static const unsigned int cases[] = { 1, 2, 3, 4, 5, 6, 7, 10, 15, 16, 17, 18 };
	unsigned int i;
	int ret, expected;

	boot_end();
	for (i = 0; i < ARRAY_SIZE(cases); i++) {
		fault = cases[i];
		expected = fault <= 4 || fault == 15 ? -ENOMEM : fault == 5 ? -EAGAIN :
			fault == 6 ? -ENOSPC : fault == 7 ? -EIO : fault == 16 ? -ERANGE :
			fault == 17 ? -EPROTO : -ENODEV;
		ret = tetris_common_prepare(&pdev, &cfg, &hw);
		assert(ret == expected && !allocations && !wakes && mem_provider.pins == 1);
		assert(!modem_sys && !pdev.dev.platform_data && !tetris_prepared_md);
		assert(!config_calls && !ports_running && !fsm_running && !sysfs_calls);
		assert(!tetris_registration_exposed && !tetris_registration_done && !self.pins);
		assert(!providers[0].pins && !providers[1].pins);
		assert(abort_fsm == (fault == 6 || fault == 7 || fault == 10 ? 1 : 0));
		assert(abort_ports == (fault == 7 || fault == 10 ? 1 : 0));
		assert(tetris_common_prepare(&pdev, &cfg, &hw) == expected);
		assert(ccci_tetris_registration_quarantine(-ETIMEDOUT) == expected);
		assert(ccci_tetris_register_prepared(&pdev) == -EOPNOTSUPP);
		boot_end();
	}
	fault = 0;
	assert(!tetris_common_prepare(&pdev, &cfg, &hw));
	assert(allocations == 3 && wakes == 2 && mem_provider.pins == 2);
	assert(tetris_prepared_md && tetris_prepared_md->tetris_smem);
	assert(!tetris_prepared_md->mem_layout.md_bank0.base_ap_view_vir);
	assert(self.pins == 1 && providers[0].pins == 1 && providers[1].pins == 1);
	assert(!modem_sys && !pdev.dev.platform_data && !config_calls);
	assert(!ports_running && !fsm_running && !tetris_registration_done);
	assert(tetris_common_prepare(&pdev, &cfg, &hw) == -EALREADY);
	assert(ccci_tetris_register_prepared(NULL) == -EOPNOTSUPP);
	pdev.dev.bound = true;
	assert(ccci_tetris_register_prepared(&pdev) == -EOPNOTSUPP);
	assert(!tetris_registration_exposed && !pdev.dev.platform_data && !pdev.dev.lock);
	boot_end();
	return 0;
}
