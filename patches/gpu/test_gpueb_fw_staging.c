/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
struct device { int unused; };
struct firmware { const u8 *data; size_t size; };
#define GFP_KERNEL 0
static unsigned int requests, releases, allocations, frees;
static int request_error;
static struct firmware fixture;
static u32 get_unaligned_le32(const void *pointer)
{
	const u8 *p = pointer;
	return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24;
}
static void *kzalloc(size_t size, int flags)
{
	(void)flags; allocations++;
	return calloc(1, size);
}
static void kfree(void *pointer) { frees++; free(pointer); }
static int request_firmware(const struct firmware **out, const char *name, struct device *dev)
{
	assert(name && dev); requests++;
	if (request_error)
		return request_error;
	*out = &fixture;
	return 0;
}
static void release_firmware(const struct firmware *firmware)
{
	assert(firmware == &fixture); releases++;
}
#include "gpueb-fw-staging.h"

static void put32(u8 *p, u32 value)
{
	p[0] = value; p[1] = value >> 8; p[2] = value >> 16; p[3] = value >> 24;
}

static size_t build(u8 *data)
{
	static const char names[][32] = { "tinysys-gpueb-RV33_A", "cert1", "cert2",
		"tinysys-gpueb-RV33_A_xfile", "cert1", "cert2" };
	size_t offset = 0;
	unsigned int i;
	memset(data, 0, 4096);
	for (i = 0; i < 6; i++) {
		u8 *h = data + offset;
		u32 size = i == 0 ? 16 : 3;
		put32(h, 0x58881688); put32(h + 4, size);
		memcpy(h + 8, names[i], 32);
		put32(h + 48, 0x58891689); put32(h + 52, 512);
		put32(h + 56, 1);
		put32(h + 60, i % 3 == 0 ? 0 : (i % 3 == 1 ? 0x02000000 : 0x02000002));
		put32(h + 68, 16); put32(h + 76, i % 3 ? 0x22345678 : 0);
		memset(h + 512, 0x55, size);
		offset = (offset + 512 + size + 15) & ~(size_t)15;
	}
	return offset;
}

int main(void)
{
	u8 data[4096], original[4096];
	struct mt6878_gpueb_fw_section sections[6], zero[6] = {};
	struct mt6878_gpueb_firmware *image;
	struct device dev = {};
	size_t size = build(data);
	unsigned int i;
	static const unsigned int offsets[] = { 0, 4, 8, 48, 52, 56, 60, 68, 72, 76 };
	memcpy(original, data, sizeof(data));
	assert(mt6878_gpueb_fw_parse(data, size, sections) == 0);
	assert(sections[0].payload_offset == 512 && sections[0].payload_size == 16);
	for (i = 0; i < sizeof(offsets) / sizeof(offsets[0]); i++) {
		memcpy(data, original, sizeof(data)); data[offsets[i]] ^= 255;
		memset(sections, 0x5a, sizeof(sections));
		assert(mt6878_gpueb_fw_parse(data, size, sections) < 0);
		assert(memcmp(sections, zero, sizeof(zero)) == 0);
	}
	for (i = 0; i < size; i++) {
		assert(mt6878_gpueb_fw_parse(original, i, sections) < 0);
		assert(memcmp(sections, zero, sizeof(zero)) == 0);
	}
	memcpy(data, original, sizeof(data)); data[size] = 1;
	assert(mt6878_gpueb_fw_parse(data, size + 1, sections) < 0);
	memcpy(data, original, sizeof(data)); data[528 + 512 + 3] = 1;
	assert(mt6878_gpueb_fw_parse(data, size, sections) < 0);
	assert(mt6878_gpueb_fw_parse(original, SIZE_MAX, sections) < 0);
	assert(mt6878_gpueb_fw_parse(NULL, size, sections) < 0);
	assert(mt6878_gpueb_fw_parse(original, size, NULL) < 0);
	memcpy(data, original, sizeof(data));
	fixture.data = original; fixture.size = size;
	request_error = -ENOENT; image = (void *)1;
	assert(mt6878_gpueb_fw_request(&dev, "gpueb.img", &image) == -ENOENT);
	assert(!image && requests == 1 && releases == 0 && allocations == frees);
	request_error = 0; fixture.size = 511;
	assert(mt6878_gpueb_fw_request(&dev, "gpueb.img", &image) < 0);
	assert(!image && releases == 1 && allocations == frees);
	fixture.size = size;
	assert(mt6878_gpueb_fw_request(&dev, "gpueb.img", &image) == 0);
	assert(image->firmware == &fixture && releases == 1);
	mt6878_gpueb_fw_release(image);
	assert(releases == 2 && allocations == frees);
	assert(mt6878_gpueb_fw_request(NULL, "gpueb.img", &image) == -EINVAL);
	assert(!image);
	assert(mt6878_gpueb_fw_request(&dev, "", &image) == -EINVAL);
	assert(mt6878_gpueb_fw_request(&dev, "gpueb.img", NULL) == -EINVAL);
	mt6878_gpueb_fw_release(NULL);
	assert(memcmp(data, fixture.data, sizeof(data)) == 0);
	puts("PASS: production RV33 parser bounds/output atomicity and firmware reference lifecycle");
	return 0;
}
