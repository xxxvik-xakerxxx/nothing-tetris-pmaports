/* SPDX-License-Identifier: GPL-2.0+ */
/* Public stock metadata + synthetic hardware report, NOT a BROM/AUTH test. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tetris_modem_ccci_tags.h"

static unsigned int word(const unsigned char *p)
{
	return (unsigned int)p[0] | (unsigned int)p[1] << 8 |
		(unsigned int)p[2] << 16 | (unsigned int)p[3] << 24;
}

int main(int argc, char **argv)
{
	static const unsigned char pin[32] =
		"\x5d\x2b\xed\xd0\x00\x49\xfc\xed\x98\x3d\x3a\xe5\x39\x89\x61\x6c"
		"\x5c\x9f\x46\xc4\xed\xdd\x32\xa0\x1a\x1a\xd4\x6f\xf8\xd2\xc5\x0f";
	struct tetris_modem_loaded_report report = { 0 };
	struct tetris_modem_boot_plan plan = { 0 };
	unsigned char header[512], footer[512], buffer[16384], *rom;
	unsigned int rom_size, dsp_size = 0, i;
	long offset;
	FILE *file;
	int which, ret;
	assert(argc == 3);
	which = atoi(argv[2]);
	assert(which >= 0 && which < 9);
	file = fopen(argv[1], "rb");
	assert(file && fread(header, 1, 512, file) == 512);
	assert(word(header) == 0x58881688 && !strcmp((char *)header + 8, "md1rom"));
	rom_size = word(header + 4);
	assert(rom_size >= 512 && rom_size <= 64U * 1024 * 1024);
	rom = malloc(rom_size);
	assert(rom && fread(rom, 1, rom_size, file) == rom_size);
	offset = (long)((512UL + rom_size + 15) & ~15UL);
	for (i = 0; i < 128 && !dsp_size; i++) {
		assert(!fseek(file, offset, SEEK_SET));
		assert(fread(header, 1, 512, file) == 512 && word(header) == 0x58881688);
		if (!strcmp((char *)header + 8, "md1dsp"))
			dsp_size = word(header + 4);
		offset += (long)((512UL + word(header + 4) + 15) & ~15UL);
	}
	assert(dsp_size);
	fclose(file);
	report.bootstrap.resources = (struct tetris_modem_emi_resources) {
		.firmware = { 0x80000000ULL, 0x20000000ULL },
		.nc = { 0xa0000000ULL, 0x8000000ULL },
		.cache = { 0xc0000000ULL, 0x8000000ULL },
		.dram_base = 0x40000000ULL, .dram_size = 0x100000000ULL,
	};
	assert(!tetris_modem_emi_rows_b41(rom, rom_size, dsp_size,
		&report.bootstrap.resources, 1, "0", pin, &report.bootstrap.rows));
	assert(!tetris_modem_plan_layout(rom, rom_size, dsp_size,
		report.bootstrap.resources.firmware.capacity, &plan.layout));
	plan.smem_inputs = report.bootstrap.rows.smem_inputs;
	plan.smem = report.bootstrap.rows.smem;
	memcpy(footer, rom + rom_size - 512, 512);
	/* Snapshot is gone; producer uses only retained authenticated-shape data. */
	memset(rom, 0xee, rom_size);
	free(rom);
	report.stage = TETRIS_MD_LOAD_COMPLETE;
	report.hardware.stage = TETRIS_MD_BOOT_COMPLETE;
	report.hardware.reply[2] = report.hardware.reply[3] = 0x100000001ULL;
	if (which == 1)
		report.error = -1;
	if (which == 2)
		report.hardware.reply[3] = 1;
	if (which == 3)
		footer[0] ^= 1;
	if (which == 4)
		plan.smem_inputs.ccb_gear = 0;
	if (which == 5)
		plan.smem.nc_capacity++;
	if (which == 6)
		report.bootstrap.resources.nc.capacity = 1;
	if (which == 8)
		report.bootstrap.resources.sib.capacity = 0x100000;
	memset(buffer, 0xa5, sizeof(buffer));
	ret = tetris_modem_build_linux_tags(&plan, footer, &report, buffer,
		which == 7 ? 1 : sizeof(buffer));
	if (which) {
		assert(ret < 0);
		for (i = 0; i < sizeof(buffer); i++)
			assert(buffer[i] == 0xa5);
		return 0;
	}
	assert(ret > 0 && ret <= (int)sizeof(buffer));
	for (i = 0; i < TETRIS_MODEM_LINUX_TAG_COUNT; i++) {
		const unsigned char *tag = buffer + i * 76;
		unsigned int at = word(tag + 64), size = word(tag + 68);
		assert(at >= TETRIS_MODEM_LINUX_TAG_COUNT * 76 && at <= (unsigned int)ret);
		assert(size <= (unsigned int)ret - at);
		assert(word(tag + 72) == (i + 1 < TETRIS_MODEM_LINUX_TAG_COUNT ? (i + 1) * 76 : 0));
		if (!strcmp((char *)tag, "md1_chk"))
			assert(size == 512 && !memcmp(buffer + at, footer, 512));
		if (!strcmp((char *)tag, "md_mem_layout")) {
			unsigned int row, end = 0;

			assert(size && !(size % 24));
			for (row = 0; row < size; row += 24) {
				const unsigned char *block = buffer + at + row;

				assert(word(block) == end);
				assert(word(block + 4) <= report.bootstrap.resources.firmware.capacity - end);
				end += word(block + 4);
			}
			assert(end == report.bootstrap.resources.firmware.capacity);
			assert(end > plan.layout.memory_size); /* Preserve the owned allocation tail. */
		}
		if (!strcmp((char *)tag, "free_in_kernel"))
			assert(size == 4 && !word(buffer + at));
		if (!strcmp((char *)tag, "md1_smem_cahce_offset"))
			assert(size == 4 && word(buffer + at) == 0x8000000);
	}
	return 0;
}
