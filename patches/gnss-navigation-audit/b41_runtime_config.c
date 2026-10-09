/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_runtime_config.h"
#include "b41_xml_config.h"
#include <errno.h>
#include <string.h>

static void put(struct b41_first_config *out, unsigned offset, uint32_t value, unsigned size)
{
    for (unsigned i = 0; i < size; ++i) {
        out->bytes[offset + i] = (uint8_t)(value >> (8 * i));
        out->provenance[offset + i] = B41_RUNTIME_PROVENANCE;
    }
}
int b41_runtime_config_apply(const struct b41_first_config *base,
    const struct b41_runtime_sources *s, const void *xml, size_t xml_size,
    struct b41_runtime_config *out)
{
    static const uint32_t mode_flags[3] = {0x80000000u, 0x40000000u, 0xc0000000u};
    struct b41_runtime_config result;
    struct b41_xml_feature feature;
    uint32_t flags, nav, mpe;
    int status;
    if (!base || !s || !out || (s->present & ~B41_RUNTIME_ALL)) return -EINVAL;
    if (s->present != B41_RUNTIME_ALL) return -ENODATA;
    /* The actual62a20 query is BD_PRIORITY, NOT GnssMode. In this exact asset
     * it is absent; zero-initialized GET output therefore gives helper result0.
     * An alternate profile must not accidentally inherit this policy.
     */
    status = b41_xml_config_get(xml, xml_size, "BD_PRIORITY", &feature);
    if (status != -ENOENT) return status < 0 ? status : -EPROTO;
    memset(&result, 0, sizeof(result));
    result.first = *base;
    put(&result.first, 0x20, s->host_mode_88794 ? 1000 : 200, 4);
    flags = s->capabilities_de308;
    if (s->receiver_mode_88c1c >= 1 && s->receiver_mode_88c1c <= 3)
        flags |= mode_flags[s->receiver_mode_88c1c - 1];
    put(&result.first, 0x28, flags, 4);
    put(&result.first, 0x2c, s->secondary_de2fe ? s->capabilities_de308 : 0, 4);
    put(&result.first, 0x30, s->chip_id_de304, 4);
    put(&result.first, 0x34, s->secondary_de2fe ? s->chip_id_de304 : 0, 4);
    nav = s->nav_override_88e10 == UINT32_MAX ? s->nav_base_88c20 : s->nav_override_88e10;
    if (s->nav_override_88e14 != UINT32_MAX) nav = s->nav_override_88e14;
    put(&result.first, 0x38, nav, 4); /* BD_PRIORITY is absent: no forced4. */
    put(&result.first, 0x50, s->tracking_de9d8 > 1 ? 0 : s->tracking_de9d8, 1);
    mpe = 0;
    if (!(s->mpe_requested_de228 & 5) && !(s->mpe_requested_de228 & 8) &&
        s->host_mode_88794 && (s->mpe_probe_4eee0 & 1))
        mpe = s->mpe_flag_88c4c;
    put(&result.first, 0x5b, mpe, 1);
    put(&result.first, 0x6c, s->feature_present_ddd84 ? s->feature_88c80 : 0, 1);
    result.first.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i)
        result.first.unresolved_bytes += result.first.provenance[i] == B41_FIRST_UNKNOWN;
    result.xml_get_verified = result.engine_contract_missing = 1;
    /* XML decoding is proven, applying all library tuning consumers is not.
     * Preserve base.xml_policy_missing and base.missing_inputs verbatim.
     */
    *out = result;
    return 1;
}
