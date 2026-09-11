/* SPDX-License-Identifier: GPL-2.0-only */
/* Experimental boot exchange. Not installed or started by a service. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include "gpsdl_v051.h"

enum { BODY_MAX = 508, READ_SIZE = 512, BINFO_SIZE = 106 };
_Static_assert(sizeof(struct gpsdl_v051_bootup_info) == 20, "boot ABI size changed");
struct decoder {
	unsigned int state;
	unsigned int expected_index;
	size_t used;
	unsigned char body[BODY_MAX];
};

static unsigned int le16(const unsigned char *p)
{
	return p[0] | ((unsigned int)p[1] << 8);
}

/* Index zero selects FE31; positive indices select FE32. */
static int check_expected_ack(const unsigned char *p, size_t size, unsigned int index)
{
	unsigned int sum = 0;
	size_t i;
	if (size < 7 || (le16(p) & 0xfff) != size - 2)
		return -1;
	for (i = 0; i < size - 2; i++)
		sum += p[i];
	if ((sum & 0xffff) != le16(p + size - 2))
		return -1;
	if (le16(p + 2) != 0xfe31 && le16(p + 2) != 0xfe32)
		return 0;
	if (index > 256 || le16(p + 2) != (index ? 0xfe32 : 0xfe31) ||
	    size != (index ? 8U : 16U) || le16(p + 4) != index)
		return -1;
	return 1;
}

static int receive_byte(struct decoder *d, unsigned char byte)
{
	int result;
	switch (d->state) {
	case 0:
		if (byte == 0xaa)
			d->state = 1;
		return 0;
	case 1:
		if (byte == 0xf0)
			d->state = 2;
		else if (byte != 0xaa)
			d->state = 0;
		return 0;
	case 2:
		if (byte == 0xaa) {
			d->state = 3;
			return 0;
		}
		if (byte == 0xde) {
			d->state = 4;
			return 0;
		}
		break;
	case 3:
		if (byte != 0x0f)
			goto fail;
		result = check_expected_ack(d->body, d->used, d->expected_index);
		if (result < 0)
			goto fail;
		d->state = 0;
		d->used = 0;
		return result;
	case 4:
		if (byte != 0xdf && byte != 0xe0)
			goto fail;
		byte = byte == 0xdf ? 0xaa : 0xde;
		d->state = 2;
		break;
	default:
		return -1;
	}
	if (d->used == sizeof(d->body))
		goto fail;
	d->body[d->used++] = byte;
	return 0;
fail:
	d->state = 5;
	d->used = 0;
	return -1;
}

static size_t encode_binfo(const unsigned char *payload, unsigned char *wire)
{
	unsigned char body[BINFO_SIZE + 6] = { BINFO_SIZE + 4, 0, 8, 0xfe };
	size_t i, n = 0;
	unsigned int sum = 0;
	memcpy(body + 4, payload, BINFO_SIZE);
	for (i = 0; i < sizeof(body) - 2; i++)
		sum += body[i];
	body[sizeof(body) - 2] = sum & 255;
	body[sizeof(body) - 1] = (sum >> 8) & 255;
	wire[n++] = 0xaa;
	wire[n++] = 0xf0;
	for (i = 0; i < sizeof(body); i++) {
		if (body[i] == 0xaa || body[i] == 0xde) {
			wire[n++] = 0xde;
			wire[n++] = body[i] == 0xaa ? 0xdf : 0xe0;
		} else
			wire[n++] = body[i];
	}
	wire[n++] = 0xaa;
	wire[n++] = 0x0f;
	return n;
}

