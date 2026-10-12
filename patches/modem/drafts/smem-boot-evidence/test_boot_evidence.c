// SPDX-License-Identifier: GPL-2.0-only
/* CI-only: links the actual decoder body and the actual pinned planner bodies. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "boot_evidence.h"
#include "oracle.h"

static const unsigned char digest[32] =
	"\x5d\x2b\xed\xd0\x00\x49\xfc\xed\x98\x3d\x3a\xe5\x39\x89\x61\x6c"
	"\x5c\x9f\x46\xc4\xed\xdd\x32\xa0\x1a\x1a\xd4\x6f\xf8\xd2\xc5\x0f";
static unsigned int rejected;

static void put32(unsigned char *p, unsigned int value)
{
	unsigned int i;
	for (i = 0; i < 4; i++)
		p[i] = (unsigned char)(value >> (i * 8));
}

static void put64(unsigned char *p, unsigned long long value)
{
	put32(p, (unsigned int)value);
	put32(p + 4, (unsigned int)(value >> 32));
}

static void encode(unsigned char wire[336], const struct tetris_metadata_banks *banks,
		unsigned long long nc_size, unsigned long long cache_size)
{
	const unsigned int header[12] = { 1, 336, 1, 2, 6878, 6299, 11, 15, 0, 0, 0, 0 };
	unsigned int i, bank;

	memset(wire, 0, 336);
	for (i = 0; i < 12; i++)
		put32(wire + i * 4, header[i]);
	memcpy(wire + 48, digest, 32);
	for (bank = 0; bank < 2; bank++) {
		const struct tetris_metadata_window *w = bank ? &banks->cache : &banks->nc;
		unsigned long long size = bank ? cache_size : nc_size;
		struct tetris_modem_emi_range range;
		unsigned long long policy[8];
		unsigned char *r = wire + 80 + bank * 128;

		assert(tetris_modem_plan_emi(w->base, size, 42 + bank, &range) == 0);
		assert(tetris_modem_plan_emi_policy(digest, 42 + bank, policy) == 0);
		put32(r, bank);
		put32(r + 4, 42 + bank);
		put64(r + 8, w->base);
		put64(r + 16, w->capacity);
		put64(r + 24, w->base);
		put64(r + 32, size);
		put64(r + 40, range.start_readback);
		put64(r + 48, range.end_readback);
		put64(r + 56, 1);
		for (i = 0; i < 8; i++)
			put64(r + 64 + i * 8, policy[i]);
	}
}

static int decode(const void *wire, size_t bytes, const struct tetris_metadata_banks *banks,
		struct tetris_smem_boot_evidence *out)
{
	return tetris_smem_boot_decode(wire, bytes, banks, sizeof(*banks), out, sizeof(*out));
}

static void reject(const void *wire, size_t bytes, const struct tetris_metadata_banks *banks)
{
	struct tetris_smem_boot_evidence output, before;
	memset(&output, 0xa5, sizeof(output));
	memcpy(&before, &output, sizeof(before));
	assert(decode(wire, bytes, banks, &output) < 0);
	assert(!memcmp(&before, &output, sizeof(output)));
	rejected++;
}

static void every_field_and_policy_bit(const unsigned char good[336],
		const struct tetris_metadata_banks *banks)
{
	unsigned char bad[336];
	struct tetris_smem_boot_evidence out;
	unsigned int byte, bit;

	/* Every header/error/reserved/digest field, record field, and all 256
	 * policy domain bits per bank. Only endpoint END_MARKER may differ.
	 */
	for (byte = 0; byte < 336; byte++) {
		for (bit = 0; bit < 8; bit++) {
			memcpy(bad, good, 336);
			bad[byte] ^= 1U << bit;
			if ((byte == 80 + 48 + 5 || byte == 208 + 48 + 5) && bit == 3) {
				assert(decode(bad, 336, banks, &out) == 0);
				assert(!(out.record[byte > 208].actual_end & TETRIS_SMEM_BOOT_END_MARKER));
			} else {
				reject(bad, 336, banks);
			}
		}
	}
}

