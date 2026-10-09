/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef uint64_t phys_addr_t;
typedef int spinlock_t;
#define __iomem
#define GPUEB_WORDS 8
#define GPUEB_SHARED_SIZE 0x4000
#define RPROC_OFFLINE 0
#define READ_ONCE(value) (value)
struct rproc { int state; };
struct device { int unused; };
struct mbox_client { int unused; };
struct mbox_chan { int unused; };
struct completion { int unused; };
struct mutex { int unused; };
struct resource { uint64_t start, size; };
static unsigned int shutdowns, frees;
static int shutdown_error, shutdown_state;
static int rproc_shutdown(struct rproc *rproc)
{
	shutdowns++;
	rproc->state = shutdown_state;
	return shutdown_error;
}
static void mbox_free_channel(struct mbox_chan *channel) { (void)channel; frees++; }
static void iounmap(void *mapping) { (void)mapping; frees++; }
static void release_mem_region(uint64_t start, uint64_t size)
{
	(void)start; (void)size; frees++;
}
static uint64_t resource_size(struct resource *resource) { return resource->size; }
static void rproc_put(struct rproc *rproc) { (void)rproc; frees++; }
static void put_device(struct device *device) { (void)device; frees++; }
static void kfree(void *pointer) { (void)pointer; frees++; }
#include "gpueb-owner-release.h"

int main(void)
{
	unsigned int scenario;
	for (scenario = 0; scenario < 6; scenario++) {
		struct rproc rproc = { .state = RPROC_OFFLINE };
		struct resource gpr = { .start = 1, .size = 0x64 }, shared = {};
		struct mbox_chan channel = {};
		struct mt6878_gpueb_session session = {
			.rproc = &rproc, .gpr_claim = &gpr, .shared_claim = &shared,
			.gpr = &gpr, .shared = &shared, .chan = &channel,
		};
		bool expected;
		shutdowns = frees = 0;
		shutdown_error = shutdown_state = 0;
		session.boot_attempted = scenario != 0;
		session.boot_ref = scenario >= 3;
		if (scenario == 2)
			rproc.state = 2; /* Failed partial start left running. */
		if (scenario == 4)
			shutdown_error = -1;
		if (scenario == 5)
			shutdown_state = 2;
		expected = scenario == 0 || scenario == 3;
		assert(gpueb_release(&session) == expected);
		assert(frees == (expected ? 8U : 0U));
		assert(shutdowns == (scenario >= 3 ? 1U : 0U));
	}
	puts("PASS: partial boot OFFLINE/running retain every claim; shutdown failures retain too");
	return 0;
}
