/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_receiver_policy.h"
#include "b41_runtime_config.h"
#include <errno.h>
#include <string.h>

static int valid_property(const char *value, size_t length)
{
    return length && length < B41_RECEIVER_PROPERTY_MAX && !value[length] &&
        !memchr(value, 0, length);
}

int b41_receiver_properties_collect(struct b41_receiver_property_owner *owner)
{
    static const char *const keys[] = {"ro.build.type", "ro.debuggable"};
    char *values[2];
    int status;
    if (!owner) return -EINVAL;
    if (owner->entered) return owner->first_error ? owner->first_error : -EALREADY;
    owner->entered = 1;
    values[0] = owner->build_type;
    values[1] = owner->debuggable;
    for (unsigned i = 0; i < 2; ++i) {
        /* A broken provider must not pass by relying on the owner's initial
         * zero padding instead of writing its promised string terminator. */
        memset(values[i], 0xa5, B41_RECEIVER_PROPERTY_MAX);
        status = b41_receiver_property_read(keys[i], values[i]);
        if (status >= 0) {
            if (!status) status = -ENODATA;
            else if ((unsigned)status >= B41_RECEIVER_PROPERTY_MAX) status = -EOVERFLOW;
            else if (!valid_property(values[i], (size_t)status)) status = -EBADMSG;
        }
        if (status < 0) {
            owner->first_error = status;
            return status;
        }
        owner->lengths[i] = (size_t)status;
        ++owner->collected;
    }
    return 0;
}

int b41_receiver_policy_apply(const struct b41_second_config *base,
    const struct b41_receiver_property_owner *p,
    const struct b41_receiver_log_sources *s, struct b41_second_config *out)
{
    struct b41_startup_config fragment = {0};
    struct b41_second_config result;
    uint8_t flags;
    int status;
    if (!base || !p || !s || !out) return -EINVAL;
    if (p->first_error) return p->first_error < 0 ? p->first_error : -EPROTO;
    if (p->entered != 1 || p->collected != 2 ||
        !valid_property(p->build_type, p->lengths[0]) ||
        !valid_property(p->debuggable, p->lengths[1])) return -ENODATA;
    status = b41_startup_set_build_policy(&fragment, p->build_type, p->debuggable);
    if (status) return status;
    flags = s->log_flags_88e40;
    if (!s->secondary_policy_de3c0 && s->ap_config_init_884c4 == 1) flags &= 0xfeu;
    if (base->provenance[4] && base->bytes[4] != flags) return -ESTALE;
    for (unsigned i = 0xc8; i < 0xcc; ++i)
        if (base->provenance[i] && base->bytes[i] != fragment.second[i]) return -ESTALE;
    result = *base;
    result.bytes[4] = flags;
    result.provenance[4] = B41_RUNTIME_PROVENANCE;
    memcpy(result.bytes + 0xc8, fragment.second + 0xc8, 4);
    memset(result.provenance + 0xc8, B41_SECOND_BUILD_RESULT, 4);
    result.missing_inputs &= ~B41_SECOND_BUILD_POLICY;
    result.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_SECOND_CONFIG_SIZE; ++i)
        result.unresolved_bytes += result.provenance[i] == B41_SECOND_UNKNOWN;
    *out = result;
    return 1;
}
