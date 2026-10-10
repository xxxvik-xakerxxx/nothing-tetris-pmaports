/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_xml_set_tail.h"
#include <errno.h>
#include <fenv.h>
#include <float.h>
#include <locale.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53, "binary64 required");
enum { SET_ROWS = 20, SET_COLUMNS = 25, SET_VALUES = SET_ROWS * SET_COLUMNS };
_Static_assert(B41_XML_FEATURE_SIZE == 0x24 + SET_VALUES * 8,
               "pinned 20x25 settings must exactly fit decoded GET storage");
_Static_assert(B41_XML_SET_WIRE_CAPACITY >= B41_XML_SET_BODY_CAPACITY + 6,
               "body, dollar, star, checksum, CRLF and NUL must fit");

static uint32_t u32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
        (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static double number(const uint8_t *p)
{
    uint64_t bits = 0;
    double value;
    for (unsigned i = 0; i < 8; ++i) bits |= (uint64_t)p[i] << (8 * i);
    memcpy(&value, &bits, sizeof(value));
    return value;
}

int b41_xml_set_serialize(const struct b41_xml_feature *f,
                         struct b41_xml_set_message *out)
{
    /* Values at4fe320: initial w25 (integer), w23 (sparse), [sp+c]
     * (include remaining counted values). These are consumer recipes, not
     * externally supplied engine-readiness/policy flags.
     */
    static const struct {
        const char *name;
        double version;
        unsigned integer, sparse, counted;
    } profiles[] = {
        {"IFB", 1, 0, 0, 1}, {"GGTO", 1, 0, 0, 1}, {"DCB", 1, 0, 1, 0},
        {"L1Only", 1, 1, 0, 1}, {"DisableSignal", 1, 1, 0, 1},
        {"GLP", 2, 1, 0, 1}, {"GnssMode", 1, 1, 0, 1},
        {"Bluesky", 1, 1, 0, 1}, {"CoTMS", 5, 1, 0, 1},
        {"SwitchTIA", 1, 1, 0, 1}, {"MDTime", 2, 1, 0, 1},
        {"Time_Source", 1, 1, 0, 1}, {"GNSSPower", 1, 0, 0, 1},
        {"OSNMA", 1, 1, 0, 1}, {"SignalConfig", 1, 1, 0, 1}
    };
    struct b41_xml_set_message result = {0};
    char body[B41_XML_SET_BODY_CAPACITY];
    unsigned selected = (unsigned)(sizeof(profiles) / sizeof(profiles[0]));
    if (!f || !out || !memchr(f->bytes, 0, 20)) return -EINVAL;
    if (!f->bytes[0x1c]) return -EACCES;
    if (f->bytes[0x1c] != 1) return -EINVAL;
    for (unsigned i = 0; i < sizeof(profiles) / sizeof(profiles[0]); ++i)
        if (!strcmp((const char *)f->bytes, profiles[i].name)) { selected = i; break; }
    if (selected == sizeof(profiles) / sizeof(profiles[0])) return -ENOTSUP;
    double version = number(f->bytes + 0x14);
    if (!isfinite(version) || version != profiles[selected].version) return -ENOTSUP;
    uint32_t remaining = u32(f->bytes + 0x20);
    /* Stock counts are1..16. OEM sxtb counter wraps above127: not generalized. */
    if (!remaining || remaining > 127) return -ERANGE;
    for (unsigned i = 0; i < SET_VALUES; ++i)
        if (!isfinite(number(f->bytes + 0x24 + i * 8))) return -ERANGE;
    const char *locale = setlocale(LC_NUMERIC, NULL);
    const struct lconv *numeric = localeconv();
    if (!locale || (strcmp(locale, "C") && strcmp(locale, "POSIX")) ||
        !numeric || !numeric->decimal_point || strcmp(numeric->decimal_point, ".") ||
        fegetround() != FE_TONEAREST) return -ENOTSUP;
    int n = snprintf(body, sizeof(body), "XML:%s,v%.2f,Cfg", (const char *)f->bytes, version);
    if (n < 0) return -EIO;
    if ((size_t)n >= sizeof(body)) return -ENOSPC;
    size_t used = (size_t)n;
    for (unsigned i = 0; i < SET_VALUES; ++i) {
        double value = number(f->bytes + 0x24 + i * 8);
        double magnitude = fabs(value);
        unsigned emit;
        if (remaining) {
            /*4fe3d8..4fe3f8: counted OR (sparse AND abs > epsilon). */
            emit = profiles[selected].counted || (profiles[selected].sparse && magnitude > 1e-8);
        } else {
            /*4fe400..4fe418: equality emits; note > versus >= distinction. */
            emit = profiles[selected].counted && magnitude >= 1e-8;
        }
        if (!emit) continue;
        n = snprintf(body + used, sizeof(body) - used,
            profiles[selected].integer ? ",%.0f" : ",%f", value);
        if (n < 0) return -EIO;
        if ((size_t)n >= sizeof(body) - used) return -ENOSPC;
        used += (size_t)n;
        ++result.emitted_settings;
        /* Zero wraps in OEM w20 after an uncounted value; avoid entering that
         * unproven path rather than hiding signed-byte wraparound semantics.
         */
        if (!remaining) return -ERANGE;
        --remaining;
    }
    unsigned checksum = 0;
    for (size_t i = 0; i < used; ++i) checksum ^= (uint8_t)body[i];
    n = snprintf((char *)result.bytes, sizeof(result.bytes), "$%s*%02X\r\n", body, checksum);
    if (n < 0) return -EIO;
    if ((size_t)n >= sizeof(result.bytes)) return -ENOSPC;
    result.length = (unsigned)n;
    *out = result;
    return 0;
}
