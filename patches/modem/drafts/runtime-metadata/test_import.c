/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual boot-args lookup and import, public producer output, no MMIO. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "metadata_resources.h"

#define __iomem
#define GFP_KERNEL 0
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define pr_info(...) ((void)0)
#define EXPORT_SYMBOL(name)
#define ARGS_KEY_VAL_KEY_SIZE 36
#define ARGS_KEY_VAL_MAX_KEY_NUM 73
enum args_src { FROM_LK_TAG, FROM_KERNEL };
/* STRUCT */
static unsigned int s_args_num, s_init_done;
static struct args_key_val s_args_tbl[ARGS_KEY_VAL_MAX_KEY_NUM];
static unsigned int copies;
static bool alloc_fail;
static void *kmalloc(size_t size, int flags)
{
	(void)flags;
	return alloc_fail ? NULL : malloc(size);
}
static void kfree(void *p) { free(p); }
static void memcpy_fromio(void *out, const void *in, size_t size)
{
	copies++;
	memcpy(out, in, size);
}
static unsigned int get_unaligned_le32(const void *p)
{
	const unsigned char *b = p;
	return (unsigned int)b[0] | (unsigned int)b[1] << 8 |
		(unsigned int)b[2] << 16 | (unsigned int)b[3] << 24;
}
static uint64_t get_unaligned_le64(const void *p)
{
	const unsigned char *b = p;
	return (uint64_t)get_unaligned_le32(b) |
		(uint64_t)get_unaligned_le32(b + 4) << 32;
}
static void *memchr_inv(const void *p, int value, size_t size)
{
	const unsigned char *b = p;
	for (size_t i = 0; i < size; i++) {
		if (b[i] != (unsigned char)value)
			return (void *)(b + i);
	}
	return NULL;
}
static void put32(unsigned char *p, unsigned int value)
{
	for (unsigned int i = 0; i < 4; i++)
		p[i] = (unsigned char)(value >> (8 * i));
}
/* EXISTING_LOOKUP */
/* IMPORT */

