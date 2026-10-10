/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "b41_xml_config.h"
#include <errno.h>
#include <float.h>
#include <locale.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <libxml/parser.h>
#include <openssl/evp.h>

static int space(unsigned char ch)
{
    return ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n';
}
static int number(const char *text, locale_t locale, double *out)
{
    char *end;
    double value;
    errno = 0;
    value = strtod_l(text, &end, locale);
    if (end == text || errno || !isfinite(value))
        return -EINVAL;
    while (space((unsigned char)*end)) ++end;
    if (*end) return -EINVAL;
    *out = value;
    return 0;
}
static void double_le(uint8_t *out, double value)
{
    uint64_t bits;
    _Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
                   "B4.1 requires IEEE754 binary64");
    memcpy(&bits, &value, 8);
    for (unsigned i = 0; i < 8; ++i) out[i] = (uint8_t)(bits >> (8 * i));
}
static int named(xmlNodePtr node, const char *name)
{
    return node->type == XML_ELEMENT_NODE && !node->ns &&
           xmlStrEqual(node->name, BAD_CAST name);
}
static int feature_get(xmlNodePtr root, locale_t locale, const char *feature,
                       struct b41_xml_feature *out)
{
    struct b41_xml_feature result = {{0}};
    xmlNodePtr match = NULL;
    unsigned rows = 0, total = 0, version_seen = 0, config_seen = 0;
    size_t name_length;
    int status = -EINVAL;
    if (!feature) return -EINVAL;
    name_length = strnlen(feature, 20);
    if (!name_length || name_length >= 20) return -EINVAL;
    for (xmlNodePtr n = root->children; n; n = n->next) {
        if (!named(n, "feature")) continue;
        /* Name is the feature's leading text only, not descendant contents. */
        xmlNodePtr text = n->children;
        if (!text || text->type != XML_TEXT_NODE || !text->content) goto done;
        const char *start = (const char *)text->content;
        while (space((unsigned char)*start)) ++start;
        size_t size = strlen(start);
        while (size && space((unsigned char)start[size - 1])) --size;
        if (size == name_length && !memcmp(start, feature, size)) {
            if (match) goto done;
            match = n;
        }
    }
    if (!match) { status = -ENOENT; goto done; }
    memcpy(result.bytes, feature, name_length);
    for (xmlNodePtr n = match->children; n; n = n->next) {
        if (n->type != XML_ELEMENT_NODE) continue;
        if (named(n, "format")) continue; /* Descriptive text is not ABI state. */
        xmlChar *text = xmlNodeGetContent(n);
        if (!text) { status = -ENOMEM; goto done; }
        if (named(n, "version") || named(n, "config")) {
            double value = 0;
            int bad = number((const char *)text, locale, &value);
            if (named(n, "version")) {
                if (version_seen++) bad = -EINVAL;
                if (!bad) double_le(result.bytes + 0x14, value);
            } else {
                if (config_seen++ || (value != 0 && value != 1)) bad = -EINVAL;
                if (!bad) result.bytes[0x1c] = (uint8_t)value;
            }
            xmlFree(text);
            if (bad) goto done;
        } else if (named(n, "setting")) {
            if (rows >= 20) { xmlFree(text); goto done; }
            char *p = (char *)text;
            unsigned columns = 0;
            for (;;) {
                char *comma = strchr(p, ',');
                double value;
                if (comma) *comma = 0;
                if (columns >= 25 || number(p, locale, &value)) {
                    xmlFree(text); goto done;
                }
                double_le(result.bytes + 0x24 + rows * 200 + columns * 8, value);
                ++columns; ++total;
                if (!comma) break;
                p = comma + 1;
            }
            ++rows;
            xmlFree(text);
        } else { xmlFree(text); goto done; }
    }
    if (version_seen != 1 || config_seen != 1 || !rows) goto done;
    for (unsigned i = 0; i < 4; ++i) result.bytes[0x20 + i] = (uint8_t)(total >> (8 * i));
    *out = result;
    status = 1;
done:
    return status;
}

int b41_xml_config_get_many(const void *xml, size_t length,
    const char *const *features, unsigned count, struct b41_xml_feature *out)
{
    static const uint8_t expected_sha[32] = {
        0x70,0x18,0x75,0x1a,0x6e,0x20,0xa1,0x2f,0xb2,0x55,0xf9,0xdf,0xd5,0xf6,0xb5,0x5a,
        0x0c,0x6c,0x79,0x66,0xa8,0x7f,0x04,0x7d,0x42,0x7b,0x88,0x5b,0x62,0xf9,0xee,0x31
    };
    uint8_t digest[EVP_MAX_MD_SIZE];
    unsigned digest_length = 0;
    xmlDocPtr doc = NULL;
    locale_t locale = (locale_t)0;
    struct b41_xml_feature *results = NULL;
    void *snapshot;
    int status = -EINVAL;
    if (!xml || !features || !out || !length || length > B41_XML_MAX_SIZE ||
        !count || count > B41_XML_MAX_FEATURES) return -EINVAL;
    for (unsigned i = 0; i < count; ++i)
        if (!features[i] || !features[i][0] || strnlen(features[i], 20) >= 20) return -EINVAL;
    snapshot = malloc(length);
    if (!snapshot) return -ENOMEM;
    memcpy(snapshot, xml, length);
    if (!EVP_Digest(snapshot, length, digest, &digest_length, EVP_sha256(), NULL)) {
        status = -EIO; goto done;
    }
    if (digest_length != 32 || memcmp(digest, expected_sha, 32)) {
        status = -EBADMSG; goto done;
    }
    doc = xmlReadMemory(snapshot, (int)length, NULL, NULL,
                       XML_PARSE_NONET | XML_PARSE_NOERROR | XML_PARSE_NOWARNING);
    if (!doc || doc->intSubset || doc->extSubset) goto done;
    xmlNodePtr root = xmlDocGetRootElement(doc);
    if (!root || !named(root, "mnl_config")) goto done;
    xmlChar *type = xmlGetProp(root, BAD_CAST "type");
    int gps = type && xmlStrEqual(type, BAD_CAST "gps");
    xmlFree(type);
    if (!gps) goto done;
    locale = newlocale(LC_NUMERIC_MASK, "C", (locale_t)0);
    if (!locale) { status = -ENOMEM; goto done; }
    results = malloc(count * sizeof(*results));
    if (!results) { status = -ENOMEM; goto done; }
    for (unsigned i = 0; i < count; ++i) {
        status = feature_get(root, locale, features[i], results + i);
        if (status < 0) goto done;
    }
    memcpy(out, results, count * sizeof(*out));
    status = 1;
done:
    free(results);
    if (locale) freelocale(locale);
    if (doc) xmlFreeDoc(doc);
    free(snapshot);
    return status;
}

int b41_xml_config_get(const void *xml, size_t length, const char *feature,
                       struct b41_xml_feature *out)
{
    return b41_xml_config_get_many(xml, length, &feature, 1, out);
}
