/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_startup_bundle.h"
#include <errno.h>
#include <string.h>
static void put(struct b41_second_config *out, unsigned offset, uint64_t value, unsigned size)
{
    for (unsigned i = 0; i < size; ++i) {
        out->bytes[offset+i] = (uint8_t)(value >> (8*i));
        out->provenance[offset+i] = B41_RUNTIME_PROVENANCE;
    }
}
int b41_startup_bundle_build(const struct b41_first_config *first,
    const struct b41_runtime_sources *runtime,
    const struct b41_second_config *second,
    const struct b41_second_runtime_sources *s,
    const void *xml, size_t xml_size, struct b41_startup_bundle *out)
{
    struct b41_startup_bundle result;
    int status;
    if (!first || !runtime || !second || !s || !out || (s->present & ~B41_SECOND_RUNTIME_ALL))
        return -EINVAL;
    if (s->present != B41_SECOND_RUNTIME_ALL) return -ENODATA;
    memset(&result, 0, sizeof(result));
    status = b41_runtime_config_apply(first, runtime, xml, xml_size, &result.runtime);
    if (status < 0) return status;
    result.second = *second;
    /* Exact byte loads/copies, no reinterpretation of unknown float semantics. */
    put(&result.second, 0x24, s->global_88a5c, 4); /*63b98..63ba4*/
    put(&result.second, 0xb4, s->bits_88c58, 4); /*63b90..63b9c*/
    put(&result.second, 0xb8, s->bits_88c68, 8); /*63b94..63ba0*/
    put(&result.second, 0x64, s->buffer_base_de21c, 4); /*63924..63940*/
    put(&result.second, 0x68, s->buffer_base_de21c + 0x50000u, 4);
    put(&result.second, 0x0c, s->global_88c18, 1); /*63948..63954*/
    put(&result.second, 0xc4, s->table_9a4eb, 1); /*56c90..56c98;63a84*/
    result.second.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        result.second.unresolved_bytes += result.second.provenance[i] == B41_SECOND_UNKNOWN;
    memcpy(result.abi.first, result.runtime.first.bytes, B41_FIRST_CONFIG_SIZE);
    memcpy(result.abi.second, result.second.bytes, B41_SECOND_CONFIG_SIZE);
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        result.abi.resolved_second[i] = result.second.provenance[i] != B41_SECOND_UNKNOWN;
    result.missing_contracts = B41_MISSING_SECOND_POLICY | B41_MISSING_TRANSPORT_OWNER |
        B41_MISSING_AGPS_RECEIVER | B41_MISSING_STOP_CONTRACT | B41_MISSING_HOST_SERVICES;
    if (result.runtime.first.unresolved_bytes || result.runtime.first.missing_inputs ||
        result.runtime.first.xml_policy_missing)
        result.missing_contracts |= B41_MISSING_FIRST_CONFIG;
    *out = result;
    return 1;
}
