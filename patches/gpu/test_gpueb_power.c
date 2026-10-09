/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
typedef uint32_t u32;
typedef uint64_t u64;
#include "gpueb-core.h"
#include "vendor-abi.h"

_Static_assert(sizeof(struct gpufreq_ipi_data) == 32, "vendor message size");
_Static_assert(offsetof(struct gpufreq_ipi_data, u) == 16, "vendor union offset");
_Static_assert(CMD_POWER_CONTROL == MT6878_GPUEB_POWER_CMD, "vendor command");
_Static_assert(GPU_PWR_OFF == 0 && GPU_PWR_ON == 1, "vendor power states");

struct fixture {
	struct mt6878_gpueb_observation o;
	int reads, writes, fail_read, transfer_error, firmware_error;
	bool wrong_count, wrong_post_count, reset_after;
	u32 words[8];
};

static int snapshot(void *ctx, struct mt6878_gpueb_observation *o)
{
	struct fixture *f = ctx;

	if (++f->reads == f->fail_read)
		return -EIO;
	*o = f->o;
	return 0;
}

static int transfer(void *ctx, const u32 *words, unsigned int count,
		    unsigned int timeout, int *power_count)
{
	struct fixture *f = ctx;

	f->writes++;
	assert(count == 8 && timeout == 10000);
	memcpy(f->words, words, sizeof(f->words));
	if (f->transfer_error)
		return f->transfer_error;
	if (f->firmware_error) {
		*power_count = f->firmware_error;
		return 0;
	}
	*power_count = f->wrong_count ? 2 : (int)words[4];
	f->o.power_count = f->wrong_post_count ? 2 : *power_count;
	if (f->reset_after)
		f->o.epoch++;
	return 0;
}

static const struct mt6878_gpueb_power_ops ops = { snapshot, transfer };

static struct fixture fresh(void)
{
	struct fixture f = { .o = { .epoch = 7, .magic = 0xabc,
		.proven = MT6878_GPUEB_REQUIRED } };
	return f;
}

static void poisoned(struct mt6878_gpueb_power_state *s, struct fixture *f, int err)
{
	int reads = f->reads, writes = f->writes;
	assert(s->first_error == err);
	assert(mt6878_gpueb_power_step(s, &ops, f, true) == err);
	assert(mt6878_gpueb_power_step(s, &ops, f, false) == err);
	assert(mt6878_gpueb_power_arm(s, &ops, f) == err);
	assert(f->reads == reads && f->writes == writes);
}

