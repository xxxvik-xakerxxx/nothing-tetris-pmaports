/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_STARTUP_BUNDLE_H
#define B41_STARTUP_BUNDLE_H
#include "b41_runtime_config.h"
#include "b41_second_config.h"
struct b41_second_runtime_sources {
    unsigned present;
    uint32_t global_88a5c, bits_88c58;
    uint64_t bits_88c68;
    uint32_t buffer_base_de21c;
    uint8_t global_88c18, table_9a4eb;
};
#define B41_SECOND_RUNTIME_ALL 7u
enum b41_second_runtime_group {
    B41_SECOND_RUNTIME_SCALARS = 1u,
    B41_SECOND_RUNTIME_BUFFERS = 2u,
    B41_SECOND_RUNTIME_BYTES = 4u,
};
struct b41_startup_bundle {
    struct b41_runtime_config runtime;
    struct b41_second_config second;
    struct b41_startup_config abi;
    unsigned missing_contracts;
};
/* Copies proven additional26 second-config bytes and combines actual first/
 * second producer outputs into the engine's distinct0x70/0x444 input blocks.
 * Caller first/base comes from frozen builder + reviewed LNA query bridge.
 * No guessed XML -> scalar alias: XML consumers needing engine-global tuning
 * remain explicit policy gates. No init/run/register/stop/library call occurs.
 * Returns1 startup partial even if first byte provenance is complete.
 */
int b41_startup_bundle_build(const struct b41_first_config *first,
    const struct b41_runtime_sources *runtime,
    const struct b41_second_config *second,
    const struct b41_second_runtime_sources *second_runtime,
    const void *xml, size_t xml_size, struct b41_startup_bundle *out);
#endif
