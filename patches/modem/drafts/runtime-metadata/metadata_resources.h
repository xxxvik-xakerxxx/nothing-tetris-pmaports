/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TETRIS_METADATA_RESOURCES_H
#define TETRIS_METADATA_RESOURCES_H
struct tetris_metadata_window {
	unsigned long long base, capacity;
};
struct tetris_metadata_banks {
	struct tetris_metadata_window firmware, nc, cache, tags;
};
#endif