static void absent_truncated_alias_overflow(unsigned char good[336],
		const struct tetris_metadata_banks *banks)
{
	struct tetris_smem_boot_evidence output, before;
	_Alignas(struct tetris_smem_boot_evidence) unsigned char arena[2048], saved[2048];
	unsigned char extended[337], unaligned[337];
	unsigned int i;
	const void *wrap = (const void *)(uintptr_t)(UINTPTR_MAX - 15);

	for (i = 0; i < 336; i++)
		reject(good, i, banks);
	memcpy(extended, good, 336);
	extended[336] = 0;
	reject(extended, sizeof(extended), banks);
	reject(NULL, 336, banks);
	reject(good, 336, NULL);
	reject(wrap, 336, banks);
	reject(good, 336, wrap);
	memset(&output, 0xa5, sizeof(output));
	memcpy(&before, &output, sizeof(output));
	for (i = 0; i < sizeof(output); i++) {
		assert(tetris_smem_boot_decode(good, 336, banks, sizeof(*banks), &output, i) < 0);
		assert(!memcmp(&before, &output, sizeof(output)));
	}
	for (i = 0; i < sizeof(*banks); i++) {
		assert(tetris_smem_boot_decode(good, 336, banks, i, &output, sizeof(output)) < 0);
		assert(!memcmp(&before, &output, sizeof(output)));
	}
	assert(tetris_smem_boot_decode(good, 336, banks, sizeof(*banks) + 1,
		&output, sizeof(output)) < 0);
	assert(!memcmp(&before, &output, sizeof(output)));
	assert(tetris_smem_boot_decode(good, 336, banks, sizeof(*banks), NULL, sizeof(output)) < 0);
	assert(tetris_smem_boot_decode(good, 336, banks, sizeof(*banks),
		(void *)wrap, sizeof(output)) < 0);
	assert(tetris_smem_boot_decode(good, 336, banks, sizeof(*banks), &output, SIZE_MAX) < 0);
	assert(!memcmp(&before, &output, sizeof(output)));
	/* Full, partial, and one-byte overlaps in each of the three pairs. */
	for (i = 0; i < 336; i++) {
		memset(arena, 0xa5, sizeof(arena));
		memcpy(arena, good, 336);
		memcpy(arena + 1024, banks, sizeof(*banks));
		memcpy(saved, arena, sizeof(arena));
		assert(tetris_smem_boot_decode(arena, 336, (void *)(arena + 1024), sizeof(*banks),
			(void *)(arena + i), sizeof(output)) < 0);
		assert(!memcmp(arena, saved, sizeof(arena)));
		assert(tetris_smem_boot_decode(arena, 336, (void *)(arena + i), sizeof(*banks),
			(void *)(arena + 512), sizeof(output)) < 0);
		assert(!memcmp(arena, saved, sizeof(arena)));
	}
	for (i = 0; i < sizeof(*banks); i++) {
		assert(tetris_smem_boot_decode(arena, 336, (void *)(arena + 1024), sizeof(*banks),
			(void *)(arena + 1024 + i), sizeof(output)) < 0);
		assert(!memcmp(arena, saved, sizeof(arena)));
	}
	/* Byte loads and memcpy permit an unaligned property. */
	memcpy(unaligned + 1, good, 336);
	assert(decode(unaligned + 1, 336, banks, &output) == 0);
}

static void reservation_and_range_faults(const unsigned char good[336],
		const struct tetris_metadata_banks *banks)
{
	struct tetris_metadata_banks bad_banks;
	unsigned char bad[336], record[128];
	unsigned int bank, i;
	const unsigned long long invalid[] = { 0, 1, 4095, ~0ULL, 0x100000000ULL };

	for (bank = 0; bank < 2; bank++) {
		unsigned int r = 80 + bank * 128;
		for (i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
			memcpy(bad, good, 336);
			put64(bad + r + 32, invalid[i]);
			reject(bad, 336, banks);
		}
		bad_banks = *banks;
		(bank ? &bad_banks.cache : &bad_banks.nc)->base = ~0ULL - 4095;
		reject(good, 336, &bad_banks);
		bad_banks = *banks;
		(bank ? &bad_banks.cache : &bad_banks.nc)->capacity = ~0ULL - 4095;
		reject(good, 336, &bad_banks);
		bad_banks = *banks;
		(bank ? &bad_banks.cache : &bad_banks.nc)->base++;
		reject(good, 336, &bad_banks);
		bad_banks = *banks;
		(bank ? &bad_banks.cache : &bad_banks.nc)->capacity++;
		reject(good, 336, &bad_banks);
		bad_banks = *banks;
		(bank ? &bad_banks.cache : &bad_banks.nc)->base = 0;
		reject(good, 336, &bad_banks);
		bad_banks = *banks;
		(bank ? &bad_banks.cache : &bad_banks.nc)->capacity = 0;
		reject(good, 336, &bad_banks);
		memcpy(bad, good, 336);
		put64(bad + r + 24, (bank ? banks->cache.base : banks->nc.base) + 4096);
		reject(bad, 336, banks);
	}
	bad_banks = *banks;
	bad_banks.cache = bad_banks.nc;
	reject(good, 336, &bad_banks);
	memcpy(bad, good, 336);
	memcpy(record, bad + 80, 128);
	memcpy(bad + 80, bad + 208, 128);
	memcpy(bad + 208, record, 128);
	reject(bad, 336, banks);
	/* Matching the wire cannot turn an overflowing or overlapping snapshot
	 * into a valid reservation. Boundary faults are independent of mismatch.
	 */
	bad_banks = *banks;
	bad_banks.nc.base = ~0ULL - 4095;
	memcpy(bad, good, 336);
	put64(bad + 88, bad_banks.nc.base);
	put64(bad + 104, bad_banks.nc.base);
	reject(bad, 336, &bad_banks);
	bad_banks = *banks;
	bad_banks.cache.base = bad_banks.nc.base + 4096;
	memcpy(bad, good, 336);
	put64(bad + 216, bad_banks.cache.base);
	put64(bad + 232, bad_banks.cache.base);
	reject(bad, 336, &bad_banks);
	bad_banks = *banks;
	bad_banks.nc.base = 0x840000000ULL - 4096;
	bad_banks.nc.capacity = 4096;
	memcpy(bad, good, 336);
	put64(bad + 88, bad_banks.nc.base);
	put64(bad + 96, bad_banks.nc.capacity);
	put64(bad + 104, bad_banks.nc.base);
	put64(bad + 112, 4096);
	put64(bad + 120, bad_banks.nc.base);
	put64(bad + 128, 0x840000000ULL | TETRIS_SMEM_BOOT_END_MARKER);
	reject(bad, 336, &bad_banks);
}

