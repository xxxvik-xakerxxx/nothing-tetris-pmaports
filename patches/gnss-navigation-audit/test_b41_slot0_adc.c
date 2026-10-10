/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "b41_slot0_adc.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <signal.h>
#include <linux/memfd.h>
#include <sys/syscall.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static unsigned calls, fail_at;
static int sink(void *context, const void *bytes, size_t length)
{
    unsigned *total = context;
    const uint8_t *p = bytes;
    assert(length > 12 && p[0] == 4 && p[1] == 1 && p[4] == 2);
    assert(p[2] == 0 && p[3] == 0 && p[5] == 0 && p[6] == 0 && p[7] == 0);
    assert((size_t)(p[8] | (unsigned)p[9] << 8) == length - 12);
    assert(p[length - 2] == '\r' && p[length - 1] == '\n');
    ++calls;
    if (fail_at && calls == fail_at) return -EAGAIN;
    ++*total;
    return 0;
}

static int snapshot(const void *capture, int sealed)
{
    int fd = (int)syscall(__NR_memfd_create, "adc-fixture-not-hardware", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    assert(fd >= 0);
    assert(write(fd, capture, B41_ADC_CAPTURE_SIZE) == (ssize_t)B41_ADC_CAPTURE_SIZE);
    if (sealed) assert(!fcntl(fd, F_ADD_SEALS, F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL));
    return fd;
}

static void owned_snapshots(const void *capture)
{
    int source = snapshot(capture, 1), channel[2];
    assert(!pipe(channel));
    assert(!fcntl(channel[1], F_SETFL, O_NONBLOCK));
    int captured = source, diagnostic = channel[1];
    struct b41_adc_snapshot_owner owner = {0};
    assert(!b41_slot0_adc_snapshot_take(&owner, &captured, &diagnostic));
    assert(captured == -1 && diagnostic == -1);
    uint8_t expected[B41_ADC_PACKET_MAX], received[B41_ADC_PACKET_MAX];
    for (unsigned row = 1; row <= B41_ADC_ROWS; ++row) {
        size_t length;
        assert(!b41_slot0_adc_packet(row, (const uint8_t *)capture + (row - 1) * B41_ADC_ROW_SIZE,
            B41_ADC_ROW_SIZE, expected, sizeof(expected), &length));
        assert(!b41_slot0_adc_snapshot_step(&owner));
        assert(read(channel[0], received, sizeof(received)) == (ssize_t)length);
        assert(!memcmp(received, expected, length));
    }
    assert(owner.state == B41_ADC_COMPLETE && owner.accepted == B41_ADC_ROWS);
    assert(b41_slot0_adc_snapshot_step(&owner) == -EALREADY);
    assert(fcntl(source, F_GETFD) >= 0 && fcntl(channel[1], F_GETFD) >= 0);
    assert(!close(source) && !close(channel[0]) && !close(channel[1]));

    source = snapshot(capture, 0);
    assert(!pipe(channel)); assert(!fcntl(channel[1], F_SETFL, O_NONBLOCK));
    owner = (struct b41_adc_snapshot_owner){0};
    captured = source; diagnostic = channel[1];
    assert(b41_slot0_adc_snapshot_take(&owner, &captured, &diagnostic) == -EPERM);
    assert(captured == source && diagnostic == channel[1] && owner.state == B41_ADC_EMPTY);
    assert(!close(source) && !close(channel[0]) && !close(channel[1]));

    source = snapshot(capture, 1);
    assert(!pipe(channel)); assert(!fcntl(channel[1], F_SETFL, O_NONBLOCK));
    owner = (struct b41_adc_snapshot_owner){0};
    captured = source; diagnostic = channel[1];
    assert(!b41_slot0_adc_snapshot_take(&owner, &captured, &diagnostic));
    uint8_t filler[4096] = {0};
    while (write(channel[1], filler, sizeof(filler)) > 0) {}
    assert(errno == EAGAIN);
    assert(b41_slot0_adc_snapshot_step(&owner) == -EAGAIN && !owner.accepted);
    assert(read(channel[0], filler, sizeof(filler)) > 0);
    assert(b41_slot0_adc_snapshot_step(&owner) == -EAGAIN && !owner.accepted);
    assert(fcntl(source, F_GETFD) >= 0 && fcntl(channel[1], F_GETFD) >= 0);
    assert(!close(source) && !close(channel[0]) && !close(channel[1]));

    source = snapshot(capture, 1);
    assert(!pipe(channel)); assert(!fcntl(channel[1], F_SETFL, O_NONBLOCK));
    owner = (struct b41_adc_snapshot_owner){0};
    captured = source; diagnostic = channel[1];
    assert(!b41_slot0_adc_snapshot_take(&owner, &captured, &diagnostic));
    assert(!close(channel[0]));
    sigset_t before, after, pending;
    assert(!sigprocmask(SIG_SETMASK, NULL, &before));
    assert(b41_slot0_adc_snapshot_step(&owner) == -EPIPE && !owner.accepted);
    assert(b41_slot0_adc_snapshot_step(&owner) == -EPIPE);
    assert(!sigprocmask(SIG_SETMASK, NULL, &after));
    assert(sigismember(&before, SIGPIPE) == sigismember(&after, SIGPIPE));
    assert(!sigpending(&pending) && !sigismember(&pending, SIGPIPE));
    assert(!close(source) && !close(channel[1]));

    source = snapshot(capture, 1);
    assert(!pipe(channel)); assert(!fcntl(channel[1], F_SETFL, O_NONBLOCK));
    owner = (struct b41_adc_snapshot_owner){0};
    captured = source; diagnostic = channel[1];
    assert(!b41_slot0_adc_snapshot_take(&owner, &captured, &diagnostic));
    assert(!fcntl(channel[1], F_SETFL, 0));
    assert(b41_slot0_adc_snapshot_step(&owner) == -EACCES);
    assert(!fcntl(channel[1], F_SETFL, O_NONBLOCK));
    assert(b41_slot0_adc_snapshot_step(&owner) == -EACCES);
    assert(!close(source) && !close(channel[0]) && !close(channel[1]));

    source = snapshot(capture, 1);
    int original = dup(source), replacement = snapshot(capture, 1);
    assert(original >= 0 && replacement >= 0);
    assert(!pipe(channel)); assert(!fcntl(channel[1], F_SETFL, O_NONBLOCK));
    owner = (struct b41_adc_snapshot_owner){0};
    captured = source; diagnostic = channel[1];
    assert(!b41_slot0_adc_snapshot_take(&owner, &captured, &diagnostic));
    assert(dup2(replacement, source) == source);
    assert(b41_slot0_adc_snapshot_step(&owner) == -ESTALE);
    assert(dup2(original, source) == source);
    assert(b41_slot0_adc_snapshot_step(&owner) == -ESTALE);
    assert(!close(source) && !close(original) && !close(replacement) &&
        !close(channel[0]) && !close(channel[1]));
}

int main(void)
{
    uint8_t samples[B41_ADC_ROW_SIZE] = {0}, packet[B41_ADC_PACKET_MAX], before[B41_ADC_PACKET_MAX];
    uint8_t *capture = malloc(B41_ADC_CAPTURE_SIZE);
    size_t used = 99;
    unsigned accepted = 77, total = 0;
    int pipes[2];
    assert(capture);
    memset(packet, 0xa5, sizeof(packet)); memcpy(before, packet, sizeof(packet));
    assert(b41_slot0_adc_packet(0, samples, sizeof(samples), packet, sizeof(packet), &used) == -EINVAL);
    assert(used == 99 && !memcmp(packet, before, sizeof(packet)));
    assert(b41_slot0_adc_packet(1, samples, sizeof(samples), packet, 12, &used) == -ENOSPC);
    assert(used == 99 && !memcmp(packet, before, sizeof(packet)));
    assert(b41_slot0_adc_packet(1, packet, sizeof(samples), packet, sizeof(packet), &used) == -EINVAL);
    samples[0] = 0x78; samples[1] = 0x56; samples[2] = 0x34; samples[3] = 0x12;
    assert(!b41_slot0_adc_packet(1280, samples, sizeof(samples), packet, sizeof(packet), &used));
    assert(!memcmp(packet + 12, "$PMTKJAM3,1280,1280,12345678",
                   sizeof("$PMTKJAM3,1280,1280,12345678") - 1));
    unsigned checksum = 0;
    for (size_t i = 12; i < used - 5; ++i) checksum ^= packet[i];
    const char *hex = "0123456789ABCDEF";
    assert(packet[used - 5] == '*' && packet[used - 4] == hex[checksum >> 4] && packet[used - 3] == hex[checksum & 15]);
    memset(capture, 0, B41_ADC_CAPTURE_SIZE);
    assert(!b41_slot0_adc_deliver(capture, B41_ADC_CAPTURE_SIZE, sink, &total, &accepted));
    assert(accepted == 1280 && total == 1280 && calls == 1280);
    calls = total = 0; fail_at = 3;
    assert(b41_slot0_adc_deliver(capture, B41_ADC_CAPTURE_SIZE, sink, &total, &accepted) == -EAGAIN);
    assert(accepted == 2 && total == 2 && calls == 3);
    assert(pipe(pipes) == 0);
    assert(fcntl(pipes[0], F_SETFL, O_NONBLOCK) == 0);
    memset(capture, 0xa5, B41_ADC_CAPTURE_SIZE);
    assert(b41_slot0_adc_capture(pipes[0], capture, B41_ADC_CAPTURE_SIZE) == -EAGAIN);
    for (unsigned i = 0; i < B41_ADC_CAPTURE_SIZE; ++i) assert(!capture[i]);
    assert(write(pipes[1], samples, sizeof(samples)) == (ssize_t)sizeof(samples));
    assert(b41_slot0_adc_capture(pipes[0], capture, B41_ADC_CAPTURE_SIZE) == -EMSGSIZE);
    for (unsigned i = 0; i < B41_ADC_CAPTURE_SIZE; ++i) assert(!capture[i]);
    assert(fcntl(pipes[0], F_SETFL, 0) == 0);
    assert(b41_slot0_adc_capture(pipes[0], capture, B41_ADC_CAPTURE_SIZE) == -EACCES);
    assert(close(pipes[0]) == 0 && close(pipes[1]) == 0);
    int null = open("/dev/null", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    assert(null >= 0);
    assert(b41_slot0_adc_capture(null, capture, B41_ADC_CAPTURE_SIZE) == -ENOTSUP);
    assert(!close(null));
    for (unsigned row = 0; row < B41_ADC_ROWS; ++row)
        memcpy(capture + row * B41_ADC_ROW_SIZE, samples, sizeof(samples));
    owned_snapshots(capture);
    free(capture);
    return 0;
}