int main(void)
{
	struct mt6878_gpueb_power_state s = {};
	struct fixture f = fresh();
	unsigned int i;

	assert(mt6878_gpueb_observation_valid(NULL) == -EINVAL);
	assert(mt6878_gpueb_power_arm(NULL, &ops, &f) == -EINVAL);
	assert(mt6878_gpueb_power_step(NULL, &ops, &f, true) == -EINVAL);
	assert(mt6878_gpueb_power_poison(NULL, -EIO) == -EINVAL);
	assert(!f.reads && !f.writes);
	assert(mt6878_gpueb_power_step(&s, &ops, &f, true) == -ENOTCONN);
	assert(f.reads == 0 && f.writes == 0);
	assert(mt6878_gpueb_power_arm(&s, &ops, &f) == 0);
	assert(f.writes == 0);
	assert(mt6878_gpueb_power_arm(&s, &ops, &f) == -EALREADY);
	assert(mt6878_gpueb_power_step(&s, &ops, &f, false) == 0);
	assert(f.writes == 0);
	assert(mt6878_gpueb_power_step(&s, &ops, &f, true) == 0);
	assert(s.on && f.writes == 1);
	assert(f.words[0] == 0xabc && f.words[1] == 6 && f.words[4] == 1);
	{
		struct gpufreq_ipi_data message;
		memcpy(&message, f.words, sizeof(message));
		assert(message.magic == 0xabc && message.cmd_id == CMD_POWER_CONTROL);
		assert(message.target == 0 && message.u.power_state == GPU_PWR_ON);
	}
	for (i = 0; i < 8; i++)
		if (i != 0 && i != 1 && i != 4)
			assert(f.words[i] == 0);
	assert(mt6878_gpueb_power_step(&s, &ops, &f, true) == 0);
	assert(f.writes == 1);
	assert(mt6878_gpueb_power_step(&s, &ops, &f, false) == 0);
	assert(!s.on && f.writes == 2 && f.words[4] == 0);

	for (i = 0; i < 7; i++) {
		s = (struct mt6878_gpueb_power_state) {};
		f = fresh();
		f.o.proven &= ~(1U << i);
		assert(mt6878_gpueb_power_arm(&s, &ops, &f) == -EACCES);
		assert(!s.armed && !f.writes);
		f = fresh();
		assert(mt6878_gpueb_power_arm(&s, &ops, &f) == 0);
		f.o.proven &= ~(1U << i);
		assert(mt6878_gpueb_power_step(&s, &ops, &f, true) == -EACCES);
		assert(!f.writes);
		poisoned(&s, &f, -EACCES);
	}

	for (i = 0; i < 11; i++) {
		int err;
		s = (struct mt6878_gpueb_power_state) {};
		f = fresh();
		assert(mt6878_gpueb_power_arm(&s, &ops, &f) == 0);
		switch (i) {
		case 0: f.fail_read = 2; err = -EIO; break;
		case 1: f.o.epoch++; err = -ESTALE; break;
		case 2: f.o.magic++; err = -ESTALE; break;
		case 3: f.o.power_count = 1; err = -EBUSY; break;
		case 4: f.transfer_error = -ETIMEDOUT; err = -ETIMEDOUT; break;
		case 5: f.firmware_error = -ERANGE; err = -ERANGE; break;
		case 6: f.wrong_count = true; err = -EPROTO; break;
		case 7: f.fail_read = 3; err = -EIO; break;
		case 8: f.reset_after = true; err = -ESTALE; break;
		case 9: f.wrong_post_count = true; err = -EPROTO; break;
		default: f.transfer_error = 1; err = -EPROTO; break;
		}
		assert(mt6878_gpueb_power_step(&s, &ops, &f, true) == err);
		assert(!s.on && f.writes == (i >= 4));
		poisoned(&s, &f, err);
	}

	for (i = 0; i < 5; i++) {
		int err;
		s = (struct mt6878_gpueb_power_state) {};
		f = fresh();
		switch (i) {
		case 0: f.o.epoch = 0; err = -ENOTCONN; break;
		case 1: f.o.magic = 0; err = -ENOTCONN; break;
		case 2: f.o.power_count = 1; err = -EBUSY; break;
		case 3: f.o.power_count = -1; err = -EPROTO; break;
		default: f.fail_read = 1; err = -EIO; break;
		}
		assert(mt6878_gpueb_power_arm(&s, &ops, &f) == err);
		assert(!s.armed && !f.writes);
	}

	/* Failed OFF is uncertain too; never blindly undo or drop dependencies. */
	s = (struct mt6878_gpueb_power_state) {};
	f = fresh();
	assert(mt6878_gpueb_power_arm(&s, &ops, &f) == 0);
	assert(mt6878_gpueb_power_step(&s, &ops, &f, true) == 0);
	f.transfer_error = -ETIMEDOUT;
	assert(mt6878_gpueb_power_step(&s, &ops, &f, false) == -ETIMEDOUT);
	assert(s.on && f.writes == 2);
	poisoned(&s, &f, -ETIMEDOUT);

	s = (struct mt6878_gpueb_power_state) {};
	f = fresh();
	assert(mt6878_gpueb_power_arm(&s, NULL, &f) == -EINVAL);
	assert(!f.reads && !f.writes);
	assert(mt6878_gpueb_power_arm(&s, &ops, &f) == 0);
	assert(mt6878_gpueb_power_step(&s, NULL, &f, true) == -EINVAL);
	poisoned(&s, &f, -EINVAL);
	puts("PASS: GPUEB ABI, ownership gates, exclusive counts, first-failure/no-retry");
	return 0;
}
