/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "modem_image.h"

#include <errno.h>
#include <stdint.h>
#include <string.h>

#define MTK_HEADER_SIZE 512U
#define MTK_HEADER_MAGIC 0x58881688U

static uint32_t le32(const unsigned char *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
		(uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int tetris_modem_partition(enum tetris_modem_slot slot,
	const char *const *names, size_t count, const char **selected)
{
	const char *wanted, *found = NULL;

	if (!names || !selected ||
	    (slot != TETRIS_MODEM_SLOT_A && slot != TETRIS_MODEM_SLOT_B))
		return -EINVAL;
	wanted = slot == TETRIS_MODEM_SLOT_A ? "modem_a" : "modem_b";
	for (size_t i = 0; i < count; i++) {
		if (!names[i])
			return -EINVAL;
		if (strcmp(names[i], wanted))
			continue;
		if (found)
			return -EEXIST;
		found = names[i];
	}
	if (!found)
		return -ENOENT;
	*selected = found;
	return 0;
}

int tetris_modem_find_member(const void *partition, size_t extent,
	enum tetris_modem_member member, size_t max_payload, size_t max_headers,
	struct tetris_modem_span *span)
{
	static const char *const names[] = { "md1rom", "md1dsp", "md1drdi" };
	const unsigned char *data = partition;
	size_t offset = 0;

	if (!data || !span || !max_payload || !max_headers ||
	    (unsigned int)member >= sizeof(names) / sizeof(names[0]))
		return -EINVAL;
	for (size_t i = 0; i < max_headers; i++) {
		size_t payload, length, alignment, rounded;
		const unsigned char *header;

		if (offset == extent)
			return -ENOENT;
		if (extent - offset < MTK_HEADER_SIZE)
			return -EMSGSIZE;
		header = data + offset;
		if (le32(header) != MTK_HEADER_MAGIC)
			return -EPROTONOSUPPORT;
		if (!memchr(header + 8, 0, 32))
			return -EBADMSG;
		length = le32(header + 4);
		alignment = le32(header + 0x44);
		if (!length || !alignment || (alignment & (alignment - 1)))
			return -EBADMSG;
		payload = offset + MTK_HEADER_SIZE;
		if (length > extent - payload)
			return -EMSGSIZE;
		if (!strcmp((const char *)header + 8, names[member])) {
			if (length > max_payload)
				return -EFBIG;
			*span = (struct tetris_modem_span) { offset, payload, length };
			return 0;
		}
		/* LK skips 512 + roundup(dsize, align); guard both arithmetic
		 * and the snapshot extent before following an untrusted header.
		 */
		if (length > SIZE_MAX - (alignment - 1))
			return -EOVERFLOW;
		rounded = (length + alignment - 1) & ~(alignment - 1);
		if (rounded > extent - payload)
			return -EMSGSIZE;
		offset = payload + rounded;
	}
	return -E2BIG;
}
