#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define NVRAM_SIZE 6146
#define NVRAM_PREFIX "WR-BUF:NVRAM"
#define NVRAM_PREFIX_SIZE (sizeof(NVRAM_PREFIX) - 1)

_Static_assert(NVRAM_PREFIX_SIZE == 12, "unexpected NVRAM command size");

static void fail(const char *format, ...)
{
	va_list arguments;

	fputs("nothing-tetris-wifi-nvram-load: ", stderr);
	va_start(arguments, format);
	vfprintf(stderr, format, arguments);
	va_end(arguments);
	fputc('\n', stderr);
	exit(EXIT_FAILURE);
}

static bool invalid_mac(const uint8_t *mac)
{
	bool all_zero = true;
	bool all_ones = true;
	size_t index;

	if (mac[0] & 1)
		return true;

	for (index = 0; index < 6; index++) {
		all_zero &= mac[index] == 0;
		all_ones &= mac[index] == 0xff;
	}

	return all_zero || all_ones;
}

int main(int argc, char **argv)
{
	const char *nvram_path = "/run/nothing-tetris/WIFI";
	const char *device_path = "/dev/wmtWifi";
	uint8_t message[NVRAM_PREFIX_SIZE + NVRAM_SIZE];
	struct stat metadata;
	ssize_t result;
	size_t offset;
	int input;
	int output;

	if (argc > 3)
		fail("usage: %s [NVRAM [DEVICE]]", argv[0]);
	if (argc >= 2)
		nvram_path = argv[1];
	if (argc == 3)
		device_path = argv[2];

	input = open(nvram_path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (input < 0)
		fail("cannot open NVRAM: %s", strerror(errno));
	if (fstat(input, &metadata) < 0)
		fail("cannot stat NVRAM: %s", strerror(errno));
	if (!S_ISREG(metadata.st_mode) || metadata.st_size != NVRAM_SIZE)
		fail("NVRAM must be a %d-byte regular file", NVRAM_SIZE);

	memcpy(message, NVRAM_PREFIX, NVRAM_PREFIX_SIZE);
	offset = NVRAM_PREFIX_SIZE;
	while (offset < sizeof(message)) {
		result = read(input, message + offset, sizeof(message) - offset);
		if (result < 0) {
			if (errno == EINTR)
				continue;
			fail("cannot read NVRAM: %s", strerror(errno));
		}
		if (result == 0)
			fail("unexpected end of NVRAM");
		offset += (size_t)result;
	}
	close(input);

	if (invalid_mac(message + NVRAM_PREFIX_SIZE + 4))
		fail("NVRAM contains an invalid Wi-Fi MAC address");

	output = open(device_path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
	if (output < 0)
		fail("cannot open %s: %s", device_path, strerror(errno));

	/* The vendor cdev accepts the command and payload in one write only. */
	result = write(output, message, sizeof(message));
	if (result != (ssize_t)sizeof(message))
		fail("single NVRAM write returned %zd instead of %zu", result,
		     sizeof(message));

	close(output);
	return EXIT_SUCCESS;
}
