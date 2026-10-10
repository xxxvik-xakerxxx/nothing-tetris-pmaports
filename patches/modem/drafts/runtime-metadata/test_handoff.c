/* SPDX-License-Identifier: GPL-2.0-only */
/* CI-only actual production wire decoder; fabricated bytes are NOT attestation. */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint64_t u64;
typedef int32_t s32;
#define U64_MAX UINT64_MAX
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
static uint32_t get_unaligned_le32(const void *p)
{
	const u8 *b = p;
	return (uint32_t)b[0] | (uint32_t)b[1] << 8 |
		(uint32_t)b[2] << 16 | (uint32_t)b[3] << 24;
}
static u64 get_unaligned_le64(const void *p)
{
	const u8 *b = p;
	return (u64)get_unaligned_le32(b) | (u64)get_unaligned_le32(b + 4) << 32;
}
static void put32(u8 *p, uint32_t value)
{
	for (unsigned int i = 0; i < 4; i++)
		p[i] = (u8)(value >> (8 * i));
}
/* DECODERS */
int main(void)
{
	u8 good[80] = { 0 }, report[80], descriptor[32] = { 0 }, changed[32];
	u64 base;
	unsigned int used;
	static const unsigned int error_offsets[] = { 4, 8, 16, 24, 32 };

	put32(good, 1);
	put32(good + 12, 11);
	put32(good + 20, 15);
	put32(good + 64, 1);
	put32(good + 68, 1);
	put32(good + 72, 1);
	put32(good + 76, 1);
	assert(!tetris_brom_result(good, 80));
	assert(tetris_brom_result(NULL, 0) == -ENODATA);
	for (int length = 0; length <= 81; length++) {
		if (length != 80)
			assert(tetris_brom_result(good, length) == -EBADMSG);
	}
	for (unsigned int i = 0; i < ARRAY_SIZE(error_offsets); i++) {
		memcpy(report, good, 80);
		put32(report + error_offsets[i], (uint32_t)-EIO);
		assert(tetris_brom_result(report, 80) == -EIO);
		put32(report + error_offsets[i], 1);
		assert(tetris_brom_result(report, 80) == -EBADMSG);
	}
	memcpy(report, good, 80);
	put32(report + 4, (uint32_t)-ENOMEM);
	put32(report + 32, (uint32_t)-EIO);
	assert(tetris_brom_result(report, 80) == -ENOMEM);
	for (unsigned int i = 64; i < 80; i++) {
		memcpy(report, good, 80);
		report[i] ^= 1;
		assert(tetris_brom_result(report, 80) == -EAGAIN);
	}
	/* Address in report[40] deliberately irrelevant to descriptor admission. */
	memcpy(report, good, 80);
	memset(report + 40, 0xff, 8);
	assert(!tetris_brom_result(report, 80));
	put32(descriptor, 0x1000); /* Synthetic fixture, never physical mapping. */
	put32(descriptor + 8, 21 * 76);
	put32(descriptor + 16, 2);
	put32(descriptor + 20, 21);
	assert(!tetris_descriptor_bytes(descriptor, 32, &base, &used));
	assert(base == 0x1000 && used == 21 * 76);
	assert(tetris_descriptor_bytes(NULL, 0, &base, &used) == -ENODATA);
	for (int length = 0; length <= 33; length++) {
		if (length != 32)
			assert(tetris_descriptor_bytes(descriptor, length, &base, &used) == -EBADMSG);
	}
	for (unsigned int i = 12; i < 32; i += 4) {
		memcpy(changed, descriptor, 32);
		changed[i] ^= 1;
		assert(tetris_descriptor_bytes(changed, 32, &base, &used) == -EBADMSG);
	}
	memcpy(changed, descriptor, 32);
	put32(changed + 8, 65537);
	assert(tetris_descriptor_bytes(changed, 32, &base, &used) == -EBADMSG);
	memset(changed, 0xff, 8);
	assert(tetris_descriptor_bytes(changed, 32, &base, &used) == -EBADMSG);
	return 0;
}
