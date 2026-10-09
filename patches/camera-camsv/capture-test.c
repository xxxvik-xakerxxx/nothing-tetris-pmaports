/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "mt6878-camsv-capture.h"

struct fake {
	unsigned int calls, fail_at, reads, writes, owners, busy, clamp;
	int unsupported;
	unsigned int registers[4][0x18000 / 4];
};
static struct fake fake;

static int tick(void)
{
	return ++fake.calls == fake.fail_at ? -EIO : 0;
}

static int verify(void *context, enum mt6878_camsv_owner owner,
	const struct mt6878_camsv_job *job)
{
	int ret = tick();

	(void)context;
	(void)job;
	if (owner != MT6878_SV_STOPPED) {
		assert(!fake.reads && !fake.writes);
		assert((unsigned int)owner == fake.owners++);
	}
	return ret ? ret : (int)owner == fake.unsupported ? -EOPNOTSUPP : 0;
}

static int read_reg(void *context, enum mt6878_camsv_region region,
	unsigned int offset, unsigned int *value)
{
	int ret = tick();

	(void)context;
	assert(region <= MT6878_SV_SENINF && !(offset & 3));
	fake.reads++;
	if (!ret)
		*value = ((region == MT6878_SV_DMA && offset == SV_DMA_RESET) ||
			(region == MT6878_SV_CQ && offset == SV_CQ_RESET)) ?
			(fake.busy ? 0 : 2) : fake.registers[region][offset / 4];
	return ret;
}

static int write_reg(void *context, enum mt6878_camsv_region region,
	unsigned int offset, unsigned int value)
{
	int ret = tick();

	(void)context;
	assert(fake.owners == 5);
	assert(region <= MT6878_SV_SENINF && !(offset & 3));
	if (!ret) {
		fake.writes++;
		fake.registers[region][offset / 4] = value;
	}
	return ret;
}

static int barrier(void *context)
{
	(void)context;
	return tick();
}

static int delay(void *context, unsigned int us)
{
	(void)context;
	assert(us == 1);
	return tick();
}

static int clamp(void *context, unsigned int common, unsigned int enable)
{
	int ret = tick();

	(void)context;
	assert(common == 31);
	if (!ret)
		fake.clamp = enable;
	return ret;
}

static void reset(struct mt6878_camsv_transaction *tx)
{
	memset(&fake, 0, sizeof(fake));
	fake.unsupported = -1;
	memset(tx, 0, sizeof(*tx));
}

