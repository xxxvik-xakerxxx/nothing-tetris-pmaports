#include <assert.h>
#include <errno.h>
#include <string.h>
#include "b41_second_config.h"

int main(void)
{
    struct b41_second_inputs input = {0};
    struct b41_second_config out, before;
    uint8_t state[68];
    for (unsigned i = 0; i < sizeof(state); ++i) state[i] = (uint8_t)i;
    assert(b41_second_config_build(&input, &out) == 1);
    assert(out.provenance[0x10] == B41_SECOND_UNKNOWN);
    assert(out.provenance[0x70] == B41_SECOND_UNKNOWN);
    assert(out.provenance[0x1cc] == B41_SECOND_LITERAL);
    input.present = B41_SECOND_BUILD_POLICY | B41_SECOND_RECEIVER_FDS | B41_SECOND_MPE_STATE_COPY;
    input.build_type = "userdebug"; input.debuggable = "1";
    input.primary_fd = 37; input.secondary_fd = -1;
    input.mpe_state = state; input.mpe_state_size = sizeof(state);
    input.mpe_requested = 1; input.mpe_backend_result = 3;
    input.paths[B41_PATH_PRIMARY_DEVICE] = "/dev/runtime-selected";
    assert(b41_second_config_build(&input, &out) == 1);
    assert(out.missing_inputs == 0 && out.unresolved_bytes > 0);
    assert(out.receiver_owner_missing && out.stop_contract_missing && out.mpe_schema_missing);
    assert(out.bytes[0x10] == 37 && out.bytes[0x14] == 0);
    for (unsigned i = 0x14; i < 0x18; ++i) assert(out.provenance[i] == B41_SECOND_INACTIVE_SECONDARY);
    assert(out.bytes[0xc8] == 2 && out.bytes[0x6c] == 1);
    assert(!memcmp(out.bytes + 0x70, state, sizeof(state)));
    memset(state, 255, sizeof(state));
    assert(out.bytes[0x70] == 0 && out.bytes[0xb3] == 67); /* No retained pointer. */
    input.secondary_enabled = 1; input.secondary_fd = 38;
    input.mpe_backend_result = 2;
    assert(b41_second_config_build(&input, &out) == 1);
    assert(out.bytes[0x14] == 38 && out.provenance[0x14] == B41_SECOND_RECEIVER_FD);
    assert(out.bytes[0x6c] == 0);
    before = out;
    input.secondary_fd = 37;
    assert(b41_second_config_build(&input, &out) == -EINVAL);
    assert(!memcmp(&before, &out, sizeof(out)));
    input.secondary_fd = 38; input.mpe_state_size = 67;
    assert(b41_second_config_build(&input, &out) == -EINVAL);
    assert(!memcmp(&before, &out, sizeof(out)));
    input.mpe_state_size = 68; input.build_type = "invented";
    assert(b41_second_config_build(&input, &out) == -EINVAL);
    assert(!memcmp(&before, &out, sizeof(out)));
    input.build_type = "userdebug";
    input.paths[B41_PATH_PRIMARY_DEVICE] = "/this/path/is/too/long/for/field";
    assert(b41_second_config_build(&input, &out) == -ENAMETOOLONG);
    assert(!memcmp(&before, &out, sizeof(out)));
    return 0;
}
