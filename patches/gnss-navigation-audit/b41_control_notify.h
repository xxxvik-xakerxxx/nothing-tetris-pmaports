/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_CONTROL_NOTIFY_H
#define B41_CONTROL_NOTIFY_H
#include <stdint.h>

/* Callback0 event7 only. Policy byte must be the caller's real runtime policy
 * (mnld global88a55), not a fabricated default. Zero means socket accepted the
 * packet, one means OEM bit4 suppressed it. Neither means navigation works.
 * Other events have additional mandatory effects and are rejected before I/O.
 */
int b41_control_notify(unsigned event, uint8_t runtime_policy);
#endif