#ifndef BINFO_UNIT_TEST
int main(int argc, char **argv)
{
	unsigned char payload[BINFO_SIZE + 1], wire[2 * (BINFO_SIZE + 6) + 4];
	unsigned char input[READ_SIZE];
	struct gpsdl_v051_bootup_info info = { 0 };
	struct decoder decoder = { 0 };
	struct stat st;
	uint32_t words[5];
	size_t i, size, total = 0;
	unsigned int index = 0;
	ssize_t count;
	int fd, template_fd, result = EXIT_FAILURE, ack = 0, download, supervised;
	unsigned char token[2];
	static const unsigned char stop_wire[] = {
		0xaa, 0xf0, 6, 0, 5, 0xfe, 4, 0, 0x0d, 1, 0xaa, 0x0f
	};
	const char *stage = "template";
	if (argc != 3 || (strcmp(argv[1], "--experimental-binfo-only") != 0 &&
	    strcmp(argv[1], "--experimental-download") != 0 &&
	    strcmp(argv[1], "--experimental-supervised-download") != 0)) {
		fprintf(stderr, "usage: %s --experimental-binfo-only|--experimental-download|--experimental-supervised-download reviewed-template.bin\n", argv[0]);
		return EXIT_FAILURE;
	}
	supervised = strcmp(argv[1], "--experimental-supervised-download") == 0;
	download = supervised || strcmp(argv[1], "--experimental-download") == 0;
	/* The caller must verify template provenance and the handset profile. */
	template_fd = open(argv[2], O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
	if (template_fd < 0)
		return EXIT_FAILURE;
	if (fstat(template_fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size != BINFO_SIZE) {
		close(template_fd);
		return EXIT_FAILURE;
	}
	count = read(template_fd, payload, sizeof(payload));
	close(template_fd);
	if (count != BINFO_SIZE || le16(payload) != 0x1a || le16(payload + 2) != 0)
		return EXIT_FAILURE;
	for (i = 14; i < 24; i++)
		if (payload[i] != 0)
			return EXIT_FAILURE;
	if (lstat("/dev/gpsdl0", &st) != 0 || !S_ISCHR(st.st_mode))
		return EXIT_FAILURE;
	/* Default SIGALRM terminates userspace; it cannot cure a stuck kernel. */
	alarm(8);
	fd = open("/dev/gpsdl0", O_RDWR | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return EXIT_FAILURE;
	stage = "opened device type";
	if (fstat(fd, &st) != 0 || !S_ISCHR(st.st_mode))
		goto out;
	stage = "26MHz co-clock profile";
	if (ioctl(fd, 11U, 0UL) != 0x21 || ioctl(fd, 30U, 0UL) != 0)
		goto out;
	stage = "boot metadata";
	if (ioctl(fd, GPSDL_V051_IOC_GET_DSP_BOOTUP_INFO, &info) != 0)
		goto out;
	words[0] = info.code_size;
	words[1] = info.start_addr;
	words[2] = info.exec_addr;
	words[3] = info.cipher_key;
	words[4] = info.frag_num;
	if (!info.code_size || !info.frag_num || info.frag_num > 256)
		goto out;
	for (i = 0; i < 5; i++) {
		if (words[i] > 0xffff)
			goto out;
		payload[14 + i * 2] = words[i] & 255;
		payload[15 + i * 2] = words[i] >> 8;
	}
	size = encode_binfo(payload, wire);
	stage = "single BINFO write";
	if (write(fd, wire, size) != (ssize_t)size)
		goto out;
	stage = "FE31 acknowledgement";
receive:
	while (!ack && total < 4096) {
		count = read(fd, input, sizeof(input));
		if (count <= 0 || count > READ_SIZE)
			goto out;
		if ((size_t)count > 4096 - total) {
			stage = "receive budget";
			goto out;
		}
		total += (size_t)count;
		for (i = 0; i < (size_t)count; i++) {
			int parsed = receive_byte(&decoder, input[i]);
			if (parsed < 0 || (parsed && ack))
				goto out;
			ack |= parsed;
		}
	}
	/* Do not discard a partial frame when advancing the request epoch. */
	if (!ack || decoder.state != 0)
		goto out;
	if (download && index < info.frag_num) {
		index++;
		decoder = (struct decoder){ .expected_index = index };
		ack = 0;
		total = 0;
		stage = "firmware fragment ioctl";
		/* v051 request 25 takes a scalar zero-based index, not a pointer. */
		if (ioctl(fd, 25U, (unsigned long)(index - 1)) != 0)
			goto out;
		stage = "FE32 acknowledgement";
		goto receive;
	}
	if (supervised) {
		stage = "supervisor RAM-code readiness";
		if (puts("DOWNLOAD_COMPLETE") == EOF || fflush(stdout) != 0 ||
		    read(STDIN_FILENO, token, sizeof(token)) != sizeof(token) ||
		    memcmp(token, "W\n", sizeof(token)) != 0)
			goto out;
		stage = "single runtime stop write";
		if (write(fd, stop_wire, sizeof(stop_wire)) != sizeof(stop_wire))
			goto out;
		stage = "supervisor runtime reset";
		if (puts("STOP_WRITTEN") == EOF || fflush(stdout) != 0 ||
		    read(STDIN_FILENO, token, sizeof(token)) != sizeof(token) ||
		    memcmp(token, "R\n", sizeof(token)) != 0)
			goto out;
	}
	result = EXIT_SUCCESS;
out:
	if (result != EXIT_SUCCESS)
		fprintf(stderr, "BINFO probe failed at %s; no retry\n", stage);
	if (close(fd) != 0) {
		perror("BINFO probe close");
		result = EXIT_FAILURE;
	}
	alarm(0);
	if (result == EXIT_SUCCESS) {
		if (supervised) {
			if (puts("CLOSED") == EOF || fflush(stdout) != 0)
				return EXIT_FAILURE;
		} else if (download)
			printf("FE31 and %u FE32 acknowledgements received; link closed; kernel teardown and navigation unverified\n", index);
		else
			puts("FE31 index=0 received; link closed; no firmware fragments submitted");
	}
	return result;
}
#endif
