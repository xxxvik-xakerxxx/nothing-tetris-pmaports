// SPDX-License-Identifier: GPL-2.0+
/* CI-only: real caller + secure transport + planners, synthetic hardware. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linux/arm-smccc.h>
#include <linux/errno.h>
#include "tetris_modem_layout.h"
#include "tetris_modem_bootstrap.h"

struct blk_desc { int unused; };
static int fault;
static unsigned int calls, writes, brom_polls, locked;
static unsigned int top = 0xabcdef00, power = 0x13b, iso = 0x123;
static unsigned int nemi = 0xc0, ifr9 = 0x200, ifr11 = 0x800;
static unsigned int other_power;
static unsigned int sequence[6], sequence_count;
static unsigned int cleaning, cleanup_count;
static struct tetris_modem_emi_rows rows;
static unsigned long long policy[12][8];
static struct tetris_modem_emi_range ranges[12];
static struct tetris_modem_remap remap;
static unsigned int enabled[12], consumed[12], bank_calls;
static unsigned int bank_regs[4];
static struct tetris_modem_emi_resources resources;

static unsigned int word(const unsigned char *p)
{
	return (unsigned int)p[0] | (unsigned int)p[1] << 8 |
		(unsigned int)p[2] << 16 | (unsigned int)p[3] << 24;
}

static unsigned char *load_rom(const char *path, size_t *rom_size, size_t *dsp_size)
{
	unsigned char header[512], *rom;
	unsigned int i;
	unsigned long offset;
	FILE *file = fopen(path, "rb");

	assert(file && fread(header, 1, 512, file) == 512);
	assert(word(header) == 0x58881688 && !strcmp((const char *)header + 8, "md1rom"));
	*rom_size = word(header + 4);
	assert(*rom_size >= 512 && *rom_size <= 64U * 1024 * 1024);
	rom = malloc(*rom_size);
	assert(rom && fread(rom, 1, *rom_size, file) == *rom_size);
	offset = (512UL + *rom_size + 15) & ~15UL;
	*dsp_size = 0;
	for (i = 0; i < 128 && !*dsp_size; i++) {
		assert(!fseek(file, (long)offset, SEEK_SET));
		assert(fread(header, 1, 512, file) == 512 && word(header) == 0x58881688);
		if (!strcmp((const char *)header + 8, "md1dsp"))
			*dsp_size = word(header + 4);
		offset += (512UL + word(header + 4) + 15) & ~15UL;
	}
	assert(*dsp_size);
	fclose(file);
	return rom;
}

unsigned int current_el(void)
{
	return fault == 1 ? 3 : 1;
}

int tetris_scp_check_atf_profile(struct blk_desc *dev)
{
	assert(dev);
	calls++;
	return fault == 2 ? -EKEYREJECTED : 0;
}

void udelay(unsigned long delay)
{
	assert(delay == 10 || delay == 20000);
}

unsigned int readl(const volatile void *pointer)
{
	uintptr_t address = (uintptr_t)pointer;

	calls++;
	switch (address) {
	case 0x10000000: return top;
	case 0x1c001e00: return power;
	case 0x1c001f24: return iso;
	case 0x10001c5c: return ifr9;
	case 0x10001c4c: return ifr11;
	case 0x1027008c: return nemi;
	default: abort();
	}
}

void writel(unsigned int value, volatile void *pointer)
{
	uintptr_t address = (uintptr_t)pointer;

	calls++;
	writes++;
	if (address == 0x10001c54)
		cleaning = 1;
	if (cleaning) {
		assert(cleanup_count < 6);
		switch (address) {
		case 0x10001c54:
			assert(cleanup_count == 0 && value == 0x200);
			if (fault != 31)
				ifr9 = 0x200;
			break;
		case 0x10001c44:
			assert(cleanup_count == 1 && value == 0x800);
			if (fault != 32)
				ifr11 = 0x800;
			break;
		case 0x10270084:
			assert(cleanup_count == 2 && value == 0xc0);
			if (fault != 33)
				nemi = 0xc0;
			break;
		case 0x1c001e00:
			assert(cleanup_count == 3 && value == (power & ~4U));
			power = value;
			if (fault != 34)
				power &= ~(3U << 30);
			assert((power & ~(4U | (3U << 30))) == other_power);
			break;
		case 0x1c001f24:
			assert(cleanup_count == 4 && value == (iso | 3U));
			assert(!(power & (4U | (3U << 30))));
			if (fault != 35)
				iso = value;
			break;
		case 0x10000000:
			assert(cleanup_count == 5 && value == (top | 0x300));
			if (fault != 36)
				top = value;
			break;
		default: abort();
		}
		cleanup_count++;
		return;
	}
	assert(locked && sequence_count < 6);
	switch (address) {
	case 0x10000000:
		assert(sequence_count == 0 && value == (top & ~0x300U));
		if (fault != 12)
			top = value;
		break;
	case 0x1c001f24:
		assert(sequence_count == 1 && value == (iso & ~3U));
		if (fault != 13)
			iso = value;
		break;
	case 0x1c001e00:
		assert(sequence_count == 2 && value == (other_power | 4));
		power = value;
		if (fault != 14)
			power |= 1U << 30;
		if (fault != 15)
			power |= 1U << 31;
		assert((power & ~(4U | (3U << 30))) == other_power);
		break;
	case 0x10270088:
		assert(sequence_count == 3 && value == 0xc0);
		if (fault != 16)
			nemi = 0;
		break;
	case 0x10001c48:
		assert(sequence_count == 4 && value == 0x800);
		if (fault != 17)
			ifr11 = 0;
		break;
	case 0x10001c58:
		assert(sequence_count == 5 && value == 0x200);
		if (fault != 18)
			ifr9 = 0;
		break;
	default: abort();
	}
	sequence[sequence_count++] = (unsigned int)address;
}

void test_smc(unsigned long fid, unsigned long operation, unsigned long a,
		unsigned long b, unsigned long c, unsigned long d,
		unsigned long e, unsigned long f, struct arm_smccc_res *out)
{
	calls++;
	assert(!d && !e && !f);
	memset(out, 0, sizeof(*out));
	if (fid == 0xc2000415U) {
		unsigned int index = (unsigned int)(!operation ? c : operation == 6 ? a : b) - 32;
		struct tetris_modem_emi_range *range;

		assert(!locked);
		assert(index < 12 && rows.row[index].kind);
		range = &ranges[index];
		if (operation == 6) {
			assert(a == 40 && b == rows.row[8].role && !c);
			writes++;
			memcpy(policy[8], rows.row[8].policy, sizeof(policy[8]));
			return;
		}
		if (!operation) {
			assert(a == range->start_page && b == range->end_page && c == index + 32);
			writes++;
			assert(!consumed[index]);
			consumed[index] = 1;
			if (fault == 8) {
				out->a0 = 0xfffffffcUL;
				return;
			}
			enabled[index] = 1;
			return;
		}
		assert(operation == 2 && b == index + 32);
		if (a == 3) {
			out->a0 = fault == 6 && !index ? 1 : enabled[index];
		} else if (a == 4) {
			assert(c < 8);
			out->a0 = policy[index][c] ^ (fault == 7 && !index && !c ? 1 : 0);
		} else if (a == 0) {
			out->a0 = range->start_readback ^ (fault == 9 && !index ? 1 : 0);
		} else {
			assert(a == 1);
			out->a0 = range->end_readback;
		}
		return;
	}
	assert(fid == 0xc200040bU);
	if (operation == 3) {
		static const unsigned int reg[8] = { 0, 1, 1, 1, 2, 2, 2, 3 };
		static const unsigned int shift[8] = { 20, 0, 10, 20, 0, 10, 20, 0 };
		unsigned int index = bank_calls < 8 ? bank_calls : bank_calls - 4;
		unsigned long long base = bank_calls < 8 ? resources.nc.base : resources.cache.base;
		unsigned long long address = base + (unsigned long long)
			(bank_calls < 8 ? bank_calls : bank_calls - 8) * 0x2000000ULL;
		unsigned int mask = 0x3ffU << shift[index];

		assert(enabled[0] && !locked && bank_calls < 12 && c == index);
		assert(a == (unsigned int)address && b == (unsigned int)(address >> 32));
		bank_calls++;
		if (fault == 37) {
			out->a0 = 0xfffffff1UL;
			return;
		}
		writes++;
		bank_regs[reg[index]] = (bank_regs[reg[index]] & ~mask) |
			((unsigned int)((address >> 25) & 0x3ff) << shift[index]);
		out->a1 = bank_regs[reg[index]] ^ (fault == 38 ? mask : 0);
		return;
	}
	if (operation == 1 || operation == 2) {
		assert(enabled[0] && !locked && !c);
		if (operation == 1) {
			writes++;
			out->a0 = fault == 10 ? ~0UL - 6 : 0;
			out->a1 = remap.value[0];
			out->a2 = remap.value[1];
			out->a3 = remap.value[2];
		} else {
			out->a0 = remap.value[2] ^ (fault == 11 ? 1 : 0);
			out->a1 = remap.value[3];
			out->a2 = remap.value[4];
			out->a3 = remap.value[5];
		}
		return;
	}
	if (operation == 8) {
		assert(!a && !b && !c && enabled[0] && !locked && bank_calls == 12);
		writes++;
		if (fault == 24) {
			out->a0 = 0xfffffff1UL;
			return;
		}
		locked = 1;
		return;
	}
	assert(operation == 6 && !b && !c && locked && sequence_count == 6);
	assert(a == 1 || a == 7);
	if (a == 1) {
		writes++;
		out->a0 = fault == 19 ? 0xfffffff3UL : 0;
		out->a3 = fault == 20 ? 0 : 1;
		return;
	}
	brom_polls++;
	out->a0 = fault == 21 || (fault >= 31 && fault <= 36) ? ~0UL - 12 : 0;
	out->a1 = 0x1234567887654321UL;
	out->a2 = out->a3 = 0x100000001UL;
	if (fault == 22)
		out->a2 = 0x100000002UL;
	if (fault == 23 && brom_polls < 3)
		out->a3 = 1;
}

int main(int argc, char **argv)
{
	static const unsigned int stage[] = {
		TETRIS_MD_BOOT_COMPLETE, TETRIS_MD_BOOT_INPUT,
		TETRIS_MD_BOOT_PROFILE, TETRIS_MD_BOOT_COLD_OFF,
		TETRIS_MD_BOOT_COLD_OFF, TETRIS_MD_BOOT_COLD_OFF,
		TETRIS_MD_BOOT_EMI, TETRIS_MD_BOOT_EMI, TETRIS_MD_BOOT_EMI,
		TETRIS_MD_BOOT_EMI, TETRIS_MD_BOOT_REMAP, TETRIS_MD_BOOT_REMAP,
		TETRIS_MD_BOOT_CLOCK, TETRIS_MD_BOOT_ISOLATION,
		TETRIS_MD_BOOT_POWER, TETRIS_MD_BOOT_POWER,
		TETRIS_MD_BOOT_BUS_NEMI, TETRIS_MD_BOOT_BUS_IFR11,
		TETRIS_MD_BOOT_BUS_IFR9, TETRIS_MD_BOOT_RELEASE,
		TETRIS_MD_BOOT_RELEASE, TETRIS_MD_BOOT_BROM, TETRIS_MD_BOOT_BROM,
		TETRIS_MD_BOOT_COMPLETE, TETRIS_MD_BOOT_REMAP_LOCK,
		TETRIS_MD_BOOT_COLD_OFF, TETRIS_MD_BOOT_COLD_OFF,
		TETRIS_MD_BOOT_COLD_OFF, TETRIS_MD_BOOT_INPUT,
		TETRIS_MD_BOOT_INPUT, TETRIS_MD_BOOT_INPUT,
		TETRIS_MD_BOOT_BROM, TETRIS_MD_BOOT_BROM, TETRIS_MD_BOOT_BROM,
		TETRIS_MD_BOOT_BROM, TETRIS_MD_BOOT_BROM, TETRIS_MD_BOOT_BROM,
		TETRIS_MD_BOOT_SMEM_REMAP, TETRIS_MD_BOOT_SMEM_REMAP,
		TETRIS_MD_BOOT_INPUT, TETRIS_MD_BOOT_INPUT,
	};
	struct blk_desc dev = { 0 };
	struct tetris_modem_bootstrap_plan plan = {
		.resources = {
			.firmware = { 0x80000000ULL, 0x20000000ULL },
			.nc = { 0xa0000000ULL, 0x8000000ULL },
			.cache = { 0xc0000000ULL, 0x8000000ULL },
			.dram_base = 0x40000000ULL, .dram_size = 0x100000000ULL,
		},
		.preloader_sha256 = {
			0x5d, 0x2b, 0xed, 0xd0, 0x00, 0x49, 0xfc, 0xed,
			0x98, 0x3d, 0x3a, 0xe5, 0x39, 0x89, 0x61, 0x6c,
			0x5c, 0x9f, 0x46, 0xc4, 0xed, 0xdd, 0x32, 0xa0,
			0x1a, 0x1a, 0xd4, 0x6f, 0xf8, 0xd2, 0xc5, 0x0f,
		},
	};
	struct tetris_modem_bootstrap_report report, repeated;
	unsigned int before_calls, before_writes, i;
	size_t rom_size, dsp_size;
	unsigned char *rom;
	int result;

	assert(argc == 3);
	fault = atoi(argv[1]);
	assert(fault >= 0 && fault <= 40);
	rom = load_rom(argv[2], &rom_size, &dsp_size);
	resources = plan.resources;
	other_power = power;
	assert(!tetris_modem_emi_rows_b41(rom, rom_size, dsp_size,
		&resources, 1, NULL, plan.preloader_sha256, &rows));
	plan.rows = rows;
	/* Production loader caches this before release; bootstrap has no ROM ptr. */
	free(rom);
	for (i = 0; i < 12; i++) {
		if (!rows.row[i].kind)
			continue;
		assert(!tetris_modem_plan_emi(rows.row[i].start, rows.row[i].size, i + 32, &ranges[i]));
		if (i != 8)
			memcpy(policy[i], rows.row[i].policy, sizeof(policy[i]));
	}
	assert(!tetris_modem_plan_remap(resources.firmware.base, resources.firmware.capacity,
		resources.dram_base, resources.dram_size, &remap));
	if (fault == 3)
		power |= 4;
	if (fault == 4)
		power |= 1U << 31;
	if (fault == 5)
		iso &= ~3U;
	if (fault == 25)
		ifr9 = 0;
	if (fault == 26)
		ifr11 = 0;
	if (fault == 27)
		nemi = 0;
	if (fault == 28)
		plan.rows.row[0].reservation.base += 0x10000;
	if (fault == 29)
		plan.preloader_sha256[0] ^= 1;
	if (fault == 39)
		plan.resources.nc.capacity = 0x7ff0000ULL;
	if (fault == 40)
		plan.resources.cache.capacity = 0x7ff0000ULL;
	result = tetris_modem_bootstrap_once(&dev, fault == 30 ? NULL : &plan);
	assert(!tetris_modem_bootstrap_report(&report));
	assert(report.error == result);
	assert(report.stage == stage[fault]);
	if (!fault || fault == 23) {
		assert(!result && report.stage == TETRIS_MD_BOOT_COMPLETE);
		assert(sequence_count == 6 && brom_polls == (fault == 23 ? 3U : 1U));
		assert(report.reply[2] == 0x100000001ULL && report.reply[3] == 0x100000001ULL);
	} else {
		assert(result < 0 && report.stage != TETRIS_MD_BOOT_COMPLETE);
		if (fault <= 7 || (fault >= 25 && fault <= 30))
			assert(!writes);
		if (fault == 8)
			assert(result == -4 && writes == 1);
		if (fault == 22)
			assert(result == -ETIMEDOUT && brom_polls == 100);
		if (fault >= 12 && fault <= 18)
			assert(!brom_polls && sequence_count == (unsigned int)(fault - 11 - (fault >= 15)));
		if ((fault >= 12 && fault <= 22)) {
			assert(report.cleanup.stage == TETRIS_MD_CLEANUP_COMPLETE);
			assert(!report.cleanup.error && cleanup_count == 6);
			assert(power == other_power && (iso & 3) == 3 && (top & 0x300) == 0x300);
		} else if (fault >= 31 && fault <= 36) {
			assert(result == -13 && report.cleanup.error == -ETIMEDOUT);
			assert(cleanup_count == (unsigned int)(fault - 30));
			assert(report.cleanup.stage == (unsigned int)(fault - 30));
		} else {
			assert(report.cleanup.stage == TETRIS_MD_CLEANUP_NONE && !cleanup_count);
		}
	}
	before_calls = calls;
	before_writes = writes;
	assert(tetris_modem_bootstrap_once(&dev, &plan) == (result ? result : -EALREADY));
	assert(!tetris_modem_bootstrap_report(&repeated));
	assert(!memcmp(&report, &repeated, sizeof(report)));
	assert(calls == before_calls && writes == before_writes);
	return 0;
}
