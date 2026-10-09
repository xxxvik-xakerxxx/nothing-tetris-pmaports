/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stddef.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint64_t phys_addr_t;
#define __iomem
typedef int spinlock_t;
struct mutex { int unused; };
struct completion { bool done; };
struct rproc { int power; int state; };
struct device;
struct resource;
struct mbox_client { struct device *dev; };
struct mbox_chan { struct mbox_client *client; };
#define RPROC_RUNNING 2
#define RPROC_ATTACHED 5
#define READ_ONCE(value) (value)
#define atomic_read(value) (*(value))
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
static void (*spin_hook)(void);
#define spin_lock_irqsave(lock, flags) do { \
	(void)(lock); (flags) = 0; \
	if (spin_hook) { void (*hook)(void) = spin_hook; spin_hook = NULL; hook(); } \
} while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(lock); (void)(flags); } while (0)
static unsigned long jiffies;
static unsigned long msecs_to_jiffies(unsigned int milliseconds) { return milliseconds; }
static void reinit_completion(struct completion *completion) { completion->done = false; }
static void complete(struct completion *completion) { completion->done = true; }
static int sends, waits, send_error;
static bool deliver;
static unsigned long send_ticks;
static int mbox_send_message(struct mbox_chan *chan, void *words);
static unsigned long wait_for_completion_timeout(struct completion *completion, unsigned long timeout)
{
	waits++;
	assert(timeout > 0 && timeout <= 10000);
	return completion->done;
}
#define PAGE_SIZE 4096U
#define IS_ALIGNED(value, align) (!((value) & ((align) - 1)))
#define lower_32_bits(value) ((u32)(value))
#define upper_32_bits(value) ((u32)((u64)(value) >> 32))
#include "gpueb-session-helpers.h"

static struct mt6878_gpueb_session *injected_session;
static void unsolicited_before_arm(void)
{
	u32 response[8] = {};
	gpueb_rx(&injected_session->client, response);
}

static int mbox_send_message(struct mbox_chan *chan, void *words)
{
	u32 reply[8] = {};
	(void)words;
	sends++;
	jiffies += send_ticks;
	if (deliver)
		gpueb_rx(chan->client, reply);
	return send_error ? send_error : 3; /* Token is not firmware completion. */
}

int main(void)
{
	u32 words[8], original[8];
	unsigned int i;

	assert(gpueb_shared_range_valid(0x40000000ULL, 0x4000));
	assert(gpueb_shared_range_valid(0x800000000ULL - 0x4000, 0x4000));
	assert(!gpueb_shared_range_valid(0x800000000ULL - 0x3000, 0x4000));
	assert(!gpueb_shared_range_valid(0x40000000ULL, UINT64_MAX));
	assert(!gpueb_shared_range_valid(UINT64_MAX, 0x4000));
	assert(!gpueb_shared_range_valid(0x40000000ULL, 0x3fff));
	assert(!gpueb_shared_range_valid(0x3ffff000ULL, 0x4000));
	assert(!gpueb_shared_range_valid(0x40000001ULL, 0x4000));
	memset(words, 0x5a, sizeof(words));
	memcpy(original, words, sizeof(words));
	assert(gpueb_init_message(NULL, 7, 0x40000000ULL) == -EINVAL);
	assert(gpueb_init_message(words, 0, 0x40000000ULL) == -EINVAL);
	assert(memcmp(words, original, sizeof(words)) == 0);
	assert(gpueb_init_message(words, 7, UINT64_MAX) == -EINVAL);
	assert(memcmp(words, original, sizeof(words)) == 0);
	assert(gpueb_init_message(words, 7, 0x123456000ULL) == 0);
	assert(words[0] == 7 && words[4] == 0x23456000 && words[5] == 1);
	assert(words[6] == 0x4000);
	for (i = 0; i < 8; i++)
		if (i != 0 && i != 4 && i != 5 && i != 6)
			assert(words[i] == 0);
	puts("PASS: reserved physical range bounds and actual INIT_SHARED_MEM encoding");
	for (i = 0; i < 6; i++) {
		struct rproc rproc = { .power = 1, .state = RPROC_RUNNING };
		struct mt6878_gpueb_session session = { .rproc = &rproc };
		struct mbox_chan channel = { .client = &session.client };
		u32 reply[8], sentinel[8];
		int result, expected = 0;
		session.chan = &channel;
		sends = waits = send_error = 0;
		jiffies = send_ticks = 0;
		deliver = true;
		memset(reply, 0x5a, sizeof(reply));
		memcpy(sentinel, reply, sizeof(reply));
		switch (i) {
		case 0: break;
		case 1: send_error = -EIO; deliver = false; expected = -EIO; break;
		case 2: deliver = false; expected = -ETIMEDOUT; break;
		case 3: send_ticks = 10000; expected = -ETIMEDOUT; break;
		case 4: rproc.state = 0; expected = -ENOTCONN; break;
		default: rproc.power = 2; expected = -EBUSY; break;
		}
		result = gpueb_exchange(&session, words, reply);
		assert(result == expected && !session.waiting);
		if (expected) {
			int before = sends;
			assert(memcmp(reply, sentinel, sizeof(reply)) == 0);
			assert(session.error == expected);
			gpueb_rx(&session.client, words); /* Late response cannot clear poison. */
			assert(gpueb_exchange(&session, words, reply) == expected);
			assert(gpueb_fail(&session, -ERANGE) == expected);
			assert(sends == before);
		} else {
			assert(sends == 1 && waits == 1);
			gpueb_rx(&session.client, words); /* Unsolicited response. */
			assert(gpueb_exchange(&session, words, reply) == -EPROTO);
			assert(sends == 1);
		}
	}
	puts("PASS: actual session exchange completion, timeouts, correlation and no retry");
	{
		struct rproc rproc = { .power = 1, .state = RPROC_RUNNING };
		struct mt6878_gpueb_session session = { .rproc = &rproc };
		struct mbox_chan channel = { .client = &session.client };
		u32 reply[8];
		session.chan = &channel;
		sends = waits = 0;
		injected_session = &session;
		spin_hook = unsolicited_before_arm;
		assert(gpueb_exchange(&session, words, reply) == -EPROTO);
		assert(sends == 0 && waits == 0 && !session.waiting);
		assert(!session.response.done);
		gpueb_rx(&session.client, NULL);
		assert(session.error == -EPROTO);
		assert(gpueb_exchange(&session, words, reply) == -EPROTO);
		assert(sends == 0);
	}
	puts("PASS: unsolicited IRQ between initial check and RX lock prevents send");
	return 0;
}
