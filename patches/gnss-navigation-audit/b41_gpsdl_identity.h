/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_GPSDL_IDENTITY_H
#define B41_GPSDL_IDENTITY_H
#include <sys/types.h>
struct b41_gpsdl_identity {
    int primary_fd, secondary_fd;
    dev_t primary_device, secondary_device;
};
/* Actual Linux kernel sysfs/character-fd identity, not caller proof flags.
 * Does not open GPS nodes, duplicate/adopt/close fds, issue ioctls or power GPS.
 * Primary must be the exclusively owned O_RDWR gpsdl0 open. Optional secondary
 * (-1 if absent) must be gpsdl1, not a dup of primary. Verifies dynamic rdev from
 * SYSFS_MAGIC-backed /sys/class/gpsdlN/gpsdlN/dev; majors are never hardcoded.
 * Source's exclusive open establishes device-session ownership; this identity
 * check cannot find external dup/fork aliases. Those remain forbidden by the
 * sole owner's lifecycle, not replaced by a new opt-in permission boolean.
 * Output unchanged on error. Zero identifies descriptors only: does not prove
 * firmware readiness, secondary policy, init, stop, or transfer to another process.
 */
int b41_gpsdl_identity_snapshot(int primary_fd, int secondary_fd, struct b41_gpsdl_identity *out);
#endif