void kernel_import_probe(unsigned char *tags, unsigned int size, unsigned int fault,
		const struct tetris_metadata_banks *source_banks)
{
	unsigned char *expected = malloc(size), result[4096];
	unsigned int original_size = size, version = 2, count = 21;
	int ret;
	struct tetris_metadata_banks banks = *source_banks;
	unsigned char *memory, *nc, *cache, *chk;
	unsigned char initial_table[sizeof(s_args_tbl)];

	assert(expected && fault < 59);
	memcpy(expected, tags, size);
	memory = tags + get_unaligned_le32(tags + 10 * 76 + 64);
	nc = tags + get_unaligned_le32(tags + 12 * 76 + 64);
	cache = tags + get_unaligned_le32(tags + 14 * 76 + 64);
	chk = tags + get_unaligned_le32(tags + 7 * 76 + 64);
	s_init_done = 1;
	s_args_num = 2;
	memcpy(s_args_tbl[0].key, "ap_platform", 12);
	s_args_tbl[0].key_size = 12;
	memcpy(s_args_tbl[1].key, "md_generation", 14);
	s_args_tbl[1].key_size = 14;
	if (fault == 1)
		alloc_fail = true;
	if (fault == 2)
		size = 65537;
	if (fault == 3)
		version = 3;
	if (fault == 4)
		count = 20;
	if (fault == 5)
		tags[0] ^= 1;
	if (fault == 6)
		put32(tags + 72, 0);
	if (fault == 7)
		put32(tags + 64, 0);
	if (fault == 8)
		put32(tags + 68, UINT32_MAX);
	if (fault == 9)
		tags[63] = 1;
	if (fault == 10)
		put32(tags + get_unaligned_le32(tags + 11 * 76 + 64), 0);
	if (fault == 11)
		put32(tags + get_unaligned_le32(tags + 20 * 76 + 64), 1);
	if (fault == 12) {
		memcpy(s_args_tbl[0].key, "hdr_count", 10);
		s_args_tbl[0].key_size = 10;
	}
	if (fault == 13)
		s_args_num = 53;
	if (fault == 14)
		s_init_done = 0;
	if (fault == 15)
		size--;
	if (fault == 16)
		put32(tags + 10 * 76 + 68, 1);
	if (fault == 17)
		tags[get_unaligned_le32(tags + 7 * 76 + 64)] ^= 1;
	if (fault == 18)
		put32(tags + get_unaligned_le32(tags + 7 * 76 + 64) + 20, 13);
	if (fault == 19)
		tags[get_unaligned_le32(tags + 5 * 76 + 64)] = 1;
	if (fault == 20)
		tags[get_unaligned_le32(tags + 1 * 76 + 64) + 13] = 1;
	if (fault == 21)
		tags[get_unaligned_le32(tags + 9 * 76 + 64)] ^= 1;
	if (fault == 22)
		banks.firmware.base += 0x2000000;
	if (fault == 23)
		banks.firmware.capacity = get_unaligned_le32(chk + 172);
	if (fault == 24)
		banks.nc.base = banks.firmware.base + 0x1e000000;
	if (fault == 25)
		banks.cache.base = banks.nc.base + 0x6000000;
	if (fault == 26)
		banks.tags.base = banks.cache.base + 0x7000000;
	if (fault == 27)
		banks.firmware.base = UINT64_MAX & ~0x1ffffffULL;
	if (fault == 28)
		memory[16] ^= 1;
	if (fault == 29)
		memory[12] ^= 1;
	if (fault == 30) {
		unsigned int bytes = get_unaligned_le32(tags + 10 * 76 + 68);
		unsigned int last = bytes - 24;
		put32(memory + last + 4, get_unaligned_le32(memory + last + 4) - 16);
	}
	if (fault == 31)
		nc[8] = 1;
	if (fault == 32)
		cache[0] ^= 1;
	if (fault == 33)
		cache[36] ^= 1;
	if (fault == 34)
		put32(nc + 32, 4);
	if (fault == 35)
		put32(nc + 28, 1);
	if (fault == 36)
		put32(nc + 40 + 16, get_unaligned_le32(nc + 16));
	if (fault == 37)
		tags[get_unaligned_le32(tags + 3 * 76 + 64)] ^= 1;
	if (fault == 38)
		tags[get_unaligned_le32(tags + 3 * 76 + 64) + 8] ^= 1;
	if (fault == 39)
		tags[get_unaligned_le32(tags + 2 * 76 + 64) + 12] ^= 1;
	if (fault == 40)
		tags[get_unaligned_le32(tags + 16 * 76 + 64) + 16] ^= 1;
	if (fault == 41)
		tags[get_unaligned_le32(tags + 18 * 76 + 64) + 8] ^= 1;
	if (fault == 42)
		chk[0x180] ^= 1;
	if (fault == 43)
		put32(chk + 0x18c, get_unaligned_le32(chk + 0x18c) + 65536);
	if (fault == 44)
		put32(chk + 0x190, 2);
	if (fault == 45) {
		put32(chk + 192, 2);
		memcpy(chk + 204, chk + 196, 8);
	}
	if (fault == 46)
		put32(chk + 192, 9);
	if (fault == 47)
		put32(tags + get_unaligned_le32(tags + 8 * 76 + 64), UINT32_MAX);
	if (fault == 48) {
		unsigned int logical = get_unaligned_le32(chk + 172) - 16;
		put32(chk + 172, logical);
		put32(tags + get_unaligned_le32(tags + 1 * 76 + 64) + 8, logical);
	}
	if (fault == 49)
		tags[get_unaligned_le32(tags + 15 * 76 + 64) + 8] ^= 1;
	if (fault == 50)
		banks.nc.base = 1ULL << 35;
	if (fault == 52)
		put32(chk + 0x120, UINT32_MAX);
	if (fault == 53)
		memory[8] ^= 1;
	if (fault == 54) {
		unsigned int bytes = get_unaligned_le32(tags + 10 * 76 + 68);
		put32(memory + bytes - 24 + 12, 1);
	}
	if (fault == 55)
		put32(nc + 32, 0x80000000);
	if (fault == 56)
		cache[8] = 1;
	if (fault == 57)
		banks.cache.capacity -= 65536;
	memcpy(initial_table, s_args_tbl, sizeof(initial_table));
	ret = mtk_ccci_import_owned_tags(tags, size, version, count, fault == 51 ? NULL : &banks);
	if (fault && fault != 58) {
		assert(ret < 0 && !tetris_owned_tags);
		assert(!memcmp(initial_table, s_args_tbl, sizeof(initial_table)));
		assert(s_args_num == (fault == 13 ? 53U : 2U));
		if ((fault >= 23 && fault <= 27) || fault == 50 || fault == 51 || fault == 57)
			assert(copies == 0);
		memcpy(tags, expected, original_size);
		assert(mtk_ccci_import_owned_tags(tags, original_size, 2, 21, source_banks) == ret);
	} else {
		assert(!ret && s_args_num == 23 && copies == 1);
		/* Emulate the exact v2 clear/unmap hazard after successful import. */
		memset(tags, 0xff, size);
		for (unsigned int i = 0; i < 21; i++) {
			const unsigned char *header = expected + i * 76;
			unsigned int at = get_unaligned_le32(header + 64);
			unsigned int bytes = get_unaligned_le32(header + 68);
			assert(bytes <= sizeof(result));
			assert(mtk_ccci_find_args_val((const char *)header, NULL, 0) == (int)bytes);
			assert(mtk_ccci_find_args_val((const char *)header, result, bytes) == (int)bytes);
			assert(!memcmp(result, expected + at, bytes));
			assert(mtk_ccci_find_args_val((const char *)header, result, bytes - 1) < 0);
		}
		assert(copies == 1); /* Lookup uses private normal memory, not released I/O. */
		assert(mtk_ccci_import_owned_tags(tags, size, 2, 21, source_banks) == -EALREADY);
	}
	free(expected);
	puts("actual U-Boot producer -> kernel args lookup: PASS (metadata, not AUTH/READY)");
}
