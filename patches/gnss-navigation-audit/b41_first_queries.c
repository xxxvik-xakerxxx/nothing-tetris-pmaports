/* SPDX-License-Identifier: GPL-2.0-only */
#include <errno.h>
#include <sys/ioctl.h>
#include "b41_first_queries.h"

int b41_first_ioctl(void *context, int fd, unsigned command, uint32_t *output)
{
    (void)context;
    int result = ioctl(fd, command, output);
    return result < 0 ? -errno : result;
}

int b41_first_queries_collect(int fd, b41_first_query_fn query, void *context,
                              struct b41_first_queries *out)
{
    const unsigned commands[] = {11, 30, 16, 21};
    struct b41_first_queries result = {0};
    if (fd < 0 || !query || !out)
        return -EINVAL;
    for (unsigned i = 0; i < sizeof(commands) / sizeof(commands[0]); ++i) {
        unsigned command = commands[i];
        uint32_t scalar = 0;
        int status = query(context, fd, command,
                           (command == 16 || command == 21) ? &scalar : NULL);
        if (status >= 0 && ((command == 30 && status > 1) ||
                           ((command == 16 || command == 21) && status != 0)))
            status = -EPROTO;
        if (status < 0) {
            result.first_error = status;
            result.failed_command = command;
            *out = result;
            return status;
        }
        switch (command) {
        case 11:
            result.clock_flag = status;
            result.present |= B41_FIRST_CLOCK_QUERY;
            break;
        case 30:
            result.platform_clock_selector = status;
            result.platform_clock_valid = 1;
            break;
        case 16:
            result.lna_pin = scalar;
            result.present |= B41_FIRST_LNA_QUERY;
            break;
        case 21:
            result.modem_status = scalar;
            result.present |= B41_FIRST_MODEM_QUERY;
            break;
        }
    }
    *out = result;
    return 0;
}

int b41_first_config_from_queries(const struct b41_first_inputs *semantic,
                                  const struct b41_first_queries *queries,
                                  struct b41_first_config *out)
{
    const unsigned required = B41_FIRST_CLOCK_QUERY | B41_FIRST_LNA_QUERY |
                              B41_FIRST_MODEM_QUERY;
    if (!semantic || !queries || !out)
        return -EINVAL;
    if (queries->first_error)
        return queries->first_error < 0 ? queries->first_error : -EPROTO;
    if (queries->failed_command || queries->present != required ||
        !queries->platform_clock_valid || queries->clock_flag < 0 ||
        queries->platform_clock_selector < 0 || queries->platform_clock_selector > 1)
        return -EPROTO;
    if (semantic->present & required)
        return -EINVAL;
    struct b41_first_inputs inputs = *semantic;
    inputs.present |= required;
    inputs.clock_ioctl_result = queries->clock_flag;
    inputs.lna_ioctl_result = 0;
    inputs.lna_pin = queries->lna_pin;
    inputs.modem_ioctl_result = 0;
    inputs.modem_status = queries->modem_status;
    /* ioctl30 is a separate AGPS131 policy input, not first+18 frequency. */
    return b41_first_config_build(&inputs, out);
}