static void endpoint_boundaries_and_physical_order(void)
{
	struct tetris_metadata_banks banks = {
		.nc = { 0x200000000ULL, 8192 },
		.cache = { 0x40000000ULL, 8192 },
	};
	struct tetris_smem_boot_evidence output;
	struct tetris_modem_emi_range range;
	unsigned char wire[336], bad[336];
	unsigned int bank;

	/* Logical NC/cache order survives cache being physically below NC.
	 * Include the aperture origin and both absent raw endpoint markers.
	 */
	encode(wire, &banks, 4096, 8192);
	assert(decode(wire, 336, &banks, &output) == 0);
	for (bank = 0; bank < 2; bank++) {
		unsigned int r = 80 + bank * 128;
		unsigned long long end = output.record[bank].range_start + output.record[bank].range_size;

		memcpy(bad, wire, 336);
		put64(bad + r + 48, end - 1);
		reject(bad, 336, &banks);
		memcpy(bad, wire, 336);
		put64(bad + r + 48, end | (1ULL << 44));
		reject(bad, 336, &banks);
		put64(wire + r + 48, end);
	}
	assert(decode(wire, 336, &banks, &output) == 0);
	assert(!(output.record[0].actual_end & TETRIS_SMEM_BOOT_END_MARKER));
	assert(!(output.record[1].actual_end & TETRIS_SMEM_BOOT_END_MARKER));
	/* Independently confirm the real helper's page and strict end bounds. */
	assert(tetris_modem_plan_emi(0x3ffff000ULL, 4096, 42, &range) < 0);
	assert(tetris_modem_plan_emi(0x40000000ULL, 4095, 42, &range) < 0);
	assert(tetris_modem_plan_emi(0x840000000ULL - 4096, 4096, 42, &range) < 0);
	assert(tetris_modem_plan_emi(0x840000000ULL, 4096, 42, &range) < 0);
	assert(tetris_modem_plan_emi(0x40000000ULL, ~0ULL, 42, &range) < 0);
	/* Matching reservation metadata still rejects a start below origin. */
	banks.nc.base = 0x3ffff000ULL;
	banks.nc.capacity = 4096;
	put64(wire + 88, banks.nc.base);
	put64(wire + 96, banks.nc.capacity);
	put64(wire + 104, banks.nc.base);
	put64(wire + 120, banks.nc.base);
	put64(wire + 128, banks.nc.base + 4096);
	reject(wire, 336, &banks);
}

int main(void)
{
	struct tetris_metadata_banks banks = {
		.firmware = { 0x80000000ULL, 0x2000000ULL },
		.nc = { 0x100000000ULL, 0x2000000ULL },
		.cache = { 0x108000000ULL, 0x4000000ULL },
		.tags = { 0x90000000ULL, 0x10000ULL },
	};
	struct tetris_smem_boot_evidence out, saved;
	unsigned char wire[336];
	unsigned int i;

	for (i = 0; i < 4; i++) {
		unsigned long long nc_size = i == 3 ? banks.nc.capacity : (i + 1) * 4096ULL;
		unsigned long long cache_size = i == 3 ? banks.cache.capacity : (i + 7) * 4096ULL;
		encode(wire, &banks, nc_size, cache_size);
		assert(decode(wire, 336, &banks, &out) == 0);
		assert(out.record[0].reservation_base == banks.nc.base);
		assert(out.record[1].reservation_capacity == banks.cache.capacity);
		assert(out.record[0].range_size == nc_size);
		assert(out.record[1].range_size == cache_size);
		assert(out.record[0].actual_end == (banks.nc.base + nc_size) + TETRIS_SMEM_BOOT_END_MARKER);
		assert(!memcmp(out.preloader_sha256, digest, 32));
		every_field_and_policy_bit(wire, &banks);
		absent_truncated_alias_overflow(wire, &banks);
		reservation_and_range_faults(wire, &banks);
		memcpy(&saved, &out, sizeof(out));
		memset(wire, 0, sizeof(wire));
		banks.nc.base += 0x20000000ULL;
		banks.cache.base += 0x20000000ULL;
		assert(!memcmp(&saved, &out, sizeof(out)));
	}
	endpoint_boundaries_and_physical_order();
	printf("PASS: actual decoder, pinned EMI/policy bodies; %u field/range rejections plus bounds/aliases\n", rejected);
	return 0;
}
