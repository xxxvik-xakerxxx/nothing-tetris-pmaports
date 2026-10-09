/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_SECOND_CONFIG_H
#define B41_SECOND_CONFIG_H
#include "b41_startup_adapter.h"

enum b41_second_input {
    B41_SECOND_BUILD_POLICY = 1u << 0,
    B41_SECOND_RECEIVER_FDS = 1u << 1,
    B41_SECOND_MPE_STATE_COPY = 1u << 2,
};
enum b41_second_provenance {
    B41_SECOND_UNKNOWN,
    B41_SECOND_LITERAL,
    B41_SECOND_BUILD_RESULT,
    B41_SECOND_PATH_INPUT,
    B41_SECOND_RECEIVER_FD,
    B41_SECOND_INACTIVE_SECONDARY,
    B41_SECOND_MPE_INPUT_COPY,
};
enum b41_second_path {
    B41_PATH_GPS_STATE, B41_PATH_OFFLOAD_STATE, B41_PATH_HOST_LOG,
    B41_PATH_PRIMARY_DEVICE, B41_PATH_SECONDARY_DEVICE, B41_PATH_SERIAL_OUTPUT,
    B41_PATH_DATA_DIRECTORY, B41_PATH_EPO0, B41_PATH_EPO1, B41_PATH_EPO2,
    B41_PATH_EPO3, B41_PATH_ASSISTANCE0, B41_PATH_ASSISTANCE1, B41_PATH_ASSISTANCE2,
    B41_PATH_ASSISTANCE3, B41_PATH_ASSISTANCE4, B41_PATH_ASSISTANCE5,
    B41_PATH_AUXILIARY0, B41_PATH_AUXILIARY1, B41_SECOND_PATH_COUNT,
};
struct b41_second_inputs {
    unsigned present;
    const char *build_type, *debuggable;
    /* gpsdl descriptors only, NEVER the AGPS IPC descriptor. Constructor is
     * pure; caller must provide the real owner's snapshot. No owner gate clears.
     */
    int primary_fd, secondary_fd;
    unsigned secondary_enabled; /* Actual56ce0 bit0 result, not inferred from fd. */
    /* Actual de4d4 producer bytes, not synthesized XML/calibration defaults.
     * Copying this state does not establish its unresolved semantic schema.
     */
    const uint8_t *mpe_state;
    size_t mpe_state_size;
    unsigned mpe_requested; /* Actual boolean(globalde228). */
    uint32_t mpe_backend_result; /* Actual56c70: bit0 survives AND with boolean. */
    const char *paths[B41_SECOND_PATH_COUNT];
};
struct b41_second_config {
    uint8_t bytes[B41_SECOND_CONFIG_SIZE];
    uint8_t provenance[B41_SECOND_CONFIG_SIZE];
    unsigned missing_inputs, unresolved_bytes;
    unsigned receiver_owner_missing, stop_contract_missing, mpe_schema_missing;
};

/* Explicit typed constructor and copied state; no XML decoder, native engine,
 * fd open/close/dup or default device/path guessing. Returns1 partial today;
 * all failures leave out untouched. Full policy/startup gates stay unresolved.
 */
int b41_second_config_build(const struct b41_second_inputs *inputs,
                            struct b41_second_config *out);
#endif
