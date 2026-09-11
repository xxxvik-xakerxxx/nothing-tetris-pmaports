/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "modem_image.h"
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	const char *const names[] = { "md1rom", "md1dsp", "md1drdi" };
	struct stat st;
	void *data;
	int fd;

	if (argc != 2)
		return 2;
	fd = open(argv[1], O_RDONLY);
	if (fd < 0)
		return 2;
	if (fstat(fd, &st) || st.st_size <= 0 || st.st_size > 512 * 1024 * 1024) {
		close(fd);
		return 2;
	}
	data = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
	close(fd);
	if (data == MAP_FAILED)
		return 2;
	puts("[");
	for (unsigned int i = 0; i < 3; i++) {
		struct tetris_modem_span span = { 0 };
		int ret = tetris_modem_find_member(data, (size_t)st.st_size, i,
			512 * 1024 * 1024, 128, &span);
		int truncated = 0;

		if (!ret) {
			struct tetris_modem_span guard = { 7, 8, 9 }, saved = guard;

			truncated = tetris_modem_find_member(data,
				span.payload_offset + span.payload_size - 1, i,
				512 * 1024 * 1024, 128, &guard);
			if (truncated >= 0 || memcmp(&guard, &saved, sizeof(guard))) {
				munmap(data, (size_t)st.st_size);
				return 3;
			}
		}

		printf("{\"name\":\"%s\",\"result\":%d,\"header_offset\":%zu,"
		       "\"payload_offset\":%zu,\"payload_size\":%zu,\"truncated_result\":%d}%s\n",
		       names[i], ret, span.header_offset, span.payload_offset,
		       span.payload_size, truncated, i == 2 ? "" : ",");
	}
	puts("]");
	munmap(data, (size_t)st.st_size);
	return 0;
}
