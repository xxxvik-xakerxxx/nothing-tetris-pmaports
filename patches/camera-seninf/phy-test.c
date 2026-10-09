/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "mt6878-seninf-phy.h"

struct fake {
	unsigned int base[0x18000 / 4], analog[0x30000 / 4];
	unsigned int calls, fail_at, reads, writes, owners, delays[16], delay_count;
	unsigned int unsupported;
	int deny;
};
static struct fake fake;

static int tick(struct fake *f)
{
	return ++f->calls == f->fail_at ? -EIO : 0;
}

static int check(void *context, enum mt6878_seninf_action action,
	const struct mt6878_seninf_plan *plan)
{
	(void)plan;
	assert(action == MT6878_RECEIVER_OFF);
	return tick(context);
}

static int verify(void *context, enum mt6878_phy_owner owner,
	const struct mt6878_seninf_plan *plan, const struct mt6878_phy_inputs *inputs)
{
	struct fake *f = context;
	int ret = tick(f);

	(void)plan;
	(void)inputs;
	if (owner != MT6878_PHY_QUIESCED) {
		assert(!f->writes);
		assert((unsigned int)owner == f->owners);
		f->owners++;
	}
	return ret ? ret : (f->unsupported & (1U << owner)) ? -EOPNOTSUPP :
		(int)owner == f->deny ? -EACCES : 0;
}

static int read_reg(void *context, enum mt6878_seninf_region region,
	unsigned int offset, unsigned int *value)
{
	struct fake *f = context;
	int ret = tick(f);

	assert(!(offset & 3));
	assert(offset < (region == MT6878_SENINF_BASE ? 0x18000 : 0x30000));
	f->reads++;
	if (!ret)
		*value = (region == MT6878_SENINF_BASE ? f->base : f->analog)[offset / 4];
	return ret;
}

static int write_reg(void *context, enum mt6878_seninf_region region,
	unsigned int offset, unsigned int value)
{
	struct fake *f = context;
	int ret = tick(f);

	assert(f->owners == 4);
	assert(!(offset & 3));
	assert(offset < (region == MT6878_SENINF_BASE ? 0x18000 : 0x30000));
	if (!ret) {
		(region == MT6878_SENINF_BASE ? f->base : f->analog)[offset / 4] = value;
		f->writes++;
	}
	return ret;
}

static int delay(void *context, unsigned int us)
{
	struct fake *f = context;
	int ret = tick(f);

	assert(f->delay_count < 16);
	if (!ret)
		f->delays[f->delay_count++] = us;
	return ret;
}

static void reset(struct mt6878_phy_transaction *tx)
{
	memset(&fake, 0, sizeof(fake));
	fake.deny = -1;
	memset(tx, 0, sizeof(*tx));
}

