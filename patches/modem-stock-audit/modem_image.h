/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef TETRIS_MODEM_IMAGE_H
#define TETRIS_MODEM_IMAGE_H

#include <stddef.h>

enum tetris_modem_slot { TETRIS_MODEM_SLOT_A, TETRIS_MODEM_SLOT_B };
enum tetris_modem_member { TETRIS_MODEM_ROM, TETRIS_MODEM_DSP, TETRIS_MODEM_DRDI };

struct tetris_modem_span {
	size_t header_offset;
	size_t payload_offset;
	size_t payload_size;
};

/* Inventory and slot must come from validated boot metadata/GPT ownership.
 * No fallback to another slot or unsuffixed partition. Output unchanged on error.
 */
int tetris_modem_partition(enum tetris_modem_slot slot,
	const char *const *names, size_t count, const char **selected);

/* Read-only MTK 512-byte member locator, not an authenticator or loader.
 * Input is a caller-owned snapshot of ONE selected partition. Returns the
 * first named member, as LK does. The returned span remains UNAUTHENTICATED.
 * Other container formats return -EPROTONOSUPPORT; no format guessing.
 */
int tetris_modem_find_member(const void *partition, size_t extent,
	enum tetris_modem_member member, size_t max_payload, size_t max_headers,
	struct tetris_modem_span *span);

#endif
