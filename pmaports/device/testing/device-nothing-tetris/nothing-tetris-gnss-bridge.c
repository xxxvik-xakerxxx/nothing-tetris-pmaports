#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef O_NOFOLLOW
#define O_NOFOLLOW 0
#endif

#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define FRAME_CAPACITY 64U

static const uint8_t post_init_payload[] = { 0x32, 0x00, 0x00, 0x01, 0x00 };
static const uint8_t expected_post_init_frame[] = {
	0xaa, 0xf0, 0x09, 0x00, 0x05, 0xfe, 0x32, 0x00,
	0x00, 0x01, 0x00, 0x3f, 0x01, 0xaa, 0x0f,
};

static int append_escaped(uint8_t byte, uint8_t *frame, size_t capacity,
			  size_t *used)
{
	if (byte == 0xaa || byte == 0xde) {
		if (*used + 2U > capacity)
			return -1;
		frame[(*used)++] = 0xde;
		frame[(*used)++] = byte == 0xaa ? 0xdf : 0xe0;
		return 0;
	}
	if (*used == capacity)
		return -1;
	frame[(*used)++] = byte;
	return 0;
}

static int encode_frame(uint16_t command, const uint8_t *payload,
			size_t payload_size, uint8_t *frame, size_t capacity,
			size_t *frame_size)
{
	uint8_t body[32];
	uint16_t checksum = 0;
	size_t body_size = payload_size + 6U;
	size_t used = 0;

	if (!payload || !frame || !frame_size || payload_size == 0U ||
	    payload_size > sizeof(body) - 6U || capacity < 4U)
		return -1;
	body[0] = (uint8_t)(payload_size + 4U);
	body[1] = (uint8_t)((payload_size + 4U) >> 8);
	body[2] = (uint8_t)command;
	body[3] = (uint8_t)(command >> 8);
	memcpy(body + 4U, payload, payload_size);
	for (size_t i = 0; i < payload_size + 4U; ++i)
		checksum = (uint16_t)(checksum + body[i]);
	body[body_size - 2U] = (uint8_t)checksum;
	body[body_size - 1U] = (uint8_t)(checksum >> 8);

	frame[used++] = 0xaa;
	frame[used++] = 0xf0;
	for (size_t i = 0; i < body_size; ++i)
		if (append_escaped(body[i], frame, capacity, &used) != 0)
			return -1;
	if (used + 2U > capacity)
		return -1;
	frame[used++] = 0xaa;
	frame[used++] = 0x0f;
	*frame_size = used;
	return 0;
}

static int build_post_init_frame(uint8_t *frame, size_t capacity,
				 size_t *frame_size)
{
	return encode_frame(0xfe05, post_init_payload,
			    ARRAY_SIZE(post_init_payload), frame, capacity,
			    frame_size);
}

static int self_test(void)
{
	uint8_t frame[FRAME_CAPACITY];
	size_t frame_size = 0;

	if (build_post_init_frame(frame, sizeof(frame), &frame_size) != 0 ||
	    frame_size != ARRAY_SIZE(expected_post_init_frame) ||
	    memcmp(frame, expected_post_init_frame, frame_size) != 0) {
		fprintf(stderr, "nothing-tetris-gnss-bridge: frame self-test failed\n");
		return 1;
	}
	puts("PASS: exact B4.1 post-init frame; recording sink only");
	return 0;
}

static int write_all(int fd, const uint8_t *data, size_t size)
{
	while (size != 0U) {
		ssize_t written = write(fd, data, size);
		if (written < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (written == 0)
			return -1;
		data += (size_t)written;
		size -= (size_t)written;
	}
	return 0;
}

static int record_frame(const char *path)
{
	uint8_t frame[FRAME_CAPACITY];
	struct stat status;
	size_t frame_size = 0;
	int fd;
	int result = 1;

	if (!path || path[0] != '/' || strncmp(path, "/dev/", 5U) == 0) {
		fprintf(stderr, "nothing-tetris-gnss-bridge: recording path must be an absolute non-/dev path\n");
		return 1;
	}
	if (build_post_init_frame(frame, sizeof(frame), &frame_size) != 0)
		return 1;
	fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
		  0600);
	if (fd < 0) {
		perror("nothing-tetris-gnss-bridge: create recording");
		return 1;
	}
	if (fstat(fd, &status) != 0 || !S_ISREG(status.st_mode)) {
		fprintf(stderr, "nothing-tetris-gnss-bridge: recording sink is not a regular file\n");
		goto out;
	}
	if (write_all(fd, frame, frame_size) != 0 || fsync(fd) != 0) {
		perror("nothing-tetris-gnss-bridge: write recording");
		goto out;
	}
	result = 0;
out:
	if (close(fd) != 0 && result == 0) {
		perror("nothing-tetris-gnss-bridge: close recording");
		result = 1;
	}
	if (result != 0)
		unlink(path);
	return result;
}

int main(int argc, char **argv)
{
	if (argc == 2 && strcmp(argv[1], "--self-test") == 0)
		return self_test();
	if (argc == 3 && strcmp(argv[1], "--record-post-init") == 0)
		return record_frame(argv[2]);
	fprintf(stderr, "usage: %s --self-test | --record-post-init ABSOLUTE_FILE\n",
		argv[0]);
	return 2;
}