int main(void)
{
	struct mt6878_phy_backend backend = {
		{ check, read_reg, write_reg, delay, &fake, 0x18000, 0x30000 }, verify
	};
	struct mt6878_seninf_plan plan = { 0, 4, 6, 0, 3 };
	/* Synthetic test pattern, not handset calibration. */
	struct mt6878_phy_inputs in = {
		.rg_csi = 0xa5a5a5a4, .csi_clock_hz = 312000000,
		.rg_csi_verified = 1,
		.mipi_pixel_rate = 700800000, .dphy_trail_ns = 0x47, .lanes = { 0, 1, 2 }
	};
	struct mt6878_phy_transaction tx;
	unsigned int port, mode, i, total = 0, calls_before, off_calls;
	unsigned int clocks[] = { 312000000, 343000000, 416000000, 499000000 };
	unsigned int settles[] = { 16, 19, 24, 29 };

	for (i = 0; i < 4; i++)
		assert(mt6878_phy_settle(clocks[i]) == settles[i]);
	for (port = 0; port < 2; port++) {
		plan.port = port;
		in.rg_csi_port = port;
		for (mode = 0; mode < 2; mode++) {
			in.mode = mode;
			in.dphy_trail_ns = mode ? 0x31 : 0x47;
			for (i = 0; i < 4; i++) {
				unsigned int bank = port * 0x8000;
				unsigned int n;

				in.csi_clock_hz = clocks[i];
				reset(&tx);
				assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == 0);
				assert(tx.configured && fake.owners == 4);
				assert(fake.delay_count == 8);
				assert(fake.delays[0] == 200 && fake.delays[1] == 30);
				assert(fake.delays[2] == 1 && fake.delays[3] == 1);
				assert(fake.delays[4] == 200 && fake.delays[5] == 30);
				assert((fake.analog[(bank + 0x5000) / 4] & 15) == 7);
				assert(fake.analog[(bank + 0x50c0) / 4] == 0x80000000U);
				assert(fake.analog[(bank + 0x3000) / 4] == 7);
				assert(fake.base[MT6878_PHY_TOP_CTRL2 / 4] == (1U << port));
				for (n = 0; n < 12; n++) {
					const struct mt6878_phy_op *op = &mt6878_phy_efuse[n];
					assert(((fake.analog[(bank + op->offset) / 4] &
						op->mask) >> op->shift) == ((in.rg_csi >> op->value) & 31));
				}
				total = fake.calls;
				assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EALREADY);
				assert(fake.calls == total);
				assert(mt6878_phy_off(&backend, &tx) == 0);
				assert(!tx.configured);
				assert((fake.analog[bank / 4] & 3) == 0);
				assert((fake.analog[(bank + 0x1000) / 4] & 3) == 0);
				assert(mt6878_phy_off(&backend, &tx) == -EALREADY);
			}
		}
	}
	/* Every setup callback fails once; the transaction must stop immediately. */
	for (i = 1; i <= total; i++) {
		reset(&tx);
		fake.fail_at = i;
		assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EIO);
		assert(fake.calls == i && tx.bus.first_error == -EIO && !tx.configured);
		assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EIO);
		assert(fake.calls == i);
		/* A second owner error must not replace the first error. */
		fake.fail_at = 0;
		fake.deny = MT6878_PHY_QUIESCED;
		assert(mt6878_phy_off(&backend, &tx) == -EIO);
		assert(tx.bus.first_error == -EIO);
	}
	for (i = 0; i < 4; i++) {
		reset(&tx);
		fake.deny = (int)i;
		assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EACCES);
		assert(!fake.reads && !fake.writes && fake.calls == i + 1);
		reset(&tx);
		fake.unsupported = 1U << i;
		assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EOPNOTSUPP);
		assert(!fake.reads && !fake.writes && fake.calls == i + 1);
	}
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == 0);
	calls_before = fake.calls;
	assert(mt6878_phy_off(&backend, &tx) == 0);
	off_calls = fake.calls - calls_before;
	for (i = 1; i <= off_calls; i++) {
		reset(&tx);
		assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == 0);
		calls_before = fake.calls;
		fake.fail_at = calls_before + i;
		assert(mt6878_phy_off(&backend, &tx) == -EIO);
		assert(fake.calls == calls_before + i && tx.bus.first_error == -EIO);
	}
	reset(&tx);
	in.rg_csi = 0;
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == 0);
	for (i = 0; i < 12; i++) {
		const struct mt6878_phy_op *op = &mt6878_phy_efuse[i];

		assert(!(fake.analog[(plan.port * 0x8000 + op->offset) / 4] & op->mask));
	}
	assert(mt6878_phy_off(&backend, &tx) == 0);
	reset(&tx);
	in.rg_csi_verified = 0;
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls);
	in.rg_csi = 1;
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls); /* Nonzero unverified metadata is still rejected. */
	in.rg_csi_verified = 1;
	in.rg_csi_port = 0;
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls);
	in.rg_csi_port = plan.port;
	in.lanes[2] = 1;
	assert(mt6878_phy_validate(&backend, &plan, &in) == -EINVAL);
	in.lanes[2] = 2;
	in.csi_clock_hz = 313000000;
	assert(mt6878_phy_validate(&backend, &plan, &in) == -EINVAL);
	in.csi_clock_hz = 312000000;
	in.cphy_settle_ns = 70;
	assert(mt6878_phy_validate(&backend, &plan, &in) == -EINVAL);
	in.cphy_settle_ns = 0;
	in.not_fixed_trail_settle = 1;
	assert(mt6878_phy_validate(&backend, &plan, &in) == -EINVAL);
	in.not_fixed_trail_settle = 0;
	in.lrte = 1;
	assert(mt6878_phy_validate(&backend, &plan, &in) == -EINVAL);
	in.lrte = 0;
	plan.port = 2;
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls);
	plan.port = in.rg_csi_port;
	plan.intf = 12;
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls);
	plan.intf = 4;
	plan.mux = 13;
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls);
	plan.mux = 6;
	plan.group = 4;
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls);
	plan.group = 0;
	plan.pixel_mode = 8;
	reset(&tx);
	assert(mt6878_phy_setup(&backend, &tx, &plan, &in) == -EINVAL);
	assert(!fake.calls);
	puts("PASS: both ports/modes/clocks, per-half efuse, timing, ownership, all setup/off faults");
	return 0;
}
