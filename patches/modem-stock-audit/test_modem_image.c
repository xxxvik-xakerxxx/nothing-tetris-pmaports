/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "modem_image.h"
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned char image[4096], before[4096];
static unsigned int checks;

static void put32(size_t at, uint32_t value)
{
	for (unsigned int i = 0; i < 4; i++)
		image[at + i] = value >> (8 * i);
}

static void header(size_t at, const char *name, uint32_t size, uint32_t alignment)
{
	memset(image + at, 0, 512);
	put32(at, 0x58881688);
	put32(at + 4, size);
	strcpy((char *)image + at + 8, name);
	put32(at + 0x44, alignment);
}

static void expect(enum tetris_modem_member member, size_t extent,
	size_t limit, size_t budget, int error, size_t offset, size_t length)
{
	struct tetris_modem_span result = { 7, 8, 9 }, saved = result;
	int ret;

	memcpy(before, image, sizeof(image));
	ret = tetris_modem_find_member(image, extent, member, limit, budget, &result);
	assert(ret == error);
	assert(!memcmp(before, image, sizeof(image)));
	if (error)
		assert(!memcmp(&saved, &result, sizeof(result)));
	else {
		assert(result.header_offset == offset);
		assert(result.payload_offset == offset + 512);
		assert(result.payload_size == length);
	}
	checks++;
}

int main(void)
{
	const char *inventory[] = { "modem_b", "md1img_a", "modem_a" };
	const char *duplicate[] = { "modem_a", "modem_a" };
	const char *fallback[] = { "modem", "md1img", "modem_b" };
	const char *selected = "unchanged";

	assert(!tetris_modem_partition(TETRIS_MODEM_SLOT_A, inventory, 3, &selected));
	assert(!strcmp(selected, "modem_a"));
	assert(!tetris_modem_partition(TETRIS_MODEM_SLOT_B, inventory, 3, &selected));
	assert(!strcmp(selected, "modem_b"));
	assert(tetris_modem_partition(TETRIS_MODEM_SLOT_A, duplicate, 2, &selected) == -EEXIST);
	assert(tetris_modem_partition(TETRIS_MODEM_SLOT_A, fallback, 3, &selected) == -ENOENT);
	assert(tetris_modem_partition(42, inventory, 3, &selected) == -EINVAL);
	assert(!strcmp(selected, "modem_b"));
	checks += 5;

	header(0, "md1rom", 513, 512);
	header(1536, "md1dsp", 16, 512);
	header(2560, "md1drdi", 32, 512);
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 4, 0, 0, 513);
	expect(TETRIS_MODEM_DSP, sizeof(image), 1024, 4, 0, 1536, 16);
	expect(TETRIS_MODEM_DRDI, sizeof(image), 1024, 4, 0, 2560, 32);
	expect(TETRIS_MODEM_ROM, sizeof(image), 512, 4, -EFBIG, 0, 0);
	expect(TETRIS_MODEM_DSP, sizeof(image), 1024, 1, -E2BIG, 0, 0);
	expect(TETRIS_MODEM_ROM, 511, 1024, 4, -EMSGSIZE, 0, 0);
	expect(TETRIS_MODEM_ROM, 1024, 1024, 4, -EMSGSIZE, 0, 0);
	expect(TETRIS_MODEM_DSP, 1536, 1024, 4, -ENOENT, 0, 0);
	expect(TETRIS_MODEM_DSP, 1200, 1024, 4, -EMSGSIZE, 0, 0);
	put32(0, 0x1eabb7d7); /* Alternative signed container is unsupported. */
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 4, -EPROTONOSUPPORT, 0, 0);
	header(0, "md1rom", 16, 0);
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 4, -EBADMSG, 0, 0);
	put32(0x44, 3);
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 4, -EBADMSG, 0, 0);
	put32(0x44, 512);
	put32(4, 0);
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 4, -EBADMSG, 0, 0);
	put32(4, UINT32_MAX);
	expect(TETRIS_MODEM_ROM, sizeof(image), SIZE_MAX, 4, -EMSGSIZE, 0, 0);
	header(0, "other", 16, 0x80000000U);
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 4, -EMSGSIZE, 0, 0);
	header(0, "md1rom", 16, 512);
	memset(image + 8, 'x', 32);
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 4, -EBADMSG, 0, 0);
	expect(42, sizeof(image), 1024, 4, -EINVAL, 0, 0);
	expect(TETRIS_MODEM_ROM, sizeof(image), 1024, 0, -EINVAL, 0, 0);
	printf("PASS: %u modem selection/extent cases; input and error output unchanged\n", checks);
	return 0;
}
