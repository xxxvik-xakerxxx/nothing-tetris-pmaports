/* SPDX-License-Identifier: GPL-2.0+ */
/* Exact extracted production caller; boundary doubles are NOT authentication. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "tetris_modem_bundle.h"
#include "tetris_modem_emi_rows.h"
#include "tetris_scp_security.h"

#define ARCH_DMA_MINALIGN 64
struct blk_desc { int unused; };
struct tetris_modem_storage { int unused; };
struct staging_allocation { int unused; };
_Alignas(64) static unsigned char snapshot[2048];
_Alignas(64) static unsigned char destination[2048];
static int fault, release_fault, released, prepared_count, produced_count, synced;
static uintptr_t map_to_sysmem(const void *p) { return (uintptr_t)p; }
static int separate(const void *a, size_t an, const void *b, size_t bn)
{
	uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
	return x <= y ? an <= y - x : bn <= x - y;
}
static int slot_storage(struct blk_desc *d, char s, struct tetris_modem_storage *out)
{
	(void)d; (void)s; (void)out;
	return fault == 1 ? -ENODEV : 0;
}
static int snapshot_size(const struct tetris_modem_storage *s, size_t *bytes)
{
	(void)s;
	*bytes = sizeof(snapshot);
	return fault == 2 ? -ERANGE : 0;
}
static int acquire_staging(struct staging_allocation *a, size_t n, void **out)
{
	(void)a; (void)n;
	*out = snapshot;
	return fault == 3 ? -ENOMEM : 0;
}
static int read_snapshot(const struct tetris_modem_storage *s, void *p,
		size_t n, size_t *used)
{
	(void)s; (void)p;
	*used = n;
	return fault == 4 ? -EIO : 0;
}
int tetris_modem_prepare_bundle_b41(const void *p, size_t n,
		const unsigned char pin[32], const struct tetris_scp_security_ops *ops,
		size_t capacity, unsigned int gear, struct tetris_modem_prepared_bundle *out)
{
	(void)n; (void)pin; (void)ops; (void)capacity;
	assert(p == snapshot && !released && gear == 1);
	prepared_count++;
	if (fault == 5)
		return -EKEYREJECTED;
	memset(out, 0, sizeof(*out));
	out->bundle.members[0].payload_offset = 128;
	out->bundle.members[2].payload_offset = 1408;
	out->bundle.layout.rom_size = 1024;
	out->bundle.layout.dsp_offset = 1536;
	out->bundle.layout.dsp_size = 64;
	return 0;
}
int tetris_modem_emi_rows_b41(const void *rom, size_t n, size_t dsp,
		const struct tetris_modem_emi_resources *r, unsigned int gear,
		const char *phy, const unsigned char pin[32], struct tetris_modem_emi_rows *out)
{
	(void)r; (void)phy; (void)pin;
	assert(rom == snapshot + 128 && n == 1024 && dsp == 64 && gear == 1);
	assert(prepared_count == 1 && !released);
	produced_count++;
	if (fault == 6)
		return -ERANGE;
	memset(out, 0, sizeof(*out));
	out->row[0].slot = 32;
	return 0;
}
static int release_staging(struct staging_allocation *a, void *p, size_t n)
{
	(void)a;
	assert(p == snapshot && n == sizeof(snapshot) && !released);
	released++;
	/* Poison the released snapshot: footer/output must no longer depend on it. */
	memset(snapshot, 0xee, sizeof(snapshot));
	return release_fault ? -EBUSY : 0;
}
static int flush_payload(void *ctx, unsigned long start, unsigned long end)
{
	(void)ctx; (void)start; (void)end;
	return 0;
}
int tetris_modem_sync_payloads(void *p, size_t n, const struct tetris_modem_layout *l,
		size_t alignment, const struct tetris_modem_cache_ops *ops)
{
	assert(p == destination && n == sizeof(destination) && l->rom_size == 1024);
	assert(alignment == 64 && ops->flush == flush_payload && released == 1);
	synced++;
	return fault == 7 ? -EIO : 0;
}
static void sha(const void *p, size_t n, unsigned char digest[32])
{
	(void)p; (void)n; (void)digest;
	assert(0); /* The authentication boundary double must not pretend to verify. */
}
static int verify(const void *key, size_t kn, const void *tbs, size_t tn,
		const unsigned char sig[256])
{
	(void)key; (void)kn; (void)tbs; (void)tn; (void)sig;
	assert(0);
	return -EKEYREJECTED;
}
#include "extracted_storage.inc"

int main(int argc, char **argv)
{
	struct tetris_modem_boot_plan plan, before;
	struct tetris_modem_emi_rows rows, rows_before;
	struct tetris_modem_emi_resources r = { 0 };
	const struct tetris_scp_security_ops ops = { sha, verify };
	unsigned char footer[512], pin[32] = { 0 };
	int which, ret, expected = 0;
	assert(argc == 2);
	which = atoi(argv[1]);
	assert(which >= 0 && which < 14);
	memset(snapshot, 0x23, sizeof(snapshot));
	memset(destination, 0x6c, sizeof(destination));
	memset(&plan, 0xa5, sizeof(plan));
	memset(&rows, 0xa5, sizeof(rows));
	memset(footer, 0xa5, sizeof(footer));
	before = plan;
	rows_before = rows;
	r.firmware.base = (uintptr_t)destination;
	r.firmware.capacity = sizeof(destination);
	if (which <= 7)
		fault = which;
	if (which == 8 || which == 9 || which == 10)
		release_fault = 1;
	if (which == 9)
		fault = 5;
	if (which == 10)
		fault = 4;
	if (which == 11)
		r.firmware.capacity--;
	ret = tetris_modem_load_slot_handoff_b41(NULL, 'a', pin, &ops,
		destination, sizeof(destination), 1, "0", pin, &r, &plan, &rows,
		which == 12 ? destination : which == 13 ? snapshot : footer);
	switch (which) {
	case 1: expected = -ENODEV; break;
	case 2: case 6: expected = -ERANGE; break;
	case 3: expected = -ENOMEM; break;
	case 4: case 7: case 10: expected = -EIO; break;
	case 5: case 9: expected = -EKEYREJECTED; break;
	case 8: expected = -EBUSY; break;
	case 11: case 12: case 13: expected = -EINVAL; break;
	default: break;
	}
	assert(ret == expected);
	assert(released == ((which >= 4 && which <= 10) || which == 0 || which == 13));
	assert(synced == (which == 0 || which == 7));
	if (ret) {
		assert(!memcmp(&plan, &before, sizeof(plan)));
		assert(!memcmp(&rows, &rows_before, sizeof(rows)));
		for (size_t i = 0; i < sizeof(footer); i++)
			assert(footer[i] == 0xa5);
	}
	if (!ret) {
		assert(plan.layout.rom_size == 1024 && rows.row[0].slot == 32);
		assert(prepared_count == 1 && produced_count == 1);
		for (size_t i = 0; i < sizeof(footer); i++)
			assert(footer[i] == 0x23);
		assert(destination[0] == 0x23 && destination[1536] == 0x23);
	}
	if ((which >= 1 && which <= 6) || which >= 9) {
		for (size_t i = 0; i < sizeof(destination); i++)
			assert(destination[i] == 0x6c);
	}
	return 0;
}
