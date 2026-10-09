/* SPDX-License-Identifier: GPL-2.0-only */
#include <errno.h>
#include <string.h>
#include "b41_lna_query_plan.h"

int b41_queries_collect_with_lna_plan(int fd, enum b41_lna_query_profile profile,
    b41_first_query_fn query, void *context, struct b41_lna_query_snapshot *out)
{
    struct b41_lna_query_snapshot result = {0};
    struct b41_first_queries *q = &result.queries;
    int status;
    unsigned command = 11;
    if (!query || !out || fd < 0 || (unsigned)profile > B41_LNA_PINNED_METADATA_ABSENT)
        return -EINVAL;
    if (profile == B41_LNA_UNRESOLVED)
        return -EOPNOTSUPP;
    result.profile = profile;
    status = query(context, fd, command, NULL);
    if (status < 0)
        goto failed;
    q->clock_flag = status;
    q->present |= B41_FIRST_CLOCK_QUERY;
    command = 30;
    status = query(context, fd, command, NULL);
    if (status < 0)
        goto failed;
    if (status > 1) {
        status = -EPROTO;
        goto failed;
    }
    q->platform_clock_selector = status;
    q->platform_clock_valid = 1;
    command = 16;
    /* mnld62bcc initializes its sp+94 output before attempting ioctl16. */
    status = query(context, fd, command, &q->lna_pin);
    result.lna_query_status = status;
    if (!status) {
        result.lna_origin = B41_LNA_VALUE_QUERY;
        result.first_config_lna_word = q->lna_pin;
        q->present |= B41_FIRST_LNA_QUERY;
    } else if (((profile == B41_LNA_PINNED_MCUDL_DISABLED && status == -EFAULT) ||
                (profile == B41_LNA_PINNED_METADATA_ABSENT && status == -ENODATA)) &&
               q->lna_pin == 0) {
        /* Exact untouched-output branch only; never discard error writes. */
        result.lna_origin = B41_LNA_VALUE_OEM_RETAINED_ZERO;
    } else {
        if (status >= 0)
            status = -EPROTO;
        goto failed;
    }
    command = 21;
    status = query(context, fd, command, &q->modem_status);
    if (status) {
        if (status > 0)
            status = -EPROTO;
        goto failed;
    }
    q->present |= B41_FIRST_MODEM_QUERY;
    *out = result;
    return 0;
failed:
    q->failed_command = command;
    q->first_error = status;
    *out = result;
    return status;
}

int b41_first_config_from_lna_plan(const struct b41_first_inputs *semantic,
    const struct b41_lna_query_snapshot *snapshot, struct b41_first_config *out)
{
    struct b41_first_inputs inputs;
    struct b41_first_config result;
    const struct b41_first_queries *q;
    int status;
    if (!semantic || !snapshot || !out)
        return -EINVAL;
    q = &snapshot->queries;
    if (snapshot->profile == B41_LNA_UNRESOLVED ||
        (unsigned)snapshot->profile > B41_LNA_PINNED_METADATA_ABSENT)
        return -EOPNOTSUPP;
    if (q->first_error || q->failed_command || !q->platform_clock_valid ||
        q->platform_clock_selector < 0 || q->platform_clock_selector > 1 ||
        (q->present & (B41_FIRST_CLOCK_QUERY | B41_FIRST_MODEM_QUERY)) !=
        (B41_FIRST_CLOCK_QUERY | B41_FIRST_MODEM_QUERY))
        return -ENODATA;
    if (snapshot->lna_origin == B41_LNA_VALUE_QUERY) {
        if (snapshot->lna_query_status || !(q->present & B41_FIRST_LNA_QUERY) ||
            snapshot->first_config_lna_word != q->lna_pin)
            return -EPROTO;
    } else if (snapshot->lna_origin == B41_LNA_VALUE_OEM_RETAINED_ZERO) {
        if (!((snapshot->profile == B41_LNA_PINNED_MCUDL_DISABLED && snapshot->lna_query_status == -EFAULT) ||
              (snapshot->profile == B41_LNA_PINNED_METADATA_ABSENT && snapshot->lna_query_status == -ENODATA)) ||
            snapshot->first_config_lna_word || q->lna_pin || (q->present & B41_FIRST_LNA_QUERY))
            return -EPROTO;
    } else
        return -EOPNOTSUPP;
    inputs = *semantic;
    inputs.present &= ~B41_FIRST_LNA_QUERY;
    inputs.present |= B41_FIRST_CLOCK_QUERY | B41_FIRST_MODEM_QUERY;
    inputs.clock_ioctl_result = q->clock_flag;
    inputs.modem_ioctl_result = 0;
    inputs.modem_status = q->modem_status;
    if (snapshot->lna_origin == B41_LNA_VALUE_QUERY) {
        inputs.present |= B41_FIRST_LNA_QUERY;
        inputs.lna_ioctl_result = 0;
        inputs.lna_pin = q->lna_pin;
    }
    status = b41_first_config_build(&inputs, &result);
    if (status < 0)
        return status;
    if (snapshot->lna_origin == B41_LNA_VALUE_OEM_RETAINED_ZERO) {
        memset(result.bytes + 0x54, 0, 4);
        memset(result.provenance + 0x54, B41_FIRST_OEM_LNA_ZERO_PROVENANCE, 4);
        result.unresolved_bytes -= 4;
        /* Contract satisfied by producer initial value, not by a query result. */
        result.missing_inputs &= ~B41_FIRST_LNA_QUERY;
    }
    *out = result;
    return status; /* Still a partial config; XML/host/stop gates unchanged. */
}
