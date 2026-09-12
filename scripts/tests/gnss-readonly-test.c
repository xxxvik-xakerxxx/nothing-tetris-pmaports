// SPDX-License-Identifier: GPL-2.0-only
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

static const char *scenario;
static unsigned int queries, opens, closes, armed, cancelled, stats;
static int mock_lstat(const char *, struct stat *);
static int mock_open(const char *, int, ...);
static int mock_ioctl(int, unsigned long, ...);
static int mock_close(int);
static unsigned int mock_alarm(unsigned int);

/* Compile the actual diagnostic with no route to device syscalls. */
#define main diagnostic_main
#define lstat mock_lstat
#define open mock_open
#define ioctl mock_ioctl
#define close mock_close
#define alarm mock_alarm
#include "nothing-tetris-gnss-readonly.c"
#undef main
#undef lstat
#undef open
#undef ioctl
#undef close
#undef alarm

static int is_case(const char *name)
{
	return strcmp(scenario, name) == 0;
}

static int error(void)
{
	errno = EIO;
	return -1;
}

static int mock_lstat(const char *path, struct stat *st)
{
	assert(strcmp(path, "/dev/gpsdl0") == 0);
	stats++;
	if (is_case("missing"))
		return error();
	memset(st, 0, sizeof(*st));
	st->st_mode = is_case("regular") ? S_IFREG :
		is_case("symlink") ? S_IFLNK : S_IFCHR;
	return 0;
}

static unsigned int mock_alarm(unsigned int seconds)
{
	if (seconds) {
		assert(seconds == 8 && opens == 0);
		armed++;
	} else {
		assert(armed == 1);
		cancelled++;
	}
	return 0;
}

static int mock_open(const char *path, int flags, ...)
{
	assert(strcmp(path, "/dev/gpsdl0") == 0);
	assert(flags == (O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
	assert(armed == 1 && stats == 1);
	opens++;
	return is_case("open-error") ? error() : 42;
}

static int mock_ioctl(int fd, unsigned long request, ...)
{
	va_list args;
	assert(fd == 42 && closes == 0 && armed == 1);
	queries++;
	va_start(args, request);
	if (queries == 1) {
		assert(request == GPSDL_V051_IOC_QUERY_STATUS);
		assert(va_arg(args, unsigned long) == 0UL);
	} else if (queries == 2) {
		struct gpsdl_v051_bootup_info *info;
		assert(request == GPSDL_V051_IOC_GET_DSP_BOOTUP_INFO);
		info = va_arg(args, struct gpsdl_v051_bootup_info *);
		info->frag_num = is_case("fragments") ? 257 :
			is_case("fragments-max") ? UINT32_MAX :
			is_case("zero-fragments") ? 0 : 256;
		info->code_size = 4096;
		info->cipher_key = 305419896;
	} else {
		struct gpsdl_v051_boot_time *time;
		assert(queries == 3 && request == GPSDL_V051_IOC_GET_BOOT_TIME);
		time = va_arg(args, struct gpsdl_v051_boot_time *);
		time->now_time = is_case("zero-time") ? 0 :
			is_case("negative-time") ? -1 : 1000;
		time->arch_counter = is_case("zero-counter") ? 0 :
			is_case("negative-counter") ? -1 : 2000;
	}
	va_end(args);
	if ((queries == 1 && is_case("status-error")) ||
		(queries == 2 && is_case("bootup-error")) ||
		(queries == 3 && is_case("time-error")))
		return error();
	return 0;
}

static int mock_close(int fd)
{
	assert(fd == 42 && ++closes == 1 && cancelled == 0);
	return is_case("close-error") ? error() : 0;
}

int main(int argc, char **argv)
{
	char *args[] = { "gnss-test", "--probe-link0", "extra", NULL };
	int result, success;
	unsigned int expected_queries;
	assert(argc == 2);
	scenario = argv[1];
	if (is_case("wrong-argument"))
		args[1] = "--probe-link1";
	result = diagnostic_main(is_case("no-argument") ? 1 :
		is_case("extra-argument") ? 3 : 2, args);
	success = is_case("valid") || is_case("zero-fragments");
	assert(result == (success ? EXIT_SUCCESS : EXIT_FAILURE));
	if (is_case("no-argument") || is_case("extra-argument") ||
		is_case("wrong-argument")) {
		assert(stats == 0 && armed == 0 && opens == 0 && queries == 0);
	} else if (is_case("missing") || is_case("regular") || is_case("symlink")) {
		assert(stats == 1 && armed == 0 && opens == 0 && queries == 0);
	} else if (is_case("open-error")) {
		assert(opens == 1 && queries == 0 && closes == 0);
	} else {
		expected_queries = is_case("status-error") ? 1 :
			(is_case("bootup-error") || is_case("fragments") ||
			is_case("fragments-max")) ? 2 : 3;
		assert(opens == 1 && queries == expected_queries && closes == 1);
	}
	assert(cancelled == (opens ? 1U : 0U));
	return 0;
}
