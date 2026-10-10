/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_native_arguments.h"
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
int main(void)
{
    struct b41_startup_bundle bundle = {0};
    unsigned config = B41_MISSING_SECOND_POLICY | B41_MISSING_AGPS_RECEIVER;
    assert(b41_native_arguments_config_missing(NULL) == ~0u);
    assert(b41_native_arguments_config_missing(&bundle) == (config | B41_MISSING_FIRST_CONFIG));
    memset(bundle.runtime.first.provenance, B41_FIRST_CONSTANT,
        sizeof(bundle.runtime.first.provenance));
    bundle.missing_contracts = B41_MISSING_HOST_SERVICES | B41_MISSING_TRANSPORT_OWNER |
        B41_MISSING_STOP_CONTRACT;
    assert(b41_native_arguments_config_missing(&bundle) == config);
    bundle.runtime.first.provenance[27] = B41_FIRST_UNKNOWN;
    assert(b41_native_arguments_config_missing(&bundle) == (config | B41_MISSING_FIRST_CONFIG));
    bundle.runtime.first.provenance[27] = B41_FIRST_CONSTANT;
    bundle.runtime.first.xml_policy_missing = 1;
    assert(b41_native_arguments_config_missing(&bundle) & B41_MISSING_FIRST_CONFIG);
    bundle.runtime.first.xml_policy_missing = 0;
    bundle.runtime.first.missing_inputs = B41_FIRST_CALIBRATION;
    assert(b41_native_arguments_config_missing(&bundle) & B41_MISSING_FIRST_CONFIG);
    bundle.runtime.first.missing_inputs = 0;
    bundle.missing_contracts |= (1u << 25) | B41_MISSING_CALLBACK_ABI;
    assert(b41_native_arguments_config_missing(&bundle) ==
        (config | (1u << 25) | B41_MISSING_CALLBACK_ABI));
    struct b41_native_arguments_owner *owner = calloc(1, sizeof(*owner));
    assert(owner);
    assert(b41_native_arguments_execute(owner, NULL, NULL, NULL) == -EINVAL);
#if !defined(__aarch64__) || !defined(__BIONIC__)
    assert(b41_native_arguments_prepare(owner, NULL, NULL, 0, NULL,
        NULL, NULL, 0, NULL, NULL) == -EOPNOTSUPP);
    assert(!owner->entered);
#else
    assert(b41_native_arguments_prepare(owner, NULL, NULL, 0, NULL,
        NULL, NULL, 0, NULL, NULL) == -EINVAL);
    assert(!owner->entered);
    {
        struct b41_agps_owner ipc = {0};
        int fds[2] = {-1, -1}, app = -1, raw = -1;
        assert(b41_native_arguments_prepare(owner, &bundle, NULL, 0, NULL,
            &ipc, fds, 1, &app, &raw) == -ENODATA);
        ipc.initialized = 1;
        ipc.state = B41_AGPS_OWNED;
        assert(b41_native_arguments_prepare(owner, &bundle, NULL, 0, NULL,
            &ipc, fds, 1, &app, &raw) == -ESTALE);
        assert(!owner->entered && app == -1 && raw == -1 && fds[0] == -1);
    }
#endif
    owner->entered = 1;
    owner->first_error = -ESTALE;
    assert(b41_native_arguments_execute(owner, NULL, NULL, NULL) == -ESTALE);
    /* Only pure, never-bound fixture storage is freed. */
    free(owner);
    return 0;
}
