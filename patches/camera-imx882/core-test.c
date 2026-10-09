/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "imx882-stream-core.h"

struct recording {
	struct imx882_reg writes[32];
	unsigned int count;
	unsigned int fail_at;
	unsigned int fail_release;
};

static int record(void *context, unsigned short address, unsigned char value)
{
	struct recording *recording = context;

	assert(recording->count < 32);
	recording->writes[recording->count++] =
		(struct imx882_reg) { address, value };
	if (recording->count == recording->fail_at)
		return -121;
	if (recording->fail_release && address == 0x0104 && value == 0)
		return -5;
	return 0;
}

int main(void)
{
	struct recording recording = { 0 };
	struct imx882_bus bus = { record, &recording };
	const struct imx882_reg table[] = {
		{ 0x0136, 0x18 }, { 0x0137, 0 }, { 0x0340, 0x0f },
	};
	unsigned int i;

	assert(imx882_write_controls(&bus, 3900, 1000, 4096) == 0);
	assert(recording.count == 9);
	assert(recording.writes[0].address == 0x0104);
	assert(recording.writes[0].value == 1);
	assert(recording.writes[1].address == 0x0340);
	assert(recording.writes[1].value == 0x0f);
	assert(recording.writes[2].value == 0x3c);
	assert(recording.writes[3].address == 0x0350);
	assert(recording.writes[3].value == 0);
	assert(recording.writes[4].address == 0x0202);
	assert(recording.writes[4].value == 3);
	assert(recording.writes[5].value == 0xe8);
	assert(recording.writes[6].address == 0x0204);
	assert(recording.writes[6].value == 0x30);
	assert(recording.writes[7].value == 0);
	assert(recording.writes[8].address == 0x0104);
	assert(recording.writes[8].value == 0);

	for (i = 1; i <= 9; i++) {
		memset(&recording, 0, sizeof(recording));
		recording.fail_at = i;
		assert(imx882_write_controls(&bus, 3900, 1000, 4096) == -121);
		assert(recording.count == (i < 9 ? i + 1 : i));
		assert(recording.writes[recording.count - 1].address == 0x0104);
		assert(recording.writes[recording.count - 1].value == 0);
	}
	memset(&recording, 0, sizeof(recording));
	recording.fail_at = 2;
	recording.fail_release = 1;
	assert(imx882_write_controls(&bus, 3900, 1000, 4096) == -121);
	assert(recording.count == 3);
	memset(&recording, 0, sizeof(recording));
	assert(imx882_write_controls(&bus, 3899, 1000, 4096) == -22);
	assert(imx882_write_controls(&bus, 65536, 1000, 4096) == -22);
	assert(imx882_write_controls(&bus, 3900, 3837, 4096) == -22);
	assert(imx882_write_controls(&bus, 3900, 5, 4096) == -22);
	assert(imx882_write_controls(&bus, 3900, 1000, 1462) == -22);
	assert(imx882_write_controls(&bus, 3900, 1000, 65537) == -22);
	assert(recording.count == 0);
	assert(imx882_write_controls(&bus, 65535, 65471, 65536) == 0);
	assert(recording.writes[6].value == 0x3f);
	assert(recording.writes[7].value == 0);
	for (i = 1; i <= 3; i++) {
		memset(&recording, 0, sizeof(recording));
		recording.fail_at = i;
		assert(imx882_write_table(&bus, table, 3) == -121);
		assert(recording.count == i);
	}
	memset(&recording, 0, sizeof(recording));
	assert(imx882_write_table(&bus, table, 3) == 0);
	assert(recording.count == 3);
	puts("IMX882 real transaction core: bounds and all write failures PASS");
	return 0;
}
