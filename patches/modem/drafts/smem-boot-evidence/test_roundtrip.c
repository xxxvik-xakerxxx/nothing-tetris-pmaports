// SPDX-License-Identifier: GPL-2.0-only
/* Real U-Boot report factory, production encoder and production decoder. */
#define main producer_selftest
#include ".github/tests/tetris_modem_smem_evidence.c"
#undef main
#include "boot_evidence.h"

int main(void)
{
	struct tetris_modem_loaded_report report;
	struct tetris_smem_boot_evidence decoded, snapshot;
	struct tetris_metadata_banks banks;
	unsigned char wire[336];
	unsigned int relocated, bank, group;

	for (relocated = 0; relocated < 2; relocated++) {
		valid(&report);
		memset(&banks, 0, sizeof(banks));
		for (bank = 0; bank < 2; bank++) {
			struct tetris_modem_emi_window *w = bank ?
				&report.bootstrap.resources.cache : &report.bootstrap.resources.nc;
			struct tetris_modem_emi_row *row = &report.bootstrap.rows.row[10 + bank];
			struct tetris_modem_emi_transaction *tx = &report.hardware.emi.ranges[10 + bank];
			struct tetris_modem_emi_range range;
			struct tetris_metadata_window *target = bank ? &banks.cache : &banks.nc;

			if (relocated)
				w->base += 0x100000000ULL;
			row->reservation = *w;
			row->start = w->base;
			assert(!tetris_modem_plan_emi(row->start, row->size, row->slot, &range));
			tx->reply[10] = range.start_readback;
			tx->reply[11] = range.end_readback;
			if (relocated)
				tx->reply[11] &= ~TETRIS_MODEM_EMI_END_MARKER;
			target->base = w->base;
			target->capacity = w->capacity;
		}
		assert(tetris_modem_build_smem_evidence(&report, wire, sizeof(wire)) == 336);
		assert(!tetris_smem_boot_decode(wire, sizeof(wire), &banks, sizeof(banks),
			&decoded, sizeof(decoded)));
		for (bank = 0; bank < 2; bank++) {
			const struct tetris_modem_emi_row *row = &report.bootstrap.rows.row[10 + bank];
			const struct tetris_modem_emi_transaction *tx = &report.hardware.emi.ranges[10 + bank];

			assert(decoded.record[bank].range_start == row->start);
			assert(decoded.record[bank].range_size == row->size);
			assert(decoded.record[bank].actual_end == tx->reply[11]);
			for (group = 0; group < 8; group++)
				assert(decoded.record[bank].policy[group] == tx->reply[13 + group]);
		}
		snapshot = decoded;
		memset(wire, 0xff, sizeof(wire));
		memset(&report, 0xff, sizeof(report));
		assert(!memcmp(&decoded, &snapshot, sizeof(decoded)));
	}
	puts("actual U-Boot encoder -> actual Linux decoder: PASS (boot evidence only, no NS grant)");
	return 0;
}
