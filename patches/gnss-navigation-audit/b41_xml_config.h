/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_XML_CONFIG_H
#define B41_XML_CONFIG_H
#include <stddef.h>
#include <stdint.h>
#define B41_XML_FEATURE_SIZE 0xfc4u
#define B41_XML_MAX_SIZE 65536u
#define B41_XML_MAX_FEATURES 19u
struct b41_xml_feature { uint8_t bytes[B41_XML_FEATURE_SIZE]; };
/* Actual B4.1 GET result, not engine SET. Requires exact verified vendor XML
 * bytes; no fallback, global policy mutation, fd/engine calls or retained input.
 * Returns1 (OEM root type gps) on success; negative errno on failure leaves out
 * unchanged. Disabled features are still decoded, never silently enabled.
 */
int b41_xml_config_get(const void *xml, size_t length, const char *feature,
                       struct b41_xml_feature *out);
/* One owned XML snapshot, digest and DOM for a bounded batch. Identical GET
 * semantics/order; all outputs remain untouched if any feature fails.
 */
int b41_xml_config_get_many(const void *xml, size_t length,
    const char *const *features, unsigned count, struct b41_xml_feature *out);
#endif
