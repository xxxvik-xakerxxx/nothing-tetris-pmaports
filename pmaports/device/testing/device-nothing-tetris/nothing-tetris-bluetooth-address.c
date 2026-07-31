#define _GNU_SOURCE

#include <endian.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

#ifndef AF_BLUETOOTH
#define AF_BLUETOOTH 31
#endif

#define BTPROTO_HCI 1
#define HCI_DEV_NONE 0xffff
#define HCI_CHANNEL_CONTROL 3

#define MGMT_EV_CMD_COMPLETE 0x0001
#define MGMT_EV_CMD_STATUS 0x0002
#define MGMT_OP_READ_UNCONF_INDEX_LIST 0x0036
#define MGMT_OP_SET_PUBLIC_ADDRESS 0x0039

struct sockaddr_hci {
	sa_family_t hci_family;
	uint16_t hci_dev;
	uint16_t hci_channel;
};

struct mgmt_hdr {
	uint16_t opcode;
	uint16_t index;
	uint16_t len;
} __attribute__((packed));

static void fail(const char *message)
{
	fprintf(stderr, "nothing-tetris: %s\n", message);
	exit(EXIT_FAILURE);
}

static void fail_errno(const char *message)
{
	fprintf(stderr, "nothing-tetris: %s: %s\n", message, strerror(errno));
	exit(EXIT_FAILURE);
}

static void read_factory_address(const char *path, uint8_t address[6])
{
	static const uint8_t fallback[6] = { 0x00, 0x00, 0x46, 0x67, 0x61, 0x01 };
	struct stat st;
	ssize_t count;
	int fd;
	int all_zero = 1;
	int all_ff = 1;
	size_t i;

	fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		fail_errno("cannot open factory Bluetooth address");
	if (fstat(fd, &st) < 0)
		fail_errno("cannot inspect factory Bluetooth address");
	if (!S_ISREG(st.st_mode) || st.st_size != 6)
		fail("factory Bluetooth address has an invalid format");

	count = read(fd, address, 6);
	if (count < 0)
		fail_errno("cannot read factory Bluetooth address");
	if (count != 6)
		fail("factory Bluetooth address is truncated");
	if (close(fd) < 0)
		fail_errno("cannot close factory Bluetooth address");

	for (i = 0; i < 6; i++) {
		all_zero &= address[i] == 0x00;
		all_ff &= address[i] == 0xff;
	}
	if ((address[0] & 0x01) || all_zero || all_ff ||
	    memcmp(address, fallback, sizeof(fallback)) == 0)
		fail("factory Bluetooth address is invalid");
}

static int open_mgmt_socket(void)
{
	const struct sockaddr_hci address = {
		.hci_family = AF_BLUETOOTH,
		.hci_dev = HCI_DEV_NONE,
		.hci_channel = HCI_CHANNEL_CONTROL,
	};
	const struct timeval timeout = { .tv_sec = 5 };
	int fd;

	fd = socket(AF_BLUETOOTH, SOCK_RAW | SOCK_CLOEXEC, BTPROTO_HCI);
	if (fd < 0)
		fail_errno("cannot open Bluetooth management socket");
	if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0)
		fail_errno("cannot set Bluetooth management timeout");
	if (bind(fd, (const struct sockaddr *)&address, sizeof(address)) < 0)
		fail_errno("cannot bind Bluetooth management socket");

	return fd;
}

static void send_command(int fd, uint16_t opcode, uint16_t index,
			 const void *payload, uint16_t payload_len)
{
	uint8_t packet[sizeof(struct mgmt_hdr) + 6];
	struct mgmt_hdr header = {
		.opcode = htole16(opcode),
		.index = htole16(index),
		.len = htole16(payload_len),
	};

	if (payload_len > sizeof(packet) - sizeof(header))
		fail("internal Bluetooth management command is too large");
	memcpy(packet, &header, sizeof(header));
	if (payload_len)
		memcpy(packet + sizeof(header), payload, payload_len);
	if (send(fd, packet, sizeof(header) + payload_len, 0) !=
	    (ssize_t)(sizeof(header) + payload_len))
		fail_errno("cannot send Bluetooth management command");
}

