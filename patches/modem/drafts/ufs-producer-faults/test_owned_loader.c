/* SPDX-License-Identifier: GPL-2.0+ */
/* Keep frozen 17-case boundaries, compile ACTUAL reviewed production owner.
 * All auth/firmware/SMC boundaries remain doubles, never an AUTH claim.
 */
#define tetris_modem_load_slot_rows_b41 old_rows_boundary
#define tetris_modem_bootstrap_once old_boot_boundary
#define tetris_modem_bootstrap_report old_report_boundary
#define main frozen_case_main
#include "baseline_fixture.inc"
#undef main
#undef tetris_modem_bootstrap_report
#undef tetris_modem_bootstrap_once
#undef tetris_modem_load_slot_rows_b41
#include "tetris_modem_final.h"
#include "tetris_modem_ccci_tags.h"

static const struct tetris_modem_boot_plan *captured_plan;
static const unsigned char *captured_footer;
static unsigned int encoded, extra;

int tetris_modem_load_slot_handoff_b41(struct blk_desc *dev, char slot,
		const unsigned char root[32], const struct tetris_scp_security_ops *ops,
		void *destination, size_t capacity, unsigned int ccb, const char *phy,
		const unsigned char pin[32], const struct tetris_modem_emi_resources *resources,
		struct tetris_modem_boot_plan *plan, struct tetris_modem_emi_rows *rows,
		unsigned char footer[512])
{
	int ret = old_rows_boundary(dev, slot, root, ops, destination, capacity,
		ccb, phy, pin, resources, plan, rows);
	if (!ret) {
		plan->layout.rom_size = 55396432;
		memset(footer, 0x23, 512);
		captured_plan = plan;
		captured_footer = footer;
	}
	return ret;
}

int tetris_modem_bootstrap_once(struct blk_desc *dev,
		const struct tetris_modem_bootstrap_plan *plan)
{
	unsigned char output[64];
	memset(output, 0xa5, sizeof(output));
	assert(tetris_modem_loaded_encode_tags(output, sizeof(output)) == -EAGAIN);
	assert(!encoded);
	for (size_t i = 0; i < sizeof(output); i++)
		assert(output[i] == 0xa5);
	return old_boot_boundary(dev, plan);
}

/* The baseline macro also renames the same-spelled struct tag in its header;
 * this is still the exact included production layout, not a new fixture ABI.
 */
int tetris_modem_bootstrap_report(struct old_report_boundary *report)
{
	int ret = old_report_boundary(report);
	if (extra == 17)
		return -EIO;
	report->stage = fault == 10 ? TETRIS_MD_BOOT_BROM : TETRIS_MD_BOOT_COMPLETE;
	report->error = fault == 10 ? -ETIMEDOUT : 0;
	if (!report->error)
		report->reply[2] = report->reply[3] = 0x100000001ULL;
	return ret;
}

int tetris_modem_build_linux_tags(const struct tetris_modem_boot_plan *plan,
		const unsigned char footer[512], const struct tetris_modem_loaded_report *report,
		void *buffer, size_t size)
{
	assert(plan == captured_plan && footer == captured_footer);
	assert(plan->layout.rom_size == 55396432 && size >= 64);
	assert(report->stage == TETRIS_MD_LOAD_COMPLETE && !report->error);
	assert(report->hardware.stage == TETRIS_MD_BOOT_COMPLETE && !report->hardware.error);
	assert(report->hardware.reply[2] == 0x100000001ULL && report->hardware.reply[3] == 0x100000001ULL);
	for (unsigned int i = 0; i < 512; i++)
		assert(footer[i] == 0x23);
	encoded++;
	if (extra == 18)
		return -ENOSPC;
	memset(buffer, 0x23, 64);
	return 64;
}

int main(int argc, char **argv)
{
	unsigned char output[64];
	struct tetris_modem_loaded_report report;
	int ret;
	assert(argc == 2);
	extra = (unsigned int)atoi(argv[1]);
	assert(extra <= 18);
	memset(output, 0xa5, sizeof(output));
	assert(tetris_modem_loaded_encode_tags(output, sizeof(output)) == -EAGAIN && !encoded);
	if (extra <= 16) {
		assert(!frozen_case_main(argc, argv)); /* ALL original first-error/repeat checks */
	} else if (extra == 18) {
		char zero[] = "0";
		char *args[] = { argv[0], zero };
		assert(!frozen_case_main(2, args));
	} else {
		/* Same independently pinned preloader bytes as the frozen fixture. */
		const unsigned char pin[32] =
			"\x5d\x2b\xed\xd0\x00\x49\xfc\xed\x98\x3d\x3a\xe5\x39\x89\x61\x6c"
			"\x5c\x9f\x46\xc4\xed\xdd\x32\xa0\x1a\x1a\xd4\x6f\xf8\xd2\xc5\x0f";
		struct blk_desc dev = { 0 };
		unsigned int before;
		ret = tetris_modem_loaded_boot_once(&dev, &dev, 'a', 1, "1", pin);
		assert(ret == -EPROTO && !tetris_modem_loaded_boot_report(&report));
		assert(report.error == ret && report.stage == TETRIS_MD_LOAD_BOOTSTRAP);
		before = calls;
		assert(tetris_modem_loaded_boot_once(&dev, &dev, 'a', 1, "1", pin) == ret);
		assert(calls == before);
	}
	ret = tetris_modem_loaded_encode_tags(output, sizeof(output));
	if (extra == 0) {
		assert(ret == 64 && encoded == 1);
	} else {
		assert(ret == (extra == 18 ? -ENOSPC : -EAGAIN));
		assert(encoded == (extra == 18));
		for (size_t i = 0; i < sizeof(output); i++)
			assert(output[i] == 0xa5);
	}
	return 0;
}
