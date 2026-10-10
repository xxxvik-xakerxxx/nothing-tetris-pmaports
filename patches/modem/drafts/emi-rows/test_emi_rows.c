// SPDX-License-Identifier: GPL-2.0+
/* CI-only actual public footer/planners/producer/SIP adapter; synthetic EMI. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linux/errno.h>
#include <linux/arm-smccc.h>
#include "tetris_modem_emi_rows.h"

static struct tetris_modem_emi_rows produced;
static unsigned long long policies[12][8];
static unsigned int enabled[12], consumed[12], calls, writes, preset_calls;
static unsigned int mode;

static unsigned int word(const unsigned char *p)
{
	return (unsigned int)p[0] | (unsigned int)p[1] << 8 |
		(unsigned int)p[2] << 16 | (unsigned int)p[3] << 24;
}

void test_smc(unsigned long fid, unsigned long op, unsigned long a,
		unsigned long b, unsigned long c, unsigned long d,
		unsigned long e, unsigned long f, struct arm_smccc_res *res)
{
	unsigned int i, index;
	const struct tetris_modem_emi_row *r;
	struct tetris_modem_emi_range range;

	assert(fid == 0xc2000415U && !d && !e && !f);
	calls++;
	memset(res, 0, sizeof(*res));
	index = (unsigned int)(op == 0 ? c : op == 6 ? a : b) - 32;
	assert(index < 12);
	r = &produced.row[index];
	assert(r->kind);
	assert(!tetris_modem_plan_emi(r->start, r->size, r->slot, &range));
	if (op == 6) {
		assert(a == 40 && b == r->role && !c);
		preset_calls++;
		if (mode == 13) {
			res->a0 = 0xfffffffcUL;
			return;
		}
		writes++;
		if (mode != 14)
			for (i = 0; i < 8; i++)
				policies[index][i] |= r->policy[i];
		return;
	}
	if (!op) {
		assert(a == range.start_page && b == range.end_page && c == r->slot);
		if (consumed[index] || (mode == 15 && index == 8)) {
			res->a0 = ~0UL - 3;
			return;
		}
		consumed[index] = enabled[index] = 1;
		writes++;
		return;
	}
	assert(op == 2);
	if (a == 3) {
		res->a0 = enabled[index] || (mode == 11 && index == 8);
	} else if (a == 4) {
		assert(c < 8);
		res->a0 = policies[index][c];
		if (mode == 12 && index == 8 && !c)
			res->a0 |= 1;
		if (mode == 16 && index == 8 && c == 1 && preset_calls)
			res->a0 ^= 1;
	} else if (!a) {
		res->a0 = range.start_readback ^ (mode == 17 && index == 8 ? 1 : 0);
	} else {
		assert(a == 1 && !c);
		res->a0 = range.end_readback;
	}
}

int main(int argc, char **argv)
{
	static const unsigned char pin[32] =
		"\x5d\x2b\xed\xd0\x00\x49\xfc\xed\x98\x3d\x3a\xe5\x39\x89\x61\x6c"
		"\x5c\x9f\x46\xc4\xed\xdd\x32\xa0\x1a\x1a\xd4\x6f\xf8\xd2\xc5\x0f";
	struct tetris_modem_emi_resources resources = {
		.firmware = { 0x80000000ULL, 0x20000000ULL },
		.nc = { 0xa0000000ULL, 0xa000000ULL },
		.cache = { 0xc0000000ULL, 0x8000000ULL },
		.dram_base = 0x40000000ULL, .dram_size = 0x100000000ULL,
	};
	struct tetris_modem_emi_rows_transaction tx = { 0 };
	unsigned char header[512], profile[32], *rom;
	unsigned int rom_size, dsp_size = 0, i, active = 0;
	unsigned int before_calls, before_writes;
	const char *phy = NULL;
	FILE *file;
	long offset;
	int result;

	assert(argc == 3);
	mode = (unsigned int)atoi(argv[2]);
	assert(mode <= 20);
	file = fopen(argv[1], "rb");
	assert(file && fread(header, 1, 512, file) == 512);
	assert(word(header) == 0x58881688 && !strcmp((const char *)header + 8, "md1rom"));
	rom_size = word(header + 4);
	assert(rom_size >= 512 && rom_size <= 64U * 1024 * 1024);
	rom = malloc(rom_size);
	assert(rom && fread(rom, 1, rom_size, file) == rom_size);
	offset = (long)((512UL + rom_size + 15) & ~15UL);
	for (i = 0; i < 128 && !dsp_size; i++) {
		assert(!fseek(file, offset, SEEK_SET));
		assert(fread(header, 1, 512, file) == 512 && word(header) == 0x58881688);
		if (!strcmp((const char *)header + 8, "md1dsp"))
			dsp_size = word(header + 4);
		offset += (long)((512UL + word(header + 4) + 15) & ~15UL);
	}
	assert(dsp_size);
	fclose(file);
	memcpy(profile, pin, 32);
	if (mode == 1)
		profile[0] ^= 1;
	if (mode == 2)
		phy = "bogus";
	if (mode == 3) {
		phy = "1";
		resources.sib = (struct tetris_modem_emi_window){ 0xd0000000ULL, 0x100000 };
	}
	if (mode == 4)
		resources.sib.base = 0xd0000000ULL;
	if (mode == 5)
		/* CHKv6 CONSYS +0x180; +0x184 is UDC enable, not its size. */
		memset(rom + rom_size - 512 + 0x180, 0, 4);
	if (mode == 6)
		resources.cache.base += 0x10000;
	if (mode == 7)
		resources.nc.base = resources.cache.base;
	if (mode == 8)
		rom[rom_size - 512 + 12] = 5;
	if (mode == 9)
		phy = "0";
	/* CHK memory ends at +480MiB, but LMB owns the whole +512MiB.
	 * These aligned banks start precisely in the previously accepted tail.
	 */
	if (mode == 19)
		resources.nc.base = resources.firmware.base + 0x1e000000ULL;
	if (mode == 20)
		resources.cache.base = resources.firmware.base + 0x1e000000ULL;
	memset(&produced, 0xa5, sizeof(produced));
	result = tetris_modem_emi_rows_b41(rom, rom_size, dsp_size, &resources, 1, phy,
		profile, &produced);
	if (mode == 1 || mode == 2 || (mode >= 4 && mode <= 8) || mode >= 19) {
		const unsigned char *bytes = (const unsigned char *)&produced;

		assert(result < 0 && !calls && !writes);
		if (mode >= 19)
			assert(result == -ERANGE);
		for (i = 0; i < sizeof(produced); i++)
			assert(bytes[i] == 0xa5);
		free(rom);
		return 0;
	}
	assert(!result);
	if (mode == 18) {
		struct tetris_modem_memory_map initial;
		unsigned int j;

		assert(!tetris_modem_plan_memory(rom, rom_size, dsp_size, resources.firmware.base,
			resources.firmware.capacity, &initial));
		printf("{\"initial\":[");
		for (j = 0; j < initial.count; j++) {
			const struct tetris_modem_block *b = &initial.blocks[j];

			printf("%s[%u,%u,%u,%u,%llu]", j ? "," : "", b->offset, b->size,
				b->info, b->attributes, b->physical);
		}
		printf("],\"memory\":[");
		for (j = 0; j < produced.memory.count; j++) {
			const struct tetris_modem_block *b = &produced.memory.blocks[j];

			printf("%s[%u,%u,%u,%u,%llu]", j ? "," : "", b->offset, b->size,
				b->info, b->attributes, b->physical);
		}
		printf("],\"rows\":[");
		for (j = 0; j < 12; j++) {
			const struct tetris_modem_emi_row *r = &produced.row[j];

			printf("%s[%u,%u,%u,%llu,%llu]", j ? "," : "", r->kind, r->role,
				r->slot, r->start, r->size);
		}
		printf("]}\n");
		free(rom);
		return 0;
	}
	/* Actual stock v6 has four regions and the large +0x11c padding window.
	 * Compare boundaries directly with signed input, not hard-coded addresses.
	 */
	assert(word(rom + rom_size - 512 + 192) == 4);
	assert(produced.row[8].kind == TETRIS_MD_EMI_PRESET_RANGE && produced.row[8].role == 3);
	assert(produced.row[8].start == resources.firmware.base +
		word(rom + rom_size - 512 + 0x11c) + word(rom + rom_size - 512 + 0x120));
	assert(produced.row[8].size == word(rom + rom_size - 512 + 172) -
		word(rom + rom_size - 512 + 0x11c) - word(rom + rom_size - 512 + 0x120));
	assert(produced.row[7].kind == (mode == 3 ? TETRIS_MD_EMI_RANGE : TETRIS_MD_EMI_ABSENT));
	if (mode == 3) {
		assert(produced.row[7].size == 0x100000);
		assert(produced.row[7].policy[1] == (3ULL << 30));
		assert(produced.row[7].policy[7] == 0xa00000000ULL);
	}
	for (i = 0; i < 12; i++) {
		if (produced.row[i].kind)
			active++;
		if (i != 8)
			memcpy(policies[i], produced.row[i].policy, sizeof(policies[i]));
	}
	if (mode == 10)
		produced.row[8].policy[0] ^= 1;
	result = tetris_modem_emi_rows_program(&produced, &tetris_modem_emi_rows_hw_ops, &tx);
	if (mode < 10) {
		assert(!result && !tx.error && writes == active + 1 && preset_calls == 1);
		for (i = 0; i < 12; i++)
			assert(!!enabled[i] == !!produced.row[i].kind);
	} else {
		assert(result < 0 && tx.error == result);
		assert(!!enabled[8] == (mode == 17));
		if (mode == 10)
			assert(!calls && !writes);
		if (mode == 11 || mode == 12)
			assert(!preset_calls);
		if (mode == 13 || mode == 15)
			assert(result == -4);
	}
	before_calls = calls;
	before_writes = writes;
	assert(tetris_modem_emi_rows_program(&produced, &tetris_modem_emi_rows_hw_ops, &tx) ==
		(result ? result : -EALREADY));
	assert(calls == before_calls && writes == before_writes);
	free(rom);
	return 0;
}
