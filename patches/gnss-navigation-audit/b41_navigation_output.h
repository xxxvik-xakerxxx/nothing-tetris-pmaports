/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_NAVIGATION_OUTPUT_H
#define B41_NAVIGATION_OUTPUT_H
#include "b41_agps_host.h"
enum b41_navigation_output_state { B41_NAV_OUTPUT_EMPTY, B41_NAV_OUTPUT_OWNED, B41_NAV_OUTPUT_FAILED };
struct b41_navigation_output {
    enum b41_navigation_output_state state;
    int fd[2], first_error;
    int pty[2]; /* Actual TIOCGPTN identity; -1 for a FIFO. */
    struct stat identity[2];
    uint64_t delivered[2]; /* App slot1, raw/NMEA slot2; byte delivery, not fixes. */
};
/* Move two exclusive already-open NONBLOCK writable FIFO/PTY fds into fresh
 * zeroed process-lifetime storage. Slot1/app and slot2/output have distinct
 * consumers; never duplicate both callback streams into gpsd. No GPS device
 * fd, regular file, guessed socket endpoint or fd alias is accepted.
 * No dup/open/flag mutation; character sinks must pass read-only TIOCGPTN
 * (PTY master, not a UART/GPS fd). Failure leaves fds and owner unchanged.
 */
int b41_navigation_output_take(struct b41_navigation_output *owner, int *app_fd, int *raw_fd);
/* Bind once before the existing host worker starts. Retained until process
 * exit, no reset/unbind/close and no caller-set engine authorization flag.
 */
int b41_navigation_output_bind(struct b41_navigation_output *owner);
/* Existing worker's sole event dispatch. Frames3/4/5 reuse the existing AGPS
 * packet service. Slot1/2 deliver exact borrowed-output copies, preserving NUL
 * and fragmentation; gpsd/native consumer owns parsing and fix validity.
 * Generic AGPS_DATA remains refused: its parameter is NOT a proven length.
 * Sole host-worker thread only. Controller observes owner after quiescence;
 * no competing queue consumer. A SIGPIPE-drain failure retains the blocked
 * mask on this failed host thread until it exits, never on a vendor thread.
 * Does not call a vendor API, authorize init or claim engine stop/navigation.
 */
int b41_navigation_dispatch_event(struct b41_agps_owner *agps, const struct b41_host_event *event);
#endif
