/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef CCCI_TETRIS_OWNER_H
#define CCCI_TETRIS_OWNER_H
#include <linux/soc/mediatek/mt6878_ccci_start.h>
struct ccci_modem;
struct module;
struct ccci_tetris_proofs {
	struct module *module;
	/* Real evidence owner; missing authentication/EMI/ownership must fail. */
	int (*verify)(struct device *, void *, enum mt6878_ccci_start_gate);
	/* Prove CCIF/DPMAIF MMIO, IRQ, DMA, shared memory, clocks and reset profile. */
	int (*transport_access)(struct device *, void *);
};
struct ccci_tetris_owner_result {
	int first_error;
	unsigned int transport_stage;
	bool transport_attempted;
	struct mt6878_ccci_start_result backend;
};
/* No autostart. runtime_dev must be the OFF-attached genpd virtual consumer. */
int ccci_tetris_owner_bind(struct ccci_modem *, struct device *runtime_dev,
			  void *proof_owner, const struct ccci_tetris_proofs *);
int ccci_tetris_owner_entry(void);
int ccci_tetris_owner_start(struct ccci_modem *);
int ccci_tetris_owner_latch(int error);
void ccci_tetris_owner_result(struct ccci_tetris_owner_result *);
/* Same composite: actual vendor implementations, not replaceable proof stubs. */
int ccci_tetris_wdt_init_owned(struct ccci_modem *);
void wdt_enable_irq(struct ccci_modem *);
int ccci_tetris_publish_hs1(void);
int ccci_hif_start_owned(void);
#endif
