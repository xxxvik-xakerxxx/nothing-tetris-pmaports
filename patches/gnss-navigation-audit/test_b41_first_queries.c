/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "b41_first_queries.h"

struct fixture { unsigned calls, fail_at; int error; };
static int query(void *context, int fd, unsigned command, uint32_t *output)
{
    struct fixture *f = context;
    const unsigned expected[] = {11, 30, 16, 21};
    assert(fd == 0 && f->calls < 4 && command == expected[f->calls]);
    ++f->calls;
    assert((command == 16 || command == 21) ? output != NULL : output == NULL);
    if (f->calls == f->fail_at)
        return f->error;
    if (command == 11) return 81;
    if (command == 30) return 1;
    *output = command == 16 ? 23 : 0x12345678;
    return 0;
}

int main(void)
{
    const unsigned commands[] = {11, 30, 16, 21};
    struct fixture f = {0};
    struct b41_first_queries result;
    assert(b41_first_queries_collect(0, query, &f, &result) == 0);
    assert(f.calls == 4 && !result.first_error && !result.failed_command);
    assert(result.present == (B41_FIRST_CLOCK_QUERY | B41_FIRST_LNA_QUERY |
                              B41_FIRST_MODEM_QUERY));
    assert(result.clock_flag == 81 && result.platform_clock_selector == 1 &&
           result.platform_clock_valid);
    assert(result.lna_pin == 23 && result.modem_status == 0x12345678);
    struct b41_first_inputs semantic = {0};
    struct b41_first_config config;
    assert(b41_first_config_from_queries(&semantic, &result, &config) == 1);
    assert(config.bytes[0x13] == 254 && config.bytes[0x54] == 23);
    assert(config.provenance[0x18] == B41_FIRST_CLOCK_RESULT);
    assert(config.xml_policy_missing && config.unresolved_bytes);
    struct b41_first_config config_before = config;
    for (unsigned i = 1; i <= 4; ++i) {
        f = (struct fixture){.fail_at = i, .error = -EFAULT};
        assert(b41_first_queries_collect(0, query, &f, &result) == -EFAULT);
        assert(f.calls == i && result.first_error == -EFAULT);
        assert(result.failed_command == commands[i - 1]);
        assert(b41_first_config_from_queries(&semantic, &result, &config) == -EFAULT);
        assert(!memcmp(&config, &config_before, sizeof(config)));
        assert(result.platform_clock_valid == (i > 2));
        assert(!(result.present & B41_FIRST_MODEM_QUERY));
        if (i <= 3) assert(!(result.present & B41_FIRST_LNA_QUERY));
    }
    for (unsigned i = 2; i <= 4; ++i) {
        f = (struct fixture){.fail_at = i, .error = 2};
        assert(b41_first_queries_collect(0, query, &f, &result) == -EPROTO);
        assert(f.calls == i);
    }
    struct b41_first_queries before = result;
    assert(b41_first_queries_collect(-1, query, &f, &result) == -EINVAL);
    assert(!memcmp(&before, &result, sizeof(result)));
    assert(b41_first_queries_collect(0, NULL, &f, &result) == -EINVAL);
    assert(b41_first_queries_collect(0, query, &f, NULL) == -EINVAL);
    puts("PASS: borrowed-fd query ABI, fail-first ownership, no retries and no failed-output promotion");
    return 0;
}
