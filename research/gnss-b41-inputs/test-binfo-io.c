/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include "gpsdl_v051.h"

#ifdef BINFO_PIPE_TEST
static ssize_t pipe_read(void *buffer, size_t count)
{
	return read(STDIN_FILENO, buffer, count);
}
#endif

static int mock_open(const char *, int, ...);
static int mock_fstat(int, struct stat *);
static int mock_lstat(const char *, struct stat *);
static ssize_t mock_read(int, void *, size_t);
static ssize_t mock_write(int, const void *, size_t);
static int mock_ioctl(int, unsigned long, ...);
static int mock_close(int);
static unsigned int mock_alarm(unsigned int);
#define main probe_main
#define open mock_open
#define fstat mock_fstat
#define lstat mock_lstat
#define read mock_read
#define write mock_write
#define ioctl mock_ioctl
#define close mock_close
#define alarm mock_alarm
#include "binfo-probe.c"
#undef main

enum scenario {
	OK, BYTEWISE, TEMPLATE_OPEN, TEMPLATE_SIZE, TEMPLATE_METADATA,
	NODE_TYPE, DEVICE_OPEN, OPENED_TYPE, CLOCK_FLAG, CLOCK_FREQ,
	METADATA_ERROR, METADATA_RANGE, SHORT_WRITE, READ_ERROR, READ_EOF,
	BAD_CHECKSUM, WRONG_INDEX, CLOSE_ERROR, NOISE_LIMIT, BUDGET_OVERFLOW,
	DOWNLOAD_ONE, DOWNLOAD_106, DOWNLOAD_256_BYTEWISE, FRAGMENT_IOCTL_ERROR,
	FRAGMENT_WRONG_INDEX, FRAGMENT_CHECKSUM, FRAGMENT_EOF, DUPLICATE_BINFO,
	PARTIAL_AFTER_BINFO, SUPERVISED_OK, READY_REJECT, STOP_SHORT,
	RESET_REJECT, SCENARIO_COUNT
};
static enum scenario scenario;
static unsigned int opens, closes, writes, reads, timer, query_count;
static size_t position;
static unsigned int fragments, acknowledged;

static unsigned int fragment_count(void)
{
	return scenario == DOWNLOAD_ONE ? 1 : scenario == DOWNLOAD_256_BYTEWISE ? 256 : 106;
}

static int mock_open(const char *path, int flags, ...)
{
	assert(flags & O_NOFOLLOW);
	if (strcmp(path, "template.bin") == 0)
		return scenario == TEMPLATE_OPEN ? -1 : 10;
	assert(strcmp(path, "/dev/gpsdl0") == 0);
	assert((flags & O_ACCMODE) == O_RDWR);
	assert(++opens == 1);
	return scenario == DEVICE_OPEN ? -1 : 11;
}

static int mock_fstat(int fd, struct stat *st)
{
	memset(st, 0, sizeof(*st));
	assert(fd == 10 || fd == 11);
	st->st_mode = fd == 10 || scenario == OPENED_TYPE ? S_IFREG : S_IFCHR;
	st->st_size = scenario == TEMPLATE_SIZE ? 105 : 106;
	return 0;
}

static int mock_lstat(const char *path, struct stat *st)
{
	assert(strcmp(path, "/dev/gpsdl0") == 0);
	memset(st, 0, sizeof(*st));
	st->st_mode = scenario == NODE_TYPE ? S_IFREG : S_IFCHR;
	return 0;
}

