// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <string.h>
#include "mt6878-seninf-events.h"

struct fixture {
	unsigned int base[0x18000 / 4], analog[0x30000 / 4];
	unsigned int writes, fail, forbidden_ack, discard;
};

static struct fixture f;

static int read_reg(void *context, enum mt6878_seninf_region r,
	unsigned int offset, unsigned int *value)
{
	struct fixture *s = context;

	*value = r == MT6878_SENINF_BASE ? s->base[offset / 4] : s->analog[offset / 4];
	return 0;
}

static int write_reg(void *context, enum mt6878_seninf_region r,
	unsigned int offset, unsigned int value)
{
	struct fixture *s = context;

	if (++s->writes == s->fail)
		return -EIO;
	if (s->discard)
		return 0; /* Successful bus write with unchanged enable: readback fails. */
	if (r == MT6878_SENINF_ANALOG && (offset & 0xfff) == 0xbc)
		s->forbidden_ack++;
	if (r == MT6878_SENINF_BASE)
		s->base[offset / 4] = value;
	else
		s->analog[offset / 4] = value;
	return 0;
}

static int check(void *context, enum mt6878_seninf_action action,
	const struct mt6878_seninf_plan *p)
{
	(void)context;
	(void)action;
	(void)p;
	return -EPERM; /* Fixture never purports to authorize live hardware. */
}

static int delay(void *context, unsigned int us)
{
	(void)context;
	(void)us;
	assert(0);
	return -EINVAL;
}

int main(void)
{
	struct mt6878_seninf_backend io = {
		.check = check, .read = read_reg, .write = write_reg, .delay_us = delay,
		.context = &f, .base_size = 0x18000, .analog_size = 0x30000,
	};
	struct mt6878_route_plan p = {
		.outputs = { { 0, 0, 0, 1, 2 }, { 0, 0, 1, 0, 2 } },
		.cammux = { 0, 1 }, .tags = { 0, 1 }, .width = 4000, .height = 3000,
	};
	struct mt6878_seninf_transaction tx;
	struct mt6878_seninf_events sample;
	unsigned int port, count, n, i, mac;

	memset(&f, 0, sizeof(f));
	assert(!mt6878_seninf_events_preflight(&io, &p));
	f.base[0x17f08 / 4] = 1;
	assert(mt6878_seninf_events_preflight(&io, &p) == -EBUSY);
	assert(!f.writes);
	f.base[0x17f08 / 4] = 0;
	f.base[0x17fc0 / 4] = 1;
	assert(mt6878_seninf_events_preflight(&io, &p) == -EBUSY);
	assert(!f.writes);
	f.base[0x17fc0 / 4] = 0;
	f.base[0x17fc4 / 4] = 1;
	assert(mt6878_seninf_events_preflight(&io, &p) == -EBUSY);
	assert(!f.writes);
	memset(&f, 0, sizeof(f));
	f.discard = 1;
	f.base[0x16000 / 4] = 0x3f;
	tx = (struct mt6878_seninf_transaction) { 0 };
	assert(mt6878_seninf_tsrec_disable(&io, &tx) == -EIO);
	assert(tx.first_error == -EIO);
	memset(&f, 0xff, sizeof(f));
	f.writes = f.fail = f.forbidden_ack = f.discard = 0;
	tx = (struct mt6878_seninf_transaction) { 0 };
	assert(!mt6878_seninf_tsrec_disable(&io, &tx));
	count = f.writes;
	assert((f.base[0x16000 / 4] & 0x3f) == 0);
	assert((f.base[0x16000 / 4] & 0x003f0000) == 0x003f0000);
	assert(!(f.base[0x16010 / 4] & 0x8fff0fff));
	assert(!(f.base[0x1601c / 4] & 0x003f003f));
	for (n = 1; n <= count; n++) {
		memset(&f, 0, sizeof(f));
		f.fail = n;
		tx = (struct mt6878_seninf_transaction) { 0 };
		assert(mt6878_seninf_tsrec_disable(&io, &tx) == -EIO);
		assert(tx.first_error == -EIO && f.writes == n);
	}
	for (port = 0; port < 2; port++) {
		memset(&f, 0, sizeof(f));
		tx = (struct mt6878_seninf_transaction) { 0 };
		p.outputs[0].port = p.outputs[1].port = port;
		p.width = port ? 4096 : 4000;
		p.height = port ? 2304 : 3000;
		f.analog[(0x30f4 + port * 0x8000) / 4] = 0x10000;
		f.base[0xac8 / 4] = 1U << 28;
		for (i = 0; i < 2; i++) {
			mac = 0x5000 + port * 0x8000 + i * 0x1000;
			f.analog[(mac + 0xc0) / 4] = 0xffffffffU;
			f.analog[(mac + 0xb8) / 4] = 0xffffffffU;
			f.analog[(mac + 0xc8) / 4] = 0x40;
			f.analog[(mac + 0xbc) / 4] = 0xf;
			f.base[(0xd10 + i * 0x1000) / 4] = 0x8000000fU;
			f.base[(0xd18 + i * 0x1000) / 4] = 3;
		}
		assert(!mt6878_seninf_sample_events(&io, &p, &sample));
		assert(sample.mac[0] == 0x40 && sample.mac[1] == 0x40);
		assert(sample.g1[0] == 0xf && sample.g1[1] == 0xf);
		assert(!mt6878_seninf_mask_events(&io, &p, &tx));
		assert(!mt6878_seninf_ack_events(&io, &p, &tx, &sample));
		assert(!f.forbidden_ack);
		assert(f.base[0xac8 / 4] == 0xffffffffU);
		assert(f.analog[(0x30f4 + port * 0x8000) / 4] == 0xff0000);
		for (i = 0; i < 2; i++) {
			mac = 0x5000 + port * 0x8000 + i * 0x1000;
			assert(f.analog[(mac + 0xc0) / 4] == 0x80008000U);
			assert(f.analog[(mac + 0xb8) / 4] == 0xffffff00U);
			assert(f.analog[(mac + 0xc8) / 4] == 0xffffffffU);
			assert(f.base[(0xd10 + i * 0x1000) / 4] == 0x80000000U);
			assert(f.base[(0xd18 + i * 0x1000) / 4] == 0x103);
		}
		/* Six proven ACK writes, stop immediately at each injected failure. */
		for (n = 1; n <= 6; n++) {
			f.writes = 0;
			f.fail = n;
			tx = (struct mt6878_seninf_transaction) { 0 };
			assert(mt6878_seninf_ack_events(&io, &p, &tx, &sample) == -EIO);
			assert(tx.first_error == -EIO && f.writes == n);
			assert(!f.forbidden_ack);
		}
	}
	return 0;
}
