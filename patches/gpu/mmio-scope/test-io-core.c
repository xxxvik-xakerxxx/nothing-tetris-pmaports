// SPDX-License-Identifier: GPL-2.0-only
/* ACTIVE software states below are mock fixtures, NEVER physical power proof. */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "mt6878-gpueb-io-core.c"

struct event { enum gpueb_io_region region; u32 offset, value; int write; };
struct mock {
	unsigned int calls, fail_at;
	u32 send, recv;
	struct event events[32];
};

static int read32(void *context, enum gpueb_io_region region, u32 offset, u32 *value)
{
	struct mock *mock = context;
	struct event *event = &mock->events[mock->calls++];
	assert(!gpueb_io_bounds(region, offset, 4));
	*event = (struct event){ region, offset, 0, 0 };
	if (mock->calls == mock->fail_at)
		return -EIO;
	*value = region == GPUEB_IO_SEND ? mock->send :
		 region == GPUEB_IO_RECV ? mock->recv : 0xa0000000U + offset;
	return 0;
}
static int write32(void *context, enum gpueb_io_region region, u32 offset, u32 value)
{
	struct mock *mock = context;
	struct event *event = &mock->events[mock->calls++];
	assert(!gpueb_io_bounds(region, offset, 4));
	*event = (struct event){ region, offset, value, 1 };
	return mock->calls == mock->fail_at ? -EIO : 0;
}
static const struct gpueb_io_ops ops = { read32, write32 };

int main(void)
{
	struct gpueb_io_core core = { 0 };
	struct mock mock = { 0 };
	u32 words[8] = { 0, 1, 2, 3, 4, 5, 6, 7 }, output[8], saved[8], gpr;
	unsigned int i, failure;

	assert(gpueb_io_tx(&core, &ops, &mock, words, 8) == -EHOSTDOWN);
	assert(!mock.calls);
	assert(!gpueb_io_get(&core));
	assert(gpueb_io_rx(&core, &ops, &mock, output, 8) == -EHOSTDOWN);
	assert(gpueb_io_can_destroy(&core) == -EBUSY);
	assert(!gpueb_io_put(&core));
	assert(!gpueb_io_quiesce(&core));
	assert(gpueb_io_get(&core) == -ESHUTDOWN);
	assert(!gpueb_io_can_destroy(&core));
	assert(gpueb_io_bounds(-1, 0, 4) == -EINVAL);
	assert(gpueb_io_bounds(GPUEB_IO_GPR, UINT32_MAX, 4) == -ERANGE);
	assert(gpueb_io_bounds(GPUEB_IO_DATA, 0, UINT32_MAX) == -ERANGE);
	assert(gpueb_io_bounds(GPUEB_IO_SET, 4, 4) == -ERANGE);
	assert(gpueb_io_bounds(GPUEB_IO_DATA, 1, 4) == -ERANGE);
	assert(!gpueb_io_bounds(GPUEB_IO_GPR, 0x60, 4));
	assert(!gpueb_io_bounds(GPUEB_IO_DATA, 0x27c, 4));
	core = (struct gpueb_io_core){ .phase = GPUEB_IO_TRANSACTION, .users = 1 };
	assert(gpueb_io_tx(&core, &ops, &mock, words, 7) == -EINVAL && !mock.calls);
	assert(!gpueb_io_tx(&core, &ops, &mock, words, 8));
	assert(mock.calls == 10);
	for (i = 0; i < 8; i++) {
		assert(mock.events[i + 1].region == GPUEB_IO_DATA);
		assert(mock.events[i + 1].offset == GPUEB_IO_TX + i * 4);
		assert(mock.events[i + 1].value == words[i]);
	}
	assert(mock.events[9].region == GPUEB_IO_SET && mock.events[9].value == 2);
	assert(!gpueb_io_quiesce(&core));
	assert(!gpueb_io_put(&core));
	assert(gpueb_io_can_destroy(&core) == -EBUSY); /* quiesce is NOT OFF */
	for (failure = 1; failure <= 10; failure++) {
		core = (struct gpueb_io_core){ .phase = GPUEB_IO_TRANSACTION, .users = 1 };
		mock = (struct mock){ .fail_at = failure };
		assert(gpueb_io_tx(&core, &ops, &mock, words, 8) == -EIO);
		assert(mock.calls == failure && core.phase == GPUEB_IO_QUARANTINED);
		assert(gpueb_io_tx(&core, &ops, &mock, words, 8) == -EIO);
		assert(mock.calls == failure); /* no retry or post-fault MMIO */
	}
	core = (struct gpueb_io_core){ .phase = GPUEB_IO_TRANSACTION, .users = 1 };
	mock = (struct mock){ .send = 2 };
	assert(gpueb_io_tx(&core, &ops, &mock, words, 8) == -EBUSY);
	assert(mock.calls == 1 && !mock.events[0].write);
	memset(saved, 0x55, sizeof(saved));
	for (failure = 1; failure <= 10; failure++) {
		core = (struct gpueb_io_core){ .phase = GPUEB_IO_TRANSACTION, .users = 1 };
		mock = (struct mock){ .recv = 2 | 0x80000000U, .fail_at = failure };
		memcpy(output, saved, sizeof(output));
		assert(gpueb_io_rx(&core, &ops, &mock, output, 8) == -EIO);
		assert(!memcmp(output, saved, sizeof(output)) && mock.calls == failure);
	}
	core = (struct gpueb_io_core){ .phase = GPUEB_IO_TRANSACTION, .users = 1 };
	mock = (struct mock){ .recv = 2 | 0x80000000U };
	assert(!gpueb_io_rx(&core, &ops, &mock, output, 8));
	assert(mock.events[9].region == GPUEB_IO_CLEAR && mock.events[9].value == 2);
	for (i = 0; i < 8; i++)
		assert(output[i] == 0xa0000000U + GPUEB_IO_RX + i * 4);
	core = (struct gpueb_io_core){ .phase = GPUEB_IO_TRANSACTION, .users = 1 };
	mock = (struct mock){ .recv = 1 };
	assert(gpueb_io_rx(&core, &ops, &mock, output, 8) == -EAGAIN && mock.calls == 1);
	assert(!gpueb_io_gpr_read(&core, &ops, &mock, 0x34, &gpr));
	assert(gpr == 0xa0000034U);
	assert(!gpueb_io_put(&core));
	assert(gpueb_io_gpr_read(&core, &ops, &mock, 0x34, &gpr) == -ENXIO);
	assert(gpueb_io_can_destroy(&core) == -EBUSY);
	core = (struct gpueb_io_core){ .users = UINT32_MAX };
	assert(gpueb_io_get(&core) == -EOVERFLOW);
	puts("Bounded MMIO transaction/lifetime fault tests PASS; no physical power/IRQ proof");
	return 0;
}
