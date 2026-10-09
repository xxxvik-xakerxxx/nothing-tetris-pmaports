/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_engine_arguments.h"
#include <assert.h>
#include <errno.h>
#include <string.h>
static struct b41_host_adapter adapter;
int main(void)
{
    struct b41_known_callbacks callbacks, changed;
    struct b41_engine_callback_table table, before;
    struct b41_startup_bundle bundle = {0};
    struct b41_engine_arguments arguments, arguments_before;
    assert(b41_host_adapter_init(&adapter) == 0);
    assert(b41_host_adapter_bind(&adapter, &callbacks) == 0);
    assert(b41_engine_callback_table_build(&callbacks, &table) == 0);
    assert(table.notify == callbacks.notify && table.app_output == callbacks.app_output);
    assert(table.output == callbacks.output && table.frame_sleep == callbacks.frame_sleep);
    assert(table.frame_network == callbacks.frame_network && table.frame_measurement == callbacks.frame_measurement);
    assert(table.agps == callbacks.agps && table.passthrough == callbacks.passthrough);
    assert(table.encode == callbacks.encode && table.decode == callbacks.decode);
    for (unsigned i = 0; i < 14; ++i) assert(table.optional_null[i] == 0);
    before = table;
    assert(b41_engine_callback_table_build(NULL, &table) == -EINVAL);
    assert(memcmp(&table, &before, sizeof(table)) == 0);
    assert(b41_engine_callback_table_build(&callbacks, NULL) == -EINVAL);
#define MISSING(field) do { changed = callbacks; changed.field = NULL; \
    assert(b41_engine_callback_table_build(&changed, &table) == -ENODATA); \
    assert(memcmp(&table, &before, sizeof(table)) == 0); } while (0)
    MISSING(notify); MISSING(app_output); MISSING(frame_sleep); MISSING(frame_network);
    MISSING(frame_measurement); MISSING(agps); MISSING(passthrough); MISSING(encode); MISSING(decode);
    changed = callbacks; changed.output = NULL;
    assert(b41_engine_callback_table_build(&changed, &table) == 0 && table.output == NULL);
    memset(bundle.runtime.first.bytes, 0x31, sizeof(bundle.runtime.first.bytes));
    memset(bundle.second.bytes, 0x42, sizeof(bundle.second.bytes));
    assert(b41_engine_arguments_build(&bundle, &callbacks, &arguments) == 1);
    assert(memcmp(arguments.first, bundle.runtime.first.bytes, sizeof(arguments.first)) == 0);
    assert(memcmp(arguments.second, bundle.second.bytes, sizeof(arguments.second)) == 0);
    memset(&bundle, 0, sizeof(bundle));
    assert(arguments.first[0] == 0x31 && arguments.second[0] == 0x42);
    assert(arguments.missing_contracts & B41_MISSING_STOP_CONTRACT);
    assert(arguments.missing_contracts & B41_MISSING_HOST_SERVICES);
    assert(arguments.missing_contracts & B41_MISSING_TRANSPORT_OWNER);
    assert(arguments.missing_contracts & B41_MISSING_AGPS_RECEIVER);
    assert(arguments.missing_contracts & B41_MISSING_SECOND_POLICY);
    arguments_before = arguments;
    assert(b41_engine_arguments_build(NULL, &callbacks, &arguments) == -EINVAL);
    assert(memcmp(&arguments, &arguments_before, sizeof(arguments)) == 0);
    assert(b41_engine_arguments_build(&bundle, NULL, &arguments) == -EINVAL);
    assert(memcmp(&arguments, &arguments_before, sizeof(arguments)) == 0);
    changed = callbacks; changed.notify = NULL;
    assert(b41_engine_arguments_build(&bundle, &changed, &arguments) == -ENODATA);
    assert(memcmp(&arguments, &arguments_before, sizeof(arguments)) == 0);
    bundle.runtime.first.unresolved_bytes = 1;
    assert(b41_engine_arguments_build(&bundle, &callbacks, &arguments) == 1);
    assert(arguments.missing_contracts & B41_MISSING_FIRST_CONFIG);
    bundle.runtime.first.unresolved_bytes = 0;
    bundle.runtime.first.missing_inputs = 1;
    assert(b41_engine_arguments_build(&bundle, &callbacks, &arguments) == 1);
    assert(arguments.missing_contracts & B41_MISSING_FIRST_CONFIG);
    bundle.runtime.first.missing_inputs = 0;
    bundle.runtime.first.xml_policy_missing = 1;
    assert(b41_engine_arguments_build(&bundle, &callbacks, &arguments) == 1);
    assert(arguments.missing_contracts & B41_MISSING_FIRST_CONFIG);
    memset(&callbacks, 0, sizeof(callbacks));
    assert(arguments.callbacks.notify == arguments_before.callbacks.notify);
    /* Production callbacks, not test-generated success stubs. Pure codec call
     * demonstrates typed slot wiring without executing vendor registration/init.
     */
    assert(arguments.callbacks.passthrough(0x12345678) == 0x12345678);
    return 0;
}
