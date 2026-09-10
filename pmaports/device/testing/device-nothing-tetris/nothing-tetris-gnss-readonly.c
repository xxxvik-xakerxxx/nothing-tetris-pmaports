// SPDX-License-Identifier: GPL-2.0-only

#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

#include "gpsdl_v051.h"

#define GPSDL_DEVICE "/dev/gpsdl0"
#define GPSDL_DEADLINE_SECONDS 8U
#define GPSDL_MAX_FRAGMENTS 256U

_Static_assert(GPSDL_V051_IOC_QUERY_STATUS == 13U,
	"query-status command changed");
_Static_assert(GPSDL_V051_IOC_GET_DSP_BOOTUP_INFO == 23U,
	"boot-info command changed");
_Static_assert(GPSDL_V051_IOC_GET_BOOT_TIME == 28U,
	"boot-time command changed");
_Static_assert(sizeof(struct gpsdl_v051_boot_time) == 16,
	"boot-time layout changed");
_Static_assert(offsetof(struct gpsdl_v051_boot_time, arch_counter) == 8,
	"boot-time layout changed");
_Static_assert(sizeof(struct gpsdl_v051_bootup_info) == 20,
	"boot-info layout changed");
_Static_assert(offsetof(struct gpsdl_v051_bootup_info, frag_num) == 16,
	"boot-info layout changed");

static void usage(const char *program)
{
	fprintf(stderr, "usage: %s --probe-link0\n", program);
}

static int fail_errno(const char *operation)
{
	fprintf(stderr, "nothing-tetris-gnss-readonly: %s: %s\n",
		operation, strerror(errno));
	return EXIT_FAILURE;
}

int main(int argc, char **argv)
{
	struct gpsdl_v051_bootup_info bootup = { 0 };
	struct gpsdl_v051_boot_time boot_time = { 0 };
	struct stat st;
	int status;
	int fd;

	if (argc != 2 || strcmp(argv[1], "--probe-link0") != 0) {
		usage(argv[0]);
		return EXIT_FAILURE;
	}

	if (lstat(GPSDL_DEVICE, &st) != 0)
		return fail_errno("lstat " GPSDL_DEVICE);
	if (!S_ISCHR(st.st_mode)) {
		fprintf(stderr,
			"nothing-tetris-gnss-readonly: %s is not a character device\n",
			GPSDL_DEVICE);
		return EXIT_FAILURE;
	}

	alarm(GPSDL_DEADLINE_SECONDS);
	fd = open(GPSDL_DEVICE, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return fail_errno("open " GPSDL_DEVICE);

	status = ioctl(fd, GPSDL_V051_IOC_QUERY_STATUS, 0UL);
	if (status < 0) {
		fail_errno("query status ioctl");
		goto fail;
	}
	if (ioctl(fd, GPSDL_V051_IOC_GET_DSP_BOOTUP_INFO, &bootup) != 0) {
		fail_errno("get DSP boot-info ioctl");
		goto fail;
	}
	if (ioctl(fd, GPSDL_V051_IOC_GET_BOOT_TIME, &boot_time) != 0) {
		fail_errno("get boot-time ioctl");
		goto fail;
	}

	if (bootup.frag_num > GPSDL_MAX_FRAGMENTS ||
		boot_time.now_time <= 0 || boot_time.arch_counter <= 0) {
		fprintf(stderr,
			"nothing-tetris-gnss-readonly: invalid read-only response\n");
		goto fail;
	}

	printf("status=%d\n", status);
	printf("code_size=%u\n", bootup.code_size);
	printf("fragment_count=%u\n", bootup.frag_num);
	printf("boot_time_ns=%lld\n", (long long)boot_time.now_time);
	printf("arch_counter=%lld\n", (long long)boot_time.arch_counter);
	printf("cipher_key=redacted\n");

	if (close(fd) != 0)
		return fail_errno("close " GPSDL_DEVICE);
	alarm(0);
	return EXIT_SUCCESS;

fail:
	if (close(fd) != 0)
		fail_errno("close " GPSDL_DEVICE);
	return EXIT_FAILURE;
}
