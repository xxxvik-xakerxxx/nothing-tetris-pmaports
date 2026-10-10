/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_SLOT0_ADC_H
#define B41_SLOT0_ADC_H
#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>

#define B41_ADC_CAPTURE_SIZE 0x50000u
#define B41_ADC_ROWS 0x500u
#define B41_ADC_ROW_SIZE 0x100u
#define B41_ADC_PACKET_MAX 640u

/* mnld5d770 -> 7f090: diagnostic envelope260/2, NOT AGPS150 or raw NMEA.
 * Pure constructor; samples are 64 LE32 words, row is one-based1..1280.
 * Error leaves output/written untouched. Input/output must not overlap.
 */
int b41_slot0_adc_packet(unsigned row, const void *samples, size_t length,
    void *output, size_t capacity, size_t *written);

/* Called synchronously per packet. Zero means the real diagnostic owner
 * accepted exactly one packet. No queue-only/default-success implementation.
 * Sink must be bounded/nonblocking. Packet storage is borrowed until return
 * and must not be retained. A sink does not establish receiver ownership.
 */
typedef int (*b41_adc_packet_sink)(void *, const void *, size_t);
int b41_slot0_adc_deliver(const void *capture, size_t length,
    b41_adc_packet_sink sink, void *context, unsigned *accepted);

/* One bounded read of the owner's already-open O_NONBLOCK FIFO input. No open,
 * close, poll, ioctl, flag mutation, retry or ownership transfer. fd provenance
 * is NOT established here; devices/regular files are rejected before read.
 * Especially do not substitute the gpsdl RX fd (its O_NONBLOCK is ignored).
 * A short OEM read would zero-pad ADC.txt; this implementation rejects it.
 * After buffer validation, failures wipe it, not promote valid ADC samples.
 */
int b41_slot0_adc_capture(int fd, void *capture, size_t capacity);

enum b41_adc_owner_state { B41_ADC_EMPTY, B41_ADC_OWNED, B41_ADC_COMPLETE, B41_ADC_FAILED };
struct b41_adc_snapshot_owner {
    enum b41_adc_owner_state state;
    int capture_fd, diagnostic_fd, first_error;
    struct stat capture_identity, diagnostic_identity;
    unsigned accepted;
};
/* Move a real fully sealed exact-size ADC snapshot and distinct already-open
 * NONBLOCK writable Linux diagnostic FIFO. No device/open/ioctl/flag mutation,
 * Android endpoint impersonation, sample synthesis or firmware ownership proof.
 * Failure leaves inputs/owner unchanged. Owner retained until process exit.
 */
int b41_slot0_adc_snapshot_take(struct b41_adc_snapshot_owner *owner,
    int *capture_fd, int *diagnostic_fd);
/* One source-backed row/atomic FIFO packet per call. No partial replay/retry;
 * backpressure, changed identity/flags or broken consumer latches first error.
 * Dedicated host thread only; temporary SIGPIPE containment never changes the
 * process disposition. A failed signal drain retains the blocked thread mask
 * until that host thread exits. Completed owners cannot be restarted.
 */
int b41_slot0_adc_snapshot_step(struct b41_adc_snapshot_owner *owner);
#endif