static ssize_t mock_read(int fd, void *output, size_t count)
{
	unsigned char ack[40] = { 0xaa, 0xf0, 14, 0, 0x31, 0xfe };
	size_t size, length = 20;
	if (fd == STDIN_FILENO) {
		assert(scenario >= SUPERVISED_OK && count == 2);
		assert(fragments == fragment_count() && acknowledged == fragments);
		assert(writes == 1 || writes == 2);
#ifdef BINFO_PIPE_TEST
		return pipe_read(output, count);
#endif
		memcpy(output, writes == 1 ? "W\n" : "R\n", 2);
		if ((writes == 1 && scenario == READY_REJECT) ||
		    (writes == 2 && scenario == RESET_REJECT))
			((char *)output)[0] = 'X';
		return 2;
	}
	if (fd == 10) {
		assert(count == 107);
		memset(output, 0, 106);
		((unsigned char *)output)[0] = 0x1a;
		if (scenario == TEMPLATE_METADATA)
			((unsigned char *)output)[14] = 1;
		return 106;
	}
	assert(fd == 11 && count == 512 && writes == 1);
	reads++;
	if (scenario == READ_ERROR) {
		errno = EIO;
		return -1;
	}
	if (scenario == READ_EOF)
		return 0;
	if (scenario == NOISE_LIMIT) {
		assert(reads <= 8);
		memset(output, 0, count);
		return (ssize_t)count;
	}
	ack[16] = 0x3d;
	ack[17] = 1;
	ack[18] = 0xaa;
	ack[19] = 0x0f;
	if (scenario == BUDGET_OVERFLOW) {
		assert(reads <= 9);
		memset(output, 0, count);
		if (reads <= 8)
			return 500;
		memcpy(output, ack, length);
		return (ssize_t)count;
	}
	if (scenario == BAD_CHECKSUM)
		ack[16] ^= 1;
	if (scenario == WRONG_INDEX) {
		ack[6] = 1;
		ack[16]++;
	}
	if (fragments) {
		unsigned int index = fragments + (scenario == FRAGMENT_WRONG_INDEX);
		unsigned char body[8] = { 6, 0, 0x32, 0xfe, index & 255, index >> 8 };
		unsigned int sum = 0;
		size_t i;
		if (scenario == FRAGMENT_EOF)
			return 0;
		for (i = 0; i < 6; i++)
			sum += body[i];
		body[6] = (sum & 255) ^ (scenario == FRAGMENT_CHECKSUM);
		body[7] = sum >> 8;
		length = 2;
		for (i = 0; i < sizeof(body); i++) {
			if (body[i] == 0xaa || body[i] == 0xde) {
				ack[length++] = 0xde;
				ack[length++] = body[i] == 0xaa ? 0xdf : 0xe0;
			} else
				ack[length++] = body[i];
		}
		ack[length++] = 0xaa;
		ack[length++] = 0x0f;
	} else if (scenario == DUPLICATE_BINFO) {
		memcpy(ack + 20, ack, 20);
		length = 40;
	} else if (scenario == PARTIAL_AFTER_BINFO) {
		ack[20] = 0xaa;
		length = 21;
	}
	assert(position < length);
	size = scenario == BYTEWISE || scenario == DOWNLOAD_256_BYTEWISE ? 1 : length;
	memcpy(output, ack + position, size);
	position += size;
	if (position == length)
		acknowledged = fragments;
	return (ssize_t)size;
}

static ssize_t mock_write(int fd, const void *data, size_t size)
{
	unsigned char expected[106] = { 0x1a }, encoded[228];
	unsigned char metadata[] = { 1, 0, 2, 0, 3, 0, 4, 0, 0, 0 };
	assert(fd == 11 && ++writes <= 2);
	if (writes == 2) {
		const unsigned char stop[] = { 0xaa, 0xf0, 6, 0, 5, 0xfe, 4, 0, 13, 1, 0xaa, 15 };
		assert(scenario >= SUPERVISED_OK && scenario != READY_REJECT);
		assert(size == sizeof(stop) && !memcmp(data, stop, size));
		return scenario == STOP_SHORT ? (ssize_t)size - 1 : (ssize_t)size;
	}
	metadata[8] = fragment_count() & 255;
	metadata[9] = fragment_count() >> 8;
	memcpy(expected + 14, metadata, sizeof(metadata));
	assert(size == encode_binfo(expected, encoded));
	assert(memcmp(data, encoded, size) == 0);
	return scenario == SHORT_WRITE ? (ssize_t)size - 1 : (ssize_t)size;
}

