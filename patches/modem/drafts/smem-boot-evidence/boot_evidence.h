/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_SMEM_BOOT_EVIDENCE_H
#define TETRIS_SMEM_BOOT_EVIDENCE_H
#ifdef TETRIS_SMEM_BOOT_HOST_TEST
#include <stddef.h>
#else
#include <linux/types.h>
#endif
#include "metadata_resources.h"

#define TETRIS_SMEM_BOOT_PROPERTY "nothing,modem-smem-boot-evidence"
#define TETRIS_SMEM_BOOT_BYTES 336U
#define TETRIS_SMEM_BOOT_END_MARKER (1ULL << 43)

struct tetris_smem_boot_record {
	unsigned int bank, slot;
	unsigned long long reservation_base, reservation_capacity;
	unsigned long long range_start, range_size;
	unsigned long long actual_start, actual_end, actual_enable;
	unsigned long long policy[8];
};

/* A copied value snapshot. Consume through const pointers after decoding;
 * no retained input pointers, mutator, ownership or permission state exists.
 * Raw actual_end preserves END_MARKER, including its absence.
 */
struct tetris_smem_boot_evidence {
	unsigned int version, bytes, scope, count, ap, md;
	unsigned int loaded_stage, boot_stage, errors[3], reserved;
	unsigned char preloader_sha256[32];
	struct tetris_smem_boot_record record[2];
};

/* Pure v1 decoder; return 0 or negative errno. The banks are an immutable,
 * already validated reservation snapshot, NOT addresses learned from evidence.
 * Caller keeps all input bytes stable for the duration of the call. All three
 * supplied spans must be disjoint and nonwrapping; bank bytes must be exact.
 * Output is unchanged on every error, including absent/truncated properties.
 * This checks NS_BL33_BOOT_EVIDENCE only: no Linux NS grant, authentication,
 * mapping, START, transport, readiness or protection assertion is produced.
 */
int tetris_smem_boot_decode(const void *wire, size_t wire_bytes,
		const struct tetris_metadata_banks *banks, size_t banks_bytes,
		struct tetris_smem_boot_evidence *output, size_t output_bytes);
#endif
