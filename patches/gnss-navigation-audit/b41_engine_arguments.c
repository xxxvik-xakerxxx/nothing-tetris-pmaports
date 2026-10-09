/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_engine_arguments.h"
#include <errno.h>
#include <stddef.h>
#include <string.h>
#define SLOT(field, index) _Static_assert(offsetof(struct b41_engine_callback_table, field) == (index)*8u && \
    sizeof(((struct b41_engine_callback_table *)0)->field) == 8, "pinned AArch64 callback slot")
SLOT(notify,0); SLOT(app_output,1); SLOT(output,2); SLOT(frame_sleep,3);
SLOT(frame_network,4); SLOT(frame_measurement,5); SLOT(agps,6);
SLOT(passthrough,7); SLOT(encode,8); SLOT(decode,9);
_Static_assert(offsetof(struct b41_engine_callback_table, optional_null) == 80 &&
               sizeof(struct b41_engine_callback_table) == 192, "pinned24-slot extent");

int b41_engine_callback_table_build(const struct b41_known_callbacks *c,
                                   struct b41_engine_callback_table *out)
{
    struct b41_engine_callback_table result = {0};
    if (!c || !out) return -EINVAL;
    if (!c->notify || !c->app_output || !c->frame_sleep || !c->frame_network ||
        !c->frame_measurement || !c->agps || !c->passthrough || !c->encode || !c->decode)
        return -ENODATA;
    result.notify = c->notify; result.app_output = c->app_output; result.output = c->output;
    result.frame_sleep = c->frame_sleep; result.frame_network = c->frame_network;
    result.frame_measurement = c->frame_measurement; result.agps = c->agps;
    result.passthrough = c->passthrough; result.encode = c->encode; result.decode = c->decode;
    *out = result;
    return 0;
}
int b41_engine_arguments_build(const struct b41_startup_bundle *bundle,
    const struct b41_known_callbacks *callbacks, struct b41_engine_arguments *out)
{
    struct b41_engine_arguments result = {0};
    int status;
    if (!bundle || !out) return -EINVAL;
    status = b41_engine_callback_table_build(callbacks, &result.callbacks);
    if (status) return status;
    memcpy(result.first, bundle->runtime.first.bytes, sizeof(result.first));
    memcpy(result.second, bundle->second.bytes, sizeof(result.second));
    /* Never trust a caller-cleared missing mask as host-service/stop evidence. */
    result.missing_contracts = bundle->missing_contracts | B41_MISSING_SECOND_POLICY |
        B41_MISSING_HOST_SERVICES | B41_MISSING_TRANSPORT_OWNER |
        B41_MISSING_AGPS_RECEIVER | B41_MISSING_STOP_CONTRACT;
    if (bundle->runtime.first.unresolved_bytes || bundle->runtime.first.missing_inputs ||
        bundle->runtime.first.xml_policy_missing)
        result.missing_contracts |= B41_MISSING_FIRST_CONFIG;
    *out = result;
    return 1;
}