int main(void)
{
	struct mt6878_camsv_backend io = {
		verify, read_reg, write_reg, barrier, delay, clamp, &fake,
		{ 0x1000, 0x1000, 0x1000, 0x18000 }
	};
	struct mt6878_camsv_job job = {
		.width = 4000, .height = 3000, .sequence = 42, .raw_tag = 0, .pdaf_tag = 1,
		.group_tags = { 1, 2, 0, 0 },
		.raw = { 0x100000, 15072000, 1 }, .pdaf = { 0x2000000, 3000000, 1 },
		.raw_layout = { SV_DMA_FMT_BAYER10, 4000, 3000, 5024, 15072000, 4 },
		.pdaf_layout = { SV_DMA_FMT_BAYER8, 4000, 750, 4000, 3000000, 4 },
		.cq = { 0x100000000ULL, 128, 1 }
	};
	struct mt6878_camsv_transaction tx;
	unsigned int total, i, before, stop_total;

	reset(&tx);
	assert(mt6878_camsv_submit(&io, &tx, &job) == 0);
	total = fake.calls;
	assert(fake.registers[MT6878_SV_CQ][SV_CQ_SIZE / 4] == 128);
	assert(fake.registers[MT6878_SV_CQ][SV_CQ_MSB / 4] == 1);
	assert(fake.registers[MT6878_SV_CQ][SV_CQ_LSB / 4] == 0);
	assert(fake.registers[MT6878_SV_SENINF][0x17004 / 4] == 0xab80);
	assert(fake.registers[MT6878_SV_SENINF][0x17044 / 4] == 0xb080);
	assert(mt6878_camsv_submit(&io, &tx, &job) == -EALREADY);
	assert(fake.calls == total);
	assert(mt6878_camsv_done(&tx, 1U << 16, 41) == -ESTALE);
	assert(!tx.complete_tags);
	assert(mt6878_camsv_done(&tx, 1U << 16, 42) == 0);
	assert(mt6878_camsv_done(&tx, 1U << 16, 42) == -EALREADY);
	assert(mt6878_camsv_done(&tx, 1U << 17, 42) == 1);
	before = fake.calls;
	assert(mt6878_camsv_stop(&io, &tx) == 0);
	stop_total = fake.calls - before;
	assert(tx.quiesced && !fake.clamp);
	assert(mt6878_camsv_stop(&io, &tx) == -EALREADY);
	for (i = 1; i <= total; i++) {
		reset(&tx);
		fake.fail_at = i;
		assert(mt6878_camsv_submit(&io, &tx, &job) == -EIO);
		assert(fake.calls == i && tx.first_error == -EIO && !tx.submitted);
		assert(mt6878_camsv_submit(&io, &tx, &job) == -EIO);
		assert(fake.calls == i);
	}
	for (i = 0; i < 5; i++) {
		reset(&tx);
		fake.unsupported = i;
		assert(mt6878_camsv_submit(&io, &tx, &job) == -EOPNOTSUPP);
		assert(!fake.reads && !fake.writes);
	}
	for (i = 1; i <= stop_total; i++) {
		reset(&tx);
		assert(mt6878_camsv_submit(&io, &tx, &job) == 0);
		before = fake.calls;
		fake.fail_at = before + i;
		assert(mt6878_camsv_stop(&io, &tx) == -EIO);
		assert(fake.calls == before + i && !tx.quiesced);
	}
	reset(&tx);
	assert(mt6878_camsv_submit(&io, &tx, &job) == 0);
	fake.busy = 1;
	assert(mt6878_camsv_stop(&io, &tx) == -ETIMEDOUT);
	assert(!tx.quiesced && fake.clamp);
	reset(&tx);
	fake.fail_at = total;
	assert(mt6878_camsv_submit(&io, &tx, &job) == -EIO);
	fake.fail_at = 0;
	assert(mt6878_camsv_stop(&io, &tx) == -EIO);
	assert(tx.quiesced && tx.first_error == -EIO);
	reset(&tx);
	job.raw.mapped = 0;
	assert(mt6878_camsv_submit(&io, &tx, &job) == -EINVAL && !fake.calls);
	job.raw.mapped = 1;
	job.pdaf.dma = job.raw.dma;
	assert(mt6878_camsv_validate(&io, &job) == -EINVAL);
	job.pdaf.dma = 0x2000000;
	job.cq.dma = 1ULL << 34;
	assert(mt6878_camsv_validate(&io, &job) == -EINVAL);
	job.cq.dma = 0x100000000ULL;
	job.sv_id = 4;
	assert(mt6878_camsv_validate(&io, &job) == -EINVAL);
	job.sv_id = 1;
	job.group_tags[1] = 1;
	assert(mt6878_camsv_validate(&io, &job) == -EINVAL);
	job.group_tags[1] = 2;
	reset(&tx);
	assert(mt6878_camsv_submit(&io, &tx, &job) == 0);
	assert(fake.registers[MT6878_SV_SENINF][0x17204 / 4] == 0xab80);
	assert(mt6878_camsv_stop(&io, &tx) == 0);
	/* Explicit output contracts for both modes; no packet-size ratio. */
	for (i = 0; i < 2; i++) {
		struct mt6878_camsv_job invalid;
		unsigned int w = i ? 4096 : 4000, h = i ? 2304 : 3000;
		unsigned int stride = i ? 5120 : 5024;

		job.width = w; job.height = h;
		job.raw_layout = (struct mt6878_camsv_dma_layout){
			SV_DMA_FMT_BAYER10, w, h, stride, stride * h, 4 };
		job.pdaf_layout = (struct mt6878_camsv_dma_layout){
			SV_DMA_FMT_BAYER8, w, h / 4, w, w * (h / 4), 4 };
		job.raw.size = job.raw_layout.sizeimage;
		job.pdaf.size = job.pdaf_layout.sizeimage;
		reset(&tx);
		assert(!mt6878_camsv_submit(&io, &tx, &job));
		job.pdaf_layout.sizeimage = 1; /* Submitted copy cannot change. */
		assert(tx.job.pdaf_layout.sizeimage == w * (h / 4));
		job = tx.job;
		invalid = job; invalid.pdaf.size--;
		reset(&tx);
		assert(mt6878_camsv_submit(&io, &tx, &invalid) == -EINVAL && !fake.calls);
		invalid = job; invalid.raw_layout.bytesperline--;
		reset(&tx);
		assert(mt6878_camsv_submit(&io, &tx, &invalid) == -EINVAL && !fake.calls);
		invalid = job; invalid.pdaf_layout.sizeimage++;
		reset(&tx);
		assert(mt6878_camsv_submit(&io, &tx, &invalid) == -EINVAL && !fake.calls);
		invalid = job; invalid.pdaf_layout.format = SV_DMA_FMT_BAYER10;
		reset(&tx);
		assert(mt6878_camsv_submit(&io, &tx, &invalid) == -EINVAL && !fake.calls);
		/* A different, explicitly proved 10-bit DMA format needs its own
		 * padded stride and capacity; never infer this from wire DT30.
		 */
		job.pdaf_layout.format = SV_DMA_FMT_BAYER10;
		job.pdaf_layout.bytesperline = stride;
		job.pdaf_layout.sizeimage = stride * (h / 4);
		job.pdaf.size = job.pdaf_layout.sizeimage;
		reset(&tx);
		assert(!mt6878_camsv_submit(&io, &tx, &job));
	}
	puts("PASS: CQ/VC order, paired group completion, IOVA guards, all callback faults and bounded reset");
	return 0;
}
