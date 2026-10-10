/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "b41_slot0_adc.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <pthread.h>
#include <signal.h>
#include <string.h>
#include <unistd.h>

static void word(uint8_t *p, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (8 * i));
}

int b41_slot0_adc_packet(unsigned row, const void *samples, size_t length,
    void *output, size_t capacity, size_t *written)
{
    uint8_t packet[B41_ADC_PACKET_MAX];
    const uint8_t *in = samples;
    char message[624];
    unsigned checksum = 0;
    size_t used;
    int n;
    if (!samples || !output || !written || !row || row > B41_ADC_ROWS ||
        length != B41_ADC_ROW_SIZE) return -EINVAL;
    n = snprintf(message, sizeof(message), "$PMTKJAM3,%u,%u", B41_ADC_ROWS, row);
    if (n < 0 || (size_t)n >= sizeof(message)) return -EOVERFLOW;
    used = (size_t)n;
    for (unsigned i = 0; i < B41_ADC_ROW_SIZE; i += 4) {
        uint32_t value = (uint32_t)in[i] | (uint32_t)in[i + 1] << 8 |
            (uint32_t)in[i + 2] << 16 | (uint32_t)in[i + 3] << 24;
        n = snprintf(message + used, sizeof(message) - used, ",%08" PRIX32, value);
        if (n != 9 || (size_t)n >= sizeof(message) - used) return -EOVERFLOW;
        used += (size_t)n;
    }
    /* Pinned7b820 includes the leading '$'; do not normalize to NMEA. */
    for (size_t i = 0; i < used; ++i) checksum ^= (uint8_t)message[i];
    n = snprintf(message + used, sizeof(message) - used, "*%02X\r\n", checksum);
    if (n != 5 || (size_t)n >= sizeof(message) - used) return -EOVERFLOW;
    used += (size_t)n;
    if (capacity < used + 12) return -ENOSPC;
    uintptr_t src = (uintptr_t)samples, dst = (uintptr_t)output;
    if (src > UINTPTR_MAX - length || dst > UINTPTR_MAX - (used + 12) ||
        (src < dst + used + 12 && dst < src + length)) return -EINVAL;
    word(packet, 260);
    word(packet + 4, 2);
    /* 37450 stores strlen, no NUL and no presence byte. */
    word(packet + 8, (uint32_t)used);
    memcpy(packet + 12, message, used);
    memcpy(output, packet, used + 12);
    *written = used + 12;
    return 0;
}

int b41_slot0_adc_deliver(const void *capture, size_t length,
    b41_adc_packet_sink sink, void *context, unsigned *accepted)
{
    uint8_t packet[B41_ADC_PACKET_MAX];
    size_t used;
    int status;
    if (!capture || length != B41_ADC_CAPTURE_SIZE || !sink || !accepted)
        return -EINVAL;
    *accepted = 0;
    for (unsigned row = 1; row <= B41_ADC_ROWS; ++row) {
        status = b41_slot0_adc_packet(row,
            (const uint8_t *)capture + (row - 1) * B41_ADC_ROW_SIZE,
            B41_ADC_ROW_SIZE, packet, sizeof(packet), &used);
        if (!status) status = sink(context, packet, used);
        if (status) return status < 0 ? status : -EPROTO;
        ++*accepted;
    }
    return 0;
}

int b41_slot0_adc_capture(int fd, void *capture, size_t capacity)
{
    struct stat identity;
    int flags, status = 0;
    ssize_t received;
    if (!capture || capacity != B41_ADC_CAPTURE_SIZE) return -EINVAL;
    if (fd < 0) {
        memset(capture, 0, capacity);
        return -EINVAL;
    }
    flags = fcntl(fd, F_GETFL);
    if (flags < 0) status = -errno;
    else if ((flags & O_ACCMODE) == O_WRONLY || !(flags & O_NONBLOCK)) status = -EACCES;
    /* O_NONBLOCK does not make vendor GPS character-device read bounded. */
    if (!status && fstat(fd, &identity)) status = -errno;
    if (!status && !S_ISFIFO(identity.st_mode)) status = -ENOTSUP;
    if (!status) {
        received = read(fd, capture, B41_ADC_CAPTURE_SIZE);
        if (received < 0) status = -errno;
        else if (received != B41_ADC_CAPTURE_SIZE) status = -EMSGSIZE;
    }
    if (status) memset(capture, 0, capacity);
    return status;
}

