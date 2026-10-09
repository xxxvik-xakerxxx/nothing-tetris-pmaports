/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "mt6878-seninf-mux.h"

struct fake {
	unsigned int base[0x18000 / 4];
	unsigned int analog[0x30000 / 4];
	unsigned int calls, fail_at, delays[16], delay_count;
	unsigned int writes, owner_denied;
};
static struct fake fake;

static int tick(struct fake *f)
{
	f->calls++;
	return f->calls == f->fail_at ? -EIO : 0;
}

static int check(void *context, enum mt6878_seninf_action action,
		 const struct mt6878_seninf_plan *plan)
{
	struct fake *f = context;
	int ret = tick(f);

	(void)action;
	(void)plan;
	return ret ? ret : f->owner_denied ? -EACCES : 0;
}

static int read_reg(void *context, enum mt6878_seninf_region region,
		    unsigned int offset, unsigned int *value)
{
	struct fake *f = context;
	int ret = tick(f);

	assert(!(offset & 3));
	assert(offset < (region == MT6878_SENINF_BASE ? 0x18000 : 0x30000));
	if (!ret)
		*value = (region == MT6878_SENINF_BASE ? f->base : f->analog)[offset / 4];
	return ret;
}

static int write_reg(void *context, enum mt6878_seninf_region region,
		     unsigned int offset, unsigned int value)
{
	struct fake *f = context;
	int ret = tick(f);

	assert(!(offset & 3));
	assert(offset < (region == MT6878_SENINF_BASE ? 0x18000 : 0x30000));
	if (!ret) {
		(region == MT6878_SENINF_BASE ? f->base : f->analog)[offset / 4] = value;
		f->writes++;
	}
	return ret;
}

static int delay(void *context, unsigned int microseconds)
{
	struct fake *f = context;
	int ret = tick(f);

	assert(f->delay_count < 16);
	if (!ret)
		f->delays[f->delay_count++] = microseconds;
	return ret;
}

int main(void)
{
	struct mt6878_seninf_backend io = {
		check, read_reg, write_reg, delay, &fake, 0x18000, 0x30000,
	};
	struct mt6878_seninf_plan plan = { 1, 4, 6, 0, 3 };
	struct mt6878_seninf_transaction tx = { 0 };
	unsigned int total, fail, mux_base = 0x6d00;
	int (*operations[])(const struct mt6878_seninf_backend *,
		const struct mt6878_seninf_plan *, struct mt6878_seninf_transaction *) = {
		mt6878_seninf_analog_on, mt6878_seninf_mux_setup,
		mt6878_seninf_receiver_off,
	};
	unsigned int operation;

	assert(mt6878_seninf_analog_on(&io, &plan, &tx) == 0);
	assert(fake.delay_count == 8);
	assert(fake.delays[0] == 200 && fake.delays[1] == 30);
	assert(fake.delays[2] == 1 && fake.delays[3] == 1);
	assert(fake.delays[4] == 200 && fake.delays[5] == 30);
	assert((fake.analog[0x8000 / 4] & 3) == 3);
	assert((fake.analog[0x9000 / 4] & 3) == 3);
	assert((fake.analog[0x8020 / 4] & 0x3f0000) == 0x3f0000);
	fake.base[(mux_base + 4) / 4] = 0xa5000000;
	assert(mt6878_seninf_mux_setup(&io, &plan, &tx) == 0);
	assert(fake.base[mux_base / 4] == 1);
	assert(fake.base[(mux_base + 4) / 4] == 0xa5000308);
	assert(fake.base[(mux_base + 8) / 4] == 8);
	assert(fake.base[0x14 / 4] == 4U << 16);
	assert(mt6878_seninf_receiver_off(&io, &plan, &tx) == 0);
	assert(fake.base[mux_base / 4] == 0);
	assert(fake.base[0x4a00 / 4] == 0);
	assert((fake.analog[0x8000 / 4] & 3) == 0);
	assert((fake.analog[0x9000 / 4] & 3) == 0);
	assert((fake.analog[0x8020 / 4] & 0x3f0000) == 0);
	assert(mt6878_seninf_receiver_off(&io, &plan, &tx) == -EBUSY);

	for (operation = 0; operation < 3; operation++) {
		memset(&fake, 0, sizeof(fake));
		memset(&tx, 0, sizeof(tx));
		assert(operations[operation](&io, &plan, &tx) == 0);
		total = fake.calls;
		for (fail = 1; fail <= total; fail++) {
			memset(&fake, 0, sizeof(fake));
			memset(&tx, 0, sizeof(tx));
			fake.fail_at = fail;
			assert(operations[operation](&io, &plan, &tx) == -EIO);
			assert(tx.first_error == -EIO);
			assert(fake.calls == fail);
			assert(operations[operation](&io, &plan, &tx) == -EBUSY);
			assert(fake.calls == fail);
		}
	}
	memset(&fake, 0, sizeof(fake));
	memset(&tx, 0, sizeof(tx));
	fake.owner_denied = 1;
	assert(mt6878_seninf_analog_on(&io, &plan, &tx) == -EACCES);
	assert(fake.writes == 0 && fake.calls == 1);
	memset(&fake, 0, sizeof(fake));
	memset(&tx, 0, sizeof(tx));
	assert(mt6878_seninf_analog_on(&io, &plan, &tx) == 0);
	total = fake.calls;
	plan.port = 0;
	assert(mt6878_seninf_receiver_off(&io, &plan, &tx) == -EINVAL);
	assert(fake.calls == total);
	plan.port = 1;
	fake.fail_at = fake.calls + 2;
	assert(mt6878_seninf_mux_setup(&io, &plan, &tx) == -EIO);
	fake.fail_at = 0;
	assert(mt6878_seninf_receiver_off(&io, &plan, &tx) == 0);
	assert(tx.first_error == -EIO);
	puts("SENINF real analog/mux backend: all callback failures and ownership gates PASS");
	return 0;
}
