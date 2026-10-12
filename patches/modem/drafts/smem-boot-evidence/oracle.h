/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_BOOT_EVIDENCE_TEST_ORACLE_H
#define TETRIS_BOOT_EVIDENCE_TEST_ORACLE_H
#define TETRIS_MODEM_EMI_POLICY_WORDS 8
struct tetris_modem_emi_range {
	unsigned long long start_page, end_page, start_readback, end_readback;
	unsigned int slot;
};
int tetris_modem_plan_emi(unsigned long long start, unsigned long long size,
		unsigned int slot, struct tetris_modem_emi_range *range);
int tetris_modem_plan_emi_policy(const unsigned char digest[32],
		unsigned int slot, unsigned long long policy[8]);
#endif