static size_t wait_command_complete(int fd, uint16_t command,
				    uint8_t *response, size_t response_size)
{
	uint8_t packet[512];

	for (;;) {
		struct mgmt_hdr header;
		uint16_t event;
		uint16_t payload_len;
		uint16_t completed_command;
		ssize_t count;

		count = recv(fd, packet, sizeof(packet), 0);
		if (count < 0)
			fail_errno("Bluetooth management command timed out");
		if ((size_t)count < sizeof(header))
			continue;
		memcpy(&header, packet, sizeof(header));
		event = le16toh(header.opcode);
		payload_len = le16toh(header.len);
		if ((size_t)count != sizeof(header) + payload_len || payload_len < 3)
			continue;
		memcpy(&completed_command, packet + sizeof(header),
		       sizeof(completed_command));
		completed_command = le16toh(completed_command);
		if (completed_command != command)
			continue;
		if (event != MGMT_EV_CMD_COMPLETE && event != MGMT_EV_CMD_STATUS)
			continue;
		if (packet[sizeof(header) + 2] != 0)
			fail("Bluetooth management command was rejected");
		if (event == MGMT_EV_CMD_STATUS)
			continue;
		payload_len -= 3;
		if (payload_len > response_size)
			fail("Bluetooth management response is too large");
		if (payload_len)
			memcpy(response, packet + sizeof(header) + 3, payload_len);
		return payload_len;
	}
}

static int read_unconfigured_index_once(int fd, uint16_t *controller_index)
{
	uint8_t response[258];
	uint16_t count;
	uint16_t index;
	size_t length;

	send_command(fd, MGMT_OP_READ_UNCONF_INDEX_LIST, HCI_DEV_NONE, NULL, 0);
	length = wait_command_complete(fd, MGMT_OP_READ_UNCONF_INDEX_LIST,
				       response, sizeof(response));
	if (length < sizeof(count))
		fail("Bluetooth unconfigured-index response is truncated");
	memcpy(&count, response, sizeof(count));
	count = le16toh(count);
	if (count == 0 && length == sizeof(count))
		return 0;
	if (count != 1 || length != sizeof(count) + sizeof(index))
		fail("expected exactly one unconfigured Bluetooth controller");
	memcpy(&index, response + sizeof(count), sizeof(index));
	*controller_index = le16toh(index);
	return 1;
}

static uint16_t wait_unconfigured_index(int fd)
{
	uint16_t index;
	unsigned int attempt;

	for (attempt = 0; attempt < 50; attempt++) {
		if (read_unconfigured_index_once(fd, &index))
			return index;
		usleep(100000);
	}
	fail("Bluetooth controller did not register in time");
	return HCI_DEV_NONE;
}

int main(int argc, char **argv)
{
	const char *path = "/run/nothing-tetris/BT_ADDR";
	uint8_t factory_address[6];
	uint8_t mgmt_address[6];
	uint32_t missing_options;
	uint16_t index;
	int fd;
	size_t response_len;
	size_t i;

	if (argc > 2)
		fail("usage: nothing-tetris-bluetooth-address [address-file]");
	if (argc == 2)
		path = argv[1];

	read_factory_address(path, factory_address);
	for (i = 0; i < 6; i++)
		mgmt_address[i] = factory_address[5 - i];

	fd = open_mgmt_socket();
	index = wait_unconfigured_index(fd);
	send_command(fd, MGMT_OP_SET_PUBLIC_ADDRESS, index,
		     mgmt_address, sizeof(mgmt_address));
	response_len = wait_command_complete(fd, MGMT_OP_SET_PUBLIC_ADDRESS,
				     (uint8_t *)&missing_options,
				     sizeof(missing_options));
	if (response_len != sizeof(missing_options) ||
	    le32toh(missing_options) != 0)
		fail("Bluetooth public-address response is invalid");
	if (close(fd) < 0)
		fail_errno("cannot close Bluetooth management socket");

	puts("nothing-tetris: factory Bluetooth address configured");
	return EXIT_SUCCESS;
}
