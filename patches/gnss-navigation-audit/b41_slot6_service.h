/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_SLOT6_SERVICE_H
#define B41_SLOT6_SERVICE_H
#include "b41_navigation_output.h"
/* Bind once before worker start/registration to the SAME existing initialized
 * adapter. Replaces only slot6. Adapter must live until child exit, no unbind.
 * Source selector0 pointer is a borrowed NUL string (NULL means absent), NOT
 * parameter bytes. Only low16 selector/parameter have dispatcher meaning.
 * Selector1 ignores pointer. Other selectors fail sticky, not successful stubs.
 * At most1010 non-NUL bytes; longer input fails rather than truncating.
 */
int b41_slot6_service_bind(struct b41_host_adapter *adapter,
    struct b41_known_callbacks *callbacks);
/* Existing sole host worker dispatch replacement. Other kinds delegate to the
 * frozen navigation dispatcher. AGPS_DATA must be the exact typed150/152
 * envelope produced here, not the old parameter-as-length raw span.
 * Validates full framing/NUL/extent before using existing IPC owner's send.
 * Delivery is NOT a working assistance receiver or permission to clear AGPS.
 */
int b41_slot6_service_dispatch(struct b41_agps_owner *ipc,
    const struct b41_host_event *event);
#endif
