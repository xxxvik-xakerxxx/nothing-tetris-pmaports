// SPDX-License-Identifier: GPL-2.0-only
#ifdef TETRIS_SMEM_BOOT_HOST_TEST
#include <errno.h>
#include <string.h>
#else
#include <linux/errno.h>
#include <linux/string.h>
#endif
#include "boot_evidence.h"

static unsigned int le32(const unsigned char *p)
{
	return (unsigned int)p[0] | (unsigned int)p[1] << 8 |
		(unsigned int)p[2] << 16 | (unsigned int)p[3] << 24;
}

static unsigned long long le64(const unsigned char *p)
{
	return le32(p) | (unsigned long long)le32(p + 4) << 32;
}

static int span(const void *p, size_t bytes)
{
	return p && bytes && (size_t)p <= (size_t)-1 - bytes;
}

static int overlaps(const void *a, size_t an, const void *b, size_t bn)
{
	return (size_t)a < (size_t)b + bn && (size_t)b < (size_t)a + an;
}

static int window_valid(const struct tetris_metadata_window *w)
{
	return w->base && w->capacity && !((w->base | w->capacity) & 4095) &&
		w->base <= ~0ULL - w->capacity;
}

int tetris_smem_boot_decode(const void *wire, size_t wire_bytes,
		const struct tetris_metadata_banks *banks, size_t banks_bytes,
		struct tetris_smem_boot_evidence *output, size_t output_bytes)
{
	/* These words are checked against the pinned policy helper in source tests
	 * and against its actual extracted C body in the CI sanitizer fixture.
	 */
	static const unsigned long long expected_policy[2][8] = {
		{ 0, 0xcff0f0c0ULL, 0, 0, 0, 0, 0, 0xc00000000ULL },
		{ 0, 0xc00300c0ULL, 0, 0, 0, 0, 0, 0xc00000000ULL },
	};
	static const unsigned char digest[32] =
		"\x5d\x2b\xed\xd0\x00\x49\xfc\xed\x98\x3d\x3a\xe5\x39\x89\x61\x6c"
		"\x5c\x9f\x46\xc4\xed\xdd\x32\xa0\x1a\x1a\xd4\x6f\xf8\xd2\xc5\x0f";
	const unsigned char *p = wire;
	const unsigned long long origin = 0x40000000ULL;
	const unsigned long long limit = origin + (1ULL << 35);
	struct tetris_smem_boot_evidence result = { 0 };
	struct tetris_metadata_banks snapshot;
	unsigned int bank, group;

	/* No dereference precedes validation of all externally supplied spans. */
	if (!span(wire, wire_bytes) || !span(banks, banks_bytes) ||
	    !span(output, output_bytes))
		return -EINVAL;
	if (wire_bytes != TETRIS_SMEM_BOOT_BYTES || banks_bytes != sizeof(snapshot))
		return -EMSGSIZE;
	if (output_bytes < sizeof(result))
		return -ENOSPC;
	if (overlaps(wire, wire_bytes, banks, banks_bytes) ||
	    overlaps(wire, wire_bytes, output, output_bytes) ||
	    overlaps(banks, banks_bytes, output, output_bytes))
		return -EINVAL;
	memcpy(&snapshot, banks, sizeof(snapshot));
	if (!window_valid(&snapshot.nc) || !window_valid(&snapshot.cache) ||
	    (snapshot.nc.base < snapshot.cache.base + snapshot.cache.capacity &&
	     snapshot.cache.base < snapshot.nc.base + snapshot.nc.capacity))
		return -ERANGE;
	result.version = le32(p);
	result.bytes = le32(p + 4);
	result.scope = le32(p + 8);
	result.count = le32(p + 12);
	result.ap = le32(p + 16);
	result.md = le32(p + 20);
	result.loaded_stage = le32(p + 24);
	result.boot_stage = le32(p + 28);
	for (group = 0; group < 3; group++)
		result.errors[group] = le32(p + 32 + group * 4);
	result.reserved = le32(p + 44);
	memcpy(result.preloader_sha256, p + 48, 32);
	if (result.version != 1 || result.bytes != TETRIS_SMEM_BOOT_BYTES ||
	    result.scope != 1 || result.count != 2 || result.ap != 6878 ||
	    result.md != 6299 || result.loaded_stage != 11 || result.boot_stage != 15 ||
	    result.errors[0] || result.errors[1] || result.errors[2] || result.reserved ||
	    memcmp(result.preloader_sha256, digest, 32))
		return -EBADMSG;
	for (bank = 0; bank < 2; bank++) {
		struct tetris_smem_boot_record *r = &result.record[bank];
		const struct tetris_metadata_window *w = bank ? &snapshot.cache : &snapshot.nc;
		unsigned long long end;

		p = (const unsigned char *)wire + 80 + bank * 128;
		r->bank = le32(p);
		r->slot = le32(p + 4);
		r->reservation_base = le64(p + 8);
		r->reservation_capacity = le64(p + 16);
		r->range_start = le64(p + 24);
		r->range_size = le64(p + 32);
		r->actual_start = le64(p + 40);
		r->actual_end = le64(p + 48);
		r->actual_enable = le64(p + 56);
		if (r->bank != bank || r->slot != 42 + bank ||
		    r->reservation_base != w->base || r->reservation_capacity != w->capacity)
			return -EBADMSG;
		/* Producer starts at the reservation base. Sizes are dynamic, not
		 * this handset's live NC/cache totals. Endpoint is start+size, NOT
		 * last-byte inclusive; ATF rejects the aperture's upper boundary.
		 */
		if (r->range_start != w->base || !r->range_size ||
		    ((r->range_start | r->range_size) & 4095) ||
		    r->range_start > ~0ULL - r->range_size ||
		    r->range_size > w->capacity || r->range_start < origin ||
		    r->range_start >= limit || r->range_size >= limit - r->range_start)
			return -ERANGE;
		end = r->range_start + r->range_size;
		if (r->actual_start != r->range_start ||
		    (r->actual_end & ~TETRIS_SMEM_BOOT_END_MARKER) != end ||
		    r->actual_enable != 1)
			return -EBADMSG;
		for (group = 0; group < 8; group++) {
			r->policy[group] = le64(p + 64 + group * 8);
			if (r->policy[group] != expected_policy[bank][group])
				return -EBADMSG;
		}
	}
	memcpy(output, &result, sizeof(result));
	return 0;
}
