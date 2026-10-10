/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_xml_globals.h"
#include <errno.h>
#include <float.h>
#include <fenv.h>
#include <limits.h>
#include <math.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 &&
    sizeof(float) == 4 && FLT_MANT_DIG == 24, "IEEE binary64/binary32 required");
static uint64_t le(const uint8_t *p, unsigned n)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < n; ++i) value |= (uint64_t)p[i] << (8 * i);
    return value;
}
static double number(const struct b41_xml_feature *f, unsigned offset)
{
    uint64_t bits = le(f->bytes + offset, 8);
    double value;
    memcpy(&value, &bits, 8);
    return value;
}
static void put(struct b41_xml_global_patch *p, unsigned offset, uint64_t value, unsigned n)
{
    for (unsigned i = 0; i < n; ++i) {
        p->bytes[offset + i] = (uint8_t)(value >> (8 * i));
        p->written[offset + i] = 1;
    }
}
static void flags(struct b41_xml_global_patch *p, uint32_t bit)
{
    put(p, 8, (uint32_t)le(p->bytes + 8, 4) | bit, 4);
}
int b41_xml_global_plan(const struct b41_xml_feature *f,
    const uint8_t current[B41_XML_GLOBAL_SIZE], const struct b41_xml_set_inputs *inputs,
    struct b41_xml_global_patch *out)
{
    struct b41_xml_global_patch p = {0};
    double values[14], version;
    int32_t integers[14];
    unsigned count = 0;
    if (!f || !current || !out) return -EINVAL;
    if (!memchr(f->bytes, 0, 20)) return -EINVAL;
    if (!f->bytes[0x1c]) return -EACCES;
    const char *name = (const char *)f->bytes;
    if (!strcmp(name, "CoTMS")) count = 4;
    else if (!strcmp(name, "MDTime") || !strcmp(name, "GGTO") || !strcmp(name, "GNSSPower")) count = 4;
    else if (!strcmp(name, "Time_Source")) count = 2;
    else if (!strcmp(name, "IFB")) count = 14;
    else if (!strcmp(name, "DCB") || !strcmp(name, "OSNMA")) count = 1;
    else if (!strcmp(name, "SwitchTIA") || !strcmp(name, "GLP") ||
        !strcmp(name, "GnssMode") || !strcmp(name, "L1Only") ||
        !strcmp(name, "DisableSignal") || !strcmp(name, "Bluesky") ||
        !strcmp(name, "SignalConfig")) count = 1;
    else return -EOPNOTSUPP;
    version = number(f, 0x14);
    if (!isfinite(version)) return -ERANGE;
    /* Missing CoTMS fourth setting is proven zero-filled GET storage, not a
     * caller default. Stock count3 is accepted ONLY through exact XML GET.
     */
    if (le(f->bytes + 0x20, 4) < count && !(count == 4 && !strcmp(name, "CoTMS") &&
        le(f->bytes + 0x20, 4) == 3 && number(f, 0x3c) == 0)) return -ENODATA;
    for (unsigned i = 0; i < count; ++i) {
        values[i] = number(f, 0x24 + 8 * i);
        if (!isfinite(values[i]) || values[i] < INT32_MIN || values[i] > INT32_MAX)
            return -ERANGE; /* Do not emulate undefined C casts or guessed FCVT saturation. */
        integers[i] = (int32_t)values[i];
    }
    memcpy(p.bytes, current, sizeof(p.bytes));
    if (!strcmp(name, "DCB")) {
        if (version != 1) return -EPROTONOSUPPORT;
        if (!inputs || !inputs->chip_present) return -ENODATA;
        /* Do not adopt OEM unmatched-chip fallback calibration as universal. */
        if (inputs->chip_id != 6637 && inputs->chip_id != 6686) return -ENODEV;
        unsigned row = inputs->chip_id == 6637 ? 0 : 3;
        if (le(f->bytes + 0x20, 4) != 16 ||
            number(f, 0x24 + (row + 2) * 200) != inputs->chip_id) return -ENODATA;
        for (unsigned i = 0; i < 4; ++i) {
            double value = number(f, 0x24 + row * 200 + 8 * i);
            if (!isfinite(value)) return -ERANGE;
            put(&p, 0x198 + 16 * i, le(f->bytes + 0x24 + row * 200 + 8 * i, 8), 8);
        }
        for (unsigned i = 0; i < 3; ++i) {
            double value = number(f, 0x24 + (row + 1) * 200 + 8 * i);
            if (!isfinite(value)) return -ERANGE;
            put(&p, 0x1a0 + 16 * i, le(f->bytes + 0x24 + (row + 1) * 200 + 8 * i, 8), 8);
        }
    } else if (!strcmp(name, "OSNMA")) {
        if (version != 1 || (uint32_t)integers[0] > 2 || le(f->bytes + 0x20, 4) != 1)
            return -EOPNOTSUPP;
        /* Stock has NO second-row policy. The actual branch writes version/
         * option then skips the optional key/config loop when row1[1] is zero.
         */
        if (number(f, 0xf4) != 0) return -EOPNOTSUPP;
        float value = (float)version; uint32_t bits;
        memcpy(&bits, &value, 4); put(&p, 0x374, bits, 4);
        put(&p, 0x378, (uint32_t)integers[0], 1);
    } else if (!strcmp(name, "CoTMS")) {
        put(&p, 0xd, (uint32_t)integers[0], 1);
        put(&p, 0x10, (uint32_t)integers[1], 2);
        put(&p, 0x16, (uint32_t)integers[2], 2);
        put(&p, 0xc, integers[3] == 1, 1);
        if (version >= 4.4) put(&p, 0x14, 1, 2);
        put(&p, 0x12, 1, 2);
    } else if (!strcmp(name, "MDTime")) {
        if (values[3] < 0) return -ERANGE;
        int32_t interval = values[1] < 1 ? 1 : integers[1];
        int32_t window = interval * 0.5 < values[2] ? interval / 2 : integers[2];
        put(&p, 0x2c0, le(f->bytes + 0x14, 8), 8);
        put(&p, 0x2cb, (uint32_t)integers[0], 1);
        put(&p, 0x2cc, (uint32_t)interval, 2);
        put(&p, 0x2ce, (uint32_t)window, 2);
        put(&p, 0x2d0, (uint32_t)integers[3], 4); flags(&p, 0x40);
    } else if (!strcmp(name, "Time_Source")) {
        put(&p, 0x2d4, (uint32_t)integers[0], 1);
        put(&p, 0x2d5, (uint32_t)integers[1], 1);
        put(&p, 0x2d6, ((uint32_t)integers[1] & 255) | (((uint32_t)integers[0] & 255) << 8), 2);
    } else if (!strcmp(name, "IFB") || !strcmp(name, "GGTO")) {
        if (!strcmp(name, "GGTO") && version != 1) return -EPROTONOSUPPORT;
        unsigned offset = !strcmp(name, "IFB") ? 0x1e0 : 0x300;
        for (unsigned i = 0; i < count; ++i) put(&p, offset + 8 * i, le(f->bytes + 0x24 + 8 * i, 8), 8);
    } else if (!strcmp(name, "GNSSPower")) {
        if (version != 1) return -EPROTONOSUPPORT;
        if (fegetround() != FE_TONEAREST) return -EOPNOTSUPP;
        for (unsigned i = 0; i < count; ++i) {
            float value = (float)values[i]; uint32_t bits;
            memcpy(&bits, &value, 4); put(&p, 0x348 + 4 * i, bits, 4);
        }
    } else {
        unsigned offset, bit = 0;
        if (!strcmp(name, "SwitchTIA")) offset = 0xe;
        else if (!strcmp(name, "GLP")) { offset = 0x45; bit = 1; }
        else if (!strcmp(name, "GnssMode")) { offset = 0x358; bit = 4; }
        else if (!strcmp(name, "L1Only")) {
            if (!integers[0]) return -ERANGE;
            offset = 0x2ac;
        } else if (!strcmp(name, "Bluesky")) offset = 0x2b6;
        else if (!strcmp(name, "DisableSignal")) {
            if (version != 1 || (uint32_t)integers[0] > 31) return -ERANGE;
            offset = 0x324;
        } else {
            if (version != 1 || integers[0] < 0) return -ERANGE;
            if (le(f->bytes + 0x20, 4) != 1) return -EOPNOTSUPP;
            for (unsigned i = 1; i < 6; ++i)
                if (number(f, 0x24 + 8 * i) != 0) return -ENODATA;
            put(&p, 0x35c, (uint32_t)integers[0], 4);
            for (unsigned i = 1; i < 6; ++i) put(&p, 0x35c + 4 * i, 0, 4);
            *out = p; return 0;
        }
        put(&p, offset, (uint32_t)integers[0], 1);
        if (bit) flags(&p, bit);
    }
    *out = p;
    return 0;
}
static int fail(struct b41_xml_global_owner *o, int error)
{
    if (!o->first_error) o->first_error = error;
    o->state = B41_XML_GLOBAL_FAILED;
    return o->first_error;
}
int b41_xml_global_owner_bind(struct b41_xml_global_owner *o,
    const void *elf, size_t size, void *image, size_t extent)
{
    static const uint8_t expected[32] = {
        0x3b,0x35,0x01,0xd4,0x60,0x31,0xfb,0x22,0xcf,0x39,0x9f,0x34,0x95,0x21,0x1a,0x3d,
        0x22,0x02,0xac,0xd0,0x4d,0xf4,0x89,0xfa,0x82,0x7e,0x38,0x38,0x52,0xce,0xff,0x90 };
    uint8_t digest[32]; unsigned written = 0; uintptr_t target;
    if (!o || !elf || !size || !image) return -EINVAL;
    if (o->state != B41_XML_GLOBAL_EMPTY) return -EALREADY;
    if (sizeof(uintptr_t) != 8 || extent < B41_XML_GLOBAL_VADDR + B41_XML_GLOBAL_SIZE ||
        (uintptr_t)image > UINTPTR_MAX - extent) return -ERANGE;
    if (!EVP_Digest(elf, size, digest, &written, EVP_sha256(), NULL) || written != 32)
        return -EIO;
    if (memcmp(digest, expected, 32)) return -EKEYREJECTED;
    memcpy(&target, (uint8_t *)image + B41_XML_GLOBAL_GOT, 8);
    if (target != (uintptr_t)image + B41_XML_GLOBAL_VADDR) return -ESTALE;
    uint8_t *global = (uint8_t *)target;
    memcpy(&target, (uint8_t *)image + B41_XML_CHIP_GOT, 8);
    if (target != (uintptr_t)image + B41_XML_CHIP_VADDR) return -ESTALE;
    o->image = image; o->image_size = extent; o->global = global;
    o->state = B41_XML_GLOBAL_OWNED;
    return 0;
}
int b41_xml_global_owner_apply(struct b41_xml_global_owner *o,
    const void *xml, size_t size, const char *name)
{
    struct b41_xml_feature feature;
    struct b41_xml_global_patch patch;
    uintptr_t target;
    if (!o) return -EINVAL;
    if (o->state == B41_XML_GLOBAL_FAILED) return o->first_error;
    if (o->state != B41_XML_GLOBAL_OWNED) return -EPERM;
    if (o->stock_applied) return -EALREADY;
    memcpy(&target, o->image + B41_XML_GLOBAL_GOT, 8);
    if (target != (uintptr_t)o->global) return fail(o, -ESTALE);
    int status = b41_xml_config_get(xml, size, name, &feature);
    if (status < 0) return fail(o, status);
    struct b41_xml_set_inputs inputs = {0};
    if (name && !strcmp(name, "DCB")) {
        memcpy(&target, o->image + B41_XML_CHIP_GOT, 8);
        if (target != (uintptr_t)o->image + B41_XML_CHIP_VADDR) return fail(o, -ESTALE);
        inputs.chip_present = 1;
        inputs.chip_id = (uint32_t)le((const uint8_t *)target, 4);
    }
    status = b41_xml_global_plan(&feature, o->global, &inputs, &patch);
    if (status) return fail(o, status);
    for (unsigned i = 0; i < B41_XML_GLOBAL_SIZE; ++i)
        if (patch.written[i]) o->global[i] = patch.bytes[i];
    ++o->applied_features;
    return 0;
}
int b41_xml_global_owner_apply_stock(struct b41_xml_global_owner *o,
    const void *xml, size_t size, struct b41_xml_stock_receipt *out)
{
    static const char *const names[B41_XML_STOCK_FEATURES] = {
        "IFB", "GGTO", "DCB", "L1Only", "L5Test", "DisableSignal", "GLP", "CAIC",
        "GnssMode", "Bluesky", "CoTMS", "SwitchTIA", "Blanking", "MDTime",
        "Time_Source", "PSO", "GNSSPower", "OSNMA", "SignalConfig"
    };
    struct b41_xml_stock_receipt result = {0};
    struct b41_xml_feature *features;
    struct b41_xml_global_patch plan;
    struct b41_xml_set_inputs inputs = {0};
    uint8_t before[B41_XML_GLOBAL_SIZE], pending[B41_XML_GLOBAL_SIZE];
    uintptr_t target;
    if (!o || !out) return -EINVAL;
    if (o->state == B41_XML_GLOBAL_FAILED) return o->first_error;
    if (o->state != B41_XML_GLOBAL_OWNED) return -EPERM;
    if (o->stock_applied) return -EALREADY;
    memcpy(&target, o->image + B41_XML_GLOBAL_GOT, 8);
    if (target != (uintptr_t)o->global) return fail(o, -ESTALE);
    memcpy(&target, o->image + B41_XML_CHIP_GOT, 8);
    if (target != (uintptr_t)o->image + B41_XML_CHIP_VADDR) return fail(o, -ESTALE);
    inputs.chip_present = 1;
    inputs.chip_id = (uint32_t)le((const uint8_t *)target, 4);
    memcpy(before, o->global, sizeof(before));
    memcpy(pending, before, sizeof(pending));
    features = malloc(B41_XML_STOCK_FEATURES * sizeof(*features));
    if (!features) return fail(o, -ENOMEM);
    int status = b41_xml_config_get_many(xml, size, names, B41_XML_STOCK_FEATURES, features);
    if (status < 0) { free(features); return fail(o, status); }
    for (unsigned i = 0; i < B41_XML_STOCK_FEATURES; ++i) {
        if (!features[i].bytes[0x1c]) {
            result.disabled |= 1u << i;
            continue;
        }
        status = b41_xml_global_plan(features + i, pending, &inputs, &plan);
        if (status) { free(features); return fail(o, status); }
        memcpy(pending, plan.bytes, sizeof(pending));
        for (unsigned byte = 0; byte < B41_XML_GLOBAL_SIZE; ++byte)
            result.written[byte] |= plan.written[byte];
        result.enabled |= 1u << i;
        ++result.committed_features;
    }
    free(features);
    memcpy(&target, o->image + B41_XML_GLOBAL_GOT, 8);
    if (target != (uintptr_t)o->global || memcmp(before, o->global, sizeof(before)))
        return fail(o, -ESTALE);
    memcpy(&target, o->image + B41_XML_CHIP_GOT, 8);
    if (target != (uintptr_t)o->image + B41_XML_CHIP_VADDR ||
        le((const uint8_t *)target, 4) != inputs.chip_id) return fail(o, -ESTALE);
    for (unsigned i = 0; i < B41_XML_GLOBAL_SIZE; ++i)
        if (result.written[i]) o->global[i] = pending[i];
    o->stock_applied = 1;
    o->applied_features += result.committed_features;
    *out = result;
    return 0;
}
int b41_xml_global_owner_expose(struct b41_xml_global_owner *o)
{
    if (!o || o->state != B41_XML_GLOBAL_OWNED) return -EPERM;
    o->state = B41_XML_GLOBAL_EXPOSED;
    return 0;
}