static int snapshot_identity(int fd, const struct stat *expected, int capture)
{
    struct stat identity;
    if (fstat(fd, &identity)) return -errno;
    if (expected && (identity.st_dev != expected->st_dev || identity.st_ino != expected->st_ino ||
        identity.st_mode != expected->st_mode || identity.st_rdev != expected->st_rdev)) return -ESTALE;
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0) return -errno;
    if (capture) {
        if (!S_ISREG(identity.st_mode) || identity.st_size != B41_ADC_CAPTURE_SIZE ||
            (flags & O_ACCMODE) == O_WRONLY) return -EINVAL;
        int required = F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL;
        int seals = fcntl(fd, F_GET_SEALS);
        if (seals < 0) return -errno;
        if ((seals & required) != required) return -EPERM;
    } else {
        if (!S_ISFIFO(identity.st_mode)) return -ENOTSUP;
        if (!(flags & O_NONBLOCK) || (flags & O_ACCMODE) == O_RDONLY) return -EACCES;
        errno = 0;
        long atomic = fpathconf(fd, _PC_PIPE_BUF);
        if (atomic < 0) return errno ? -errno : -ENOTSUP;
        if ((unsigned long)atomic < B41_ADC_PACKET_MAX) return -EMSGSIZE;
    }
    return 0;
}

int b41_slot0_adc_snapshot_take(struct b41_adc_snapshot_owner *o, int *capture, int *diagnostic)
{
    struct b41_adc_snapshot_owner result = {0};
    if (!o || !capture || !diagnostic || capture == diagnostic || *capture < 0 ||
        *diagnostic < 0 || *capture == *diagnostic) return -EINVAL;
    if (o->state != B41_ADC_EMPTY) return -EALREADY;
    int error = snapshot_identity(*capture, NULL, 1);
    if (!error) error = snapshot_identity(*diagnostic, NULL, 0);
    if (error) return error;
    if (fstat(*capture, &result.capture_identity) || fstat(*diagnostic, &result.diagnostic_identity))
        return -errno;
    result.capture_fd = *capture; result.diagnostic_fd = *diagnostic;
    result.state = B41_ADC_OWNED;
    *o = result;
    *capture = *diagnostic = -1;
    return 0;
}

static int adc_fail(struct b41_adc_snapshot_owner *o, int error)
{
    if (!o->first_error) o->first_error = error;
    o->state = B41_ADC_FAILED;
    return o->first_error;
}

static int atomic_packet(int fd, const void *packet, size_t length, unsigned *delivered)
{
    sigset_t set, old, pending;
    if (sigemptyset(&set) || sigaddset(&set, SIGPIPE)) return -errno;
    int error = pthread_sigmask(SIG_BLOCK, &set, &old);
    if (error) return -error;
    int first = 0;
    *delivered = 0;
    if (sigpending(&pending)) first = -errno;
    else {
        int existed = sigismember(&pending, SIGPIPE);
        ssize_t n = write(fd, packet, length);
        *delivered = n == (ssize_t)length;
        first = n < 0 ? -errno : n != (ssize_t)length ? -EIO : 0;
        if (first == -EPIPE && !existed) {
            const struct timespec zero = {0, 0};
            int result = sigtimedwait(&set, NULL, &zero);
            if (result < 0 && errno != EAGAIN) return first;
        }
    }
    error = pthread_sigmask(SIG_SETMASK, &old, NULL);
    return first ? first : error ? -error : 0;
}

int b41_slot0_adc_snapshot_step(struct b41_adc_snapshot_owner *o)
{
    uint8_t samples[B41_ADC_ROW_SIZE], packet[B41_ADC_PACKET_MAX];
    size_t length;
    unsigned delivered = 0;
    if (!o) return -EINVAL;
    if (o->state == B41_ADC_FAILED) return o->first_error;
    if (o->state == B41_ADC_COMPLETE) return -EALREADY;
    if (o->state != B41_ADC_OWNED || o->accepted >= B41_ADC_ROWS) return -EPERM;
    int error = snapshot_identity(o->capture_fd, &o->capture_identity, 1);
    if (!error) error = snapshot_identity(o->diagnostic_fd, &o->diagnostic_identity, 0);
    if (error) return adc_fail(o, error);
    ssize_t count = pread(o->capture_fd, samples, sizeof(samples), (off_t)o->accepted * B41_ADC_ROW_SIZE);
    if (count < 0) return adc_fail(o, -errno);
    if (count != (ssize_t)sizeof(samples)) return adc_fail(o, -EMSGSIZE);
    error = b41_slot0_adc_packet(o->accepted + 1, samples, sizeof(samples), packet, sizeof(packet), &length);
    if (!error) error = atomic_packet(o->diagnostic_fd, packet, length, &delivered);
    if (delivered) ++o->accepted;
    if (error) return adc_fail(o, error);
    if (o->accepted == B41_ADC_ROWS) o->state = B41_ADC_COMPLETE;
    return 0;
}