static int mock_ioctl(int fd, unsigned long command, ...)
{
	va_list args;
	int result = 0;
	assert(fd == 11);
	va_start(args, command);
	if (command == 25) {
		assert(scenario >= DOWNLOAD_ONE && writes == 1 && position > 0);
		assert(acknowledged == fragments && fragments < fragment_count());
		assert(va_arg(args, unsigned long) == fragments);
		fragments++;
		position = 0;
		va_end(args);
		return scenario == FRAGMENT_IOCTL_ERROR ? -1 : 0;
	}
	assert(writes == 0 && ++query_count <= 3);
	if (command == 23) {
		struct gpsdl_v051_bootup_info *info = va_arg(args, void *);
		*info = (struct gpsdl_v051_bootup_info){ 1, 2, 3, 4, fragment_count() };
		if (scenario == METADATA_RANGE)
			info->frag_num = 257;
		if (scenario == METADATA_ERROR)
			result = -1;
	} else {
		assert(va_arg(args, unsigned long) == 0);
		assert(command == 11 || command == 30);
		result = command == 11 ? (scenario == CLOCK_FLAG ? -1 : 0x21)
			: (scenario == CLOCK_FREQ ? 1 : 0);
	}
	va_end(args);
	return result;
}

static int mock_close(int fd)
{
	assert(fd == 10 || fd == 11);
	if (fd == 11) {
		assert(++closes == 1);
		if (scenario == CLOSE_ERROR)
			errno = EIO;
		return scenario == CLOSE_ERROR ? -1 : 0;
	}
	return 0;
}

static unsigned int mock_alarm(unsigned int seconds)
{
	assert(seconds == 8 || seconds == 0);
	timer = seconds;
	return 0;
}

int main(void)
{
	char *argv[] = { "probe", "--experimental-binfo-only", "template.bin", NULL };
#ifdef BINFO_PIPE_TEST
	const char *mode = getenv("BINFO_PIPE_SCENARIO");
	scenario = mode && !strcmp(mode, "short-stop") ? STOP_SHORT : SUPERVISED_OK;
	argv[1] = "--experimental-supervised-download";
	return probe_main(3, argv);
#else
	for (scenario = OK; scenario < SCENARIO_COUNT; scenario++) {
		int expected = scenario == OK || scenario == BYTEWISE || scenario == SUPERVISED_OK ||
			(scenario >= DOWNLOAD_ONE && scenario <= DOWNLOAD_256_BYTEWISE) ? 0 : 1;
		argv[1] = scenario >= DOWNLOAD_ONE ? "--experimental-download" : "--experimental-binfo-only";
		if (scenario >= SUPERVISED_OK)
			argv[1] = "--experimental-supervised-download";
		opens = closes = writes = reads = timer = query_count = 0;
		fragments = acknowledged = 0;
		position = 0;
		errno = 0;
		assert(probe_main(3, argv) == expected);
		if (opens && scenario != DEVICE_OPEN)
			assert(closes == 1 && timer == 0);
		if (scenario >= OPENED_TYPE && scenario <= METADATA_RANGE)
			assert(writes == 0 && reads == 0);
		if (scenario == SHORT_WRITE)
			assert(writes == 1 && reads == 0);
		if ((scenario >= DOWNLOAD_ONE && scenario <= DOWNLOAD_256_BYTEWISE) ||
		    scenario >= SUPERVISED_OK)
			assert(fragments == fragment_count() && acknowledged == fragments);
		else if (scenario >= FRAGMENT_IOCTL_ERROR && scenario <= FRAGMENT_EOF)
			assert(fragments == 1 && reads == (scenario == FRAGMENT_IOCTL_ERROR ? 1U : 2U));
		else
			assert(fragments == 0);
		if (scenario >= SUPERVISED_OK)
			assert(writes == (scenario == READY_REJECT ? 1U : 2U));
	}
	puts("PASS: 33 native main-path scenarios; substituted I/O; supervised stop and ordered fragments");
	return 0;
#endif
}
