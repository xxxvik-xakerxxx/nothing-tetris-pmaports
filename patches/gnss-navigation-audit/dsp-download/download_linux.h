/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_DSP_DOWNLOAD_LINUX_H
#define B41_DSP_DOWNLOAD_LINUX_H

#include "download.h"

/* Adapter for an actual exclusively held O_RDWR|O_NONBLOCK gps0 descriptor.
 * Requires packaged1008 RX and the reviewed nonblocking TX extension. This is
 * not an opener/service/CLI and never acquires unknown profile inputs itself.
 * Caller supplies the exact retained session and owns normal close/recovery.
 * No poll assumption: stock gps0 has no .poll. Invoke step from the owner's
 * bounded event loop; EAGAIN retains the same request, never restarts download.
 */
int b41_download_linux_begin(struct b41_download *owner,
                             const struct b41_bootstrap_session *session,
                             uint64_t deadline_ns);
int b41_download_linux_step(struct b41_download *owner);

#endif
