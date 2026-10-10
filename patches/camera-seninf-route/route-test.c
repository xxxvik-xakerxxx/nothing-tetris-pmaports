// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <string.h>
#include "mt6878-seninf-route-program.h"

/* In-memory fault fixture only. Never a production ownership provider. */
struct fixture {
	unsigned int base[0x18000 / 4], analog[0x30000 / 4];
	unsigned int cammux[2][16][0x40 / 4];
	unsigned int writes, fail_write, reject_mux, acks;
};

static int check(void *context, enum mt6878_seninf_action action,
	const struct mt6878_seninf_plan *p)
{
	struct fixture *f = context;

	assert(action == MT6878_MUX_SETUP);
	return p->mux == f->reject_mux ? -EPERM : 0;
}

static int read_reg(void *context, enum mt6878_seninf_region r,
	unsigned int offset, unsigned int *v)
{
	struct fixture *f = context;

	if (r == MT6878_SENINF_BASE && offset >= 0x17000 && offset < 0x17400) {
		*v = f->cammux[!!(f->base[0x17f04 / 4] & 0x80)]
			[(offset - 0x17000) / 0x40][(offset % 0x40) / 4];
		return 0;
	}
	*v = r == MT6878_SENINF_BASE ? f->base[offset / 4] : f->analog[offset / 4];
	return 0;
}

static int write_reg(void *context, enum mt6878_seninf_region r,
	unsigned int offset, unsigned int v)
{
	struct fixture *f = context;

	if (++f->writes == f->fail_write)
		return -EIO;
	if (r == MT6878_SENINF_BASE && offset >= 0x17000 && offset < 0x17400 &&
	    offset % 0x40 == 0xc) {
		assert(v == 0x103);
		f->acks++;
	}
	if (r == MT6878_SENINF_BASE && offset >= 0x17000 && offset < 0x17400)
		f->cammux[!!(f->base[0x17f04 / 4] & 0x80)]
			[(offset - 0x17000) / 0x40][(offset % 0x40) / 4] = v;
	else if (r == MT6878_SENINF_BASE)
		f->base[offset / 4] = v;
	else
		f->analog[offset / 4] = v;
	return 0;
}

static int delay(void *context, unsigned int us)
{
	(void)context;
	(void)us;
	assert(0); /* VC/CAMMUX/mux setup has no invented delay or ready poll. */
	return -EINVAL;
}

static struct fixture f;

static void reset(void)
{
	memset(&f, 0, sizeof(f));
	f.reject_mux = 99;
}

int main(void)
{
	struct mt6878_seninf_backend io = {
		.check = check, .read = read_reg, .write = write_reg, .delay_us = delay,
		.context = &f, .base_size = 0x18000, .analog_size = 0x30000,
	};
	struct mt6878_route_plan p = {
		.outputs = { { 0, 0, 0, 1, 2 }, { 0, 0, 1, 2, 2 } },
		.cammux = { 0, 1 }, .tags = { 0, 1 }, .width = 4000, .height = 3000,
	};
	struct mt6878_route_transaction tx;
	unsigned int mode, port, count, stop_count, n, mac, writes;

	for (mode = 0; mode < 2; mode++) {
		p.width = mode ? 4096 : 4000;
		p.height = mode ? 2304 : 3000;
		for (port = 0; port < 2; port++) {
			p.outputs[0].port = p.outputs[1].port = port;
			reset();
			tx = (struct mt6878_route_transaction) { 0 };
			assert(!mt6878_route_setup(&io, &p, &tx));
			count = f.writes;
			mac = 0x5000 + port * 0x8000;
			assert(f.analog[(mac + 0x110) / 4] == 0x1130);
			assert(f.analog[(mac + 0x104) / 4] == 0x2e2d2c2b);
			assert(f.base[(0xa00 + 0x20) / 4] == 0x2b0011);
			assert(f.base[(0xa00 + 0x24) / 4] == 0x300011);
			assert(f.cammux[0][0][0x14 / 4] == (p.height << 16 | p.width));
			assert(f.cammux[0][1][0x14 / 4] == (p.height / 4 << 16 | p.width));
			assert(f.cammux[1][1][0] == f.cammux[0][1][0]);
			assert((f.cammux[0][1][0] & 0x7f007f) == 0x80008);
			assert(f.acks == 4 && tx.configured);
			assert(!mt6878_route_disconnect(&io, &tx));
			stop_count = f.writes - count;
			assert(tx.disconnected && !tx.configured && f.acks == 8);
			assert((f.cammux[0][0][0] & 0x7f007f) == 0x7f007f);
			assert((f.cammux[1][0][0] & 0x7f007f) == 0x7f007f);
			assert(!(f.cammux[0][0][0] & 0x80));
			assert(mt6878_route_setup(&io, &p, &tx) == -EBUSY);
			for (n = 1; n <= count; n++) {
				reset();
				f.fail_write = n;
				tx = (struct mt6878_route_transaction) { 0 };
				assert(mt6878_route_setup(&io, &p, &tx) == -EIO);
				assert(tx.bus.first_error == -EIO && !tx.configured);
				f.fail_write = 0;
				assert(!mt6878_route_disconnect(&io, &tx));
				assert(tx.bus.first_error == -EIO && tx.disconnected);
			}
			for (n = 1; n <= stop_count; n++) {
				reset();
				tx = (struct mt6878_route_transaction) { 0 };
				assert(!mt6878_route_setup(&io, &p, &tx));
				f.fail_write = f.writes + n;
				assert(mt6878_route_disconnect(&io, &tx) == -EIO);
				assert(!tx.disconnected && tx.bus.first_error == -EIO);
				writes = f.writes;
				assert(mt6878_route_disconnect(&io, &tx) == -EIO);
				assert(f.writes == writes); /* No failed-stop replay. */
			}
		}
	}
	reset();
	tx = (struct mt6878_route_transaction) { 0 };
	f.reject_mux = p.outputs[1].mux;
	assert(mt6878_route_setup(&io, &p, &tx) == -EPERM && !f.writes);
	reset();
	f.base[0x17f08 / 4] = 0x300;
	assert(mt6878_route_setup(&io, &p, &tx) == -EBUSY && !f.writes);
	reset();
	f.cammux[0][0][0] = 1U << 23;
	assert(mt6878_route_setup(&io, &p, &tx) == -EBUSY && !f.writes);
	p.outputs[1].mux = p.outputs[0].mux;
	assert(mt6878_route_setup(&io, &p, &tx) == -EINVAL && !f.writes);
	return 0;
}
