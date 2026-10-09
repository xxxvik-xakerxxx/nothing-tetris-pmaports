/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "mt6878-camera-ccd-cq.h"

static unsigned int get32(const unsigned char *p)
{
	return p[0] | ((unsigned int)p[1] << 8) |
		((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}

static void one_and_split(void)
{
	struct mt6878_ccd_cq cq;
	unsigned char data[4096];
	unsigned int values[512], length, tail, i;

	for (i = 0; i < 512; i++)
		values[i] = 0xaabb0000 + i;
	memset(data, 0xcc, sizeof(data));
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0x100000000ULL,
		0x1a100000, 0x1000));
	assert(!mt6878_ccd_cq_values(&cq, 0x1a100040, values, 512));
	assert(!mt6878_ccd_cq_finish(&cq, &length, &tail));
	assert(length == 36 && tail == 2048);
	/* Stock formula: bank 0x10, low address 0x40, 511-1 words. */
	assert(get32(data) == 0x81fe0040);
	assert(get32(data + 4) == 2048 && get32(data + 8) == 1);
	assert(get32(data + 12) == 0x8000083c);
	assert(get32(data + 16) == 4092 && get32(data + 20) == 1);
	assert(get32(data + 24) == MT6878_CQ_END);
	assert(!get32(data + 28) && !get32(data + 32));
	assert(get32(data + tail) == values[0]);
	assert(get32(data + 4092) == values[511]);
	assert(mt6878_ccd_cq_values(&cq, 0x1a100040, values, 1) == -EALREADY);
	assert(mt6878_ccd_cq_finish(&cq, &length, &tail) == -EALREADY);
}

static void faults(void)
{
	struct mt6878_ccd_cq cq;
	unsigned char data[28], before[28];
	unsigned int values[2] = {0x12345678, 0xabcdef00}, length = 99, tail = 99;

	memset(data, 0x55, sizeof(data));
	memcpy(before, data, sizeof(data));
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0,
		0x1a100000, 0x1000));
	assert(mt6878_ccd_cq_values(&cq, 0x1a100040, values, 2) == -ENOSPC);
	assert(!memcmp(before, data, sizeof(data)));
	assert(cq.head == 0 && cq.tail == sizeof(data));
	assert(mt6878_ccd_cq_values(&cq, 0x1a100040, values, 1) == -ENOSPC);
	assert(mt6878_ccd_cq_finish(&cq, &length, &tail) == -ENOSPC);
	assert(length == 99 && tail == 99);
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0,
		0x1a100000, 0x1000));
	assert(!mt6878_ccd_cq_values(&cq, 0x1a100ffc, values, 1));
	assert(!mt6878_ccd_cq_finish(&cq, &length, &tail));
	assert(length == 24 && tail == 24);
	assert(get32(data + 24) == values[0]);
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0,
		0x1a100000, 0x1000));
	assert(mt6878_ccd_cq_values(&cq, 0x1a100ffc, values, 2) == -ERANGE);
	assert(mt6878_ccd_cq_finish(&cq, &length, &tail) == -ERANGE);
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0,
		0x1a100000, 0x1000));
	assert(mt6878_ccd_cq_values(&cq, 0x1a100041, values, 1) == -ERANGE);
	assert(mt6878_ccd_cq_init(&cq, data, sizeof(data), 1,
		0x1a100000, 0x1000) == -EINVAL);
	assert(mt6878_ccd_cq_init(&cq, data, sizeof(data), (1ULL << 34) - 16,
		0x1a100000, 0x1000) == -EINVAL);
	assert(mt6878_ccd_cq_init(&cq, data, sizeof(data), 0,
		0x1a1ffffc, 8) == -EINVAL);
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0,
		0x1a100000, 0x1000));
	assert(mt6878_ccd_cq_values(&cq, 0x1a100040,
		(const unsigned int *)data, 1) == -EINVAL);
}

static void cookie_recipe(void)
{
	struct mt6878_ccd_cq cq;
	unsigned char data[140], before[140];
	unsigned int tag, command, length, tail, cookie = 0x03001234;

	memset(data, 0x55, sizeof(data));
	memcpy(before, data, sizeof(data));
	assert(!mt6878_ccd_cq_init(&cq, data, 136, 0x200000000ULL,
		0x1a100000, 0x1000));
	assert(mt6878_ccd_cq_frame_cookie(&cq, 0x1a100000, 3, cookie) == -ENOSPC);
	assert(!memcmp(before, data, sizeof(data)));
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0x200000000ULL,
		0x1a100000, 0x1000));
	assert(mt6878_ccd_cq_frame_cookie(&cq, 0x1a100000, 2, cookie) == -ERANGE);
	assert(!memcmp(before, data, sizeof(data)));
	assert(!mt6878_ccd_cq_init(&cq, data, sizeof(data), 0x200000000ULL,
		0x1a100000, 0x1000));
	assert(!mt6878_ccd_cq_frame_cookie(&cq, 0x1a100000, 3, cookie));
	assert(!mt6878_ccd_cq_finish(&cq, &length, &tail));
	assert(length == 108 && tail == 108);
	for (tag = 0; tag < 8; tag++) {
		command = 0x8000057c + tag * 0x40;
		assert(get32(data + tag * 12) == command);
		assert(get32(data + tag * 12 + 4) == 136 - tag * 4);
		assert(get32(data + tag * 12 + 8) == 2);
		assert(get32(data + 136 - tag * 4) == cookie);
	}
	assert(get32(data + 96) == MT6878_CQ_END);
}

int main(void)
{
	one_and_split();
	faults();
	cookie_recipe();
	puts("CAMSV CCD CQ native fixtures PASS");
	return 0;
}
