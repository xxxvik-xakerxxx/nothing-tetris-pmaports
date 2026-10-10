/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_XML_SET_TAIL_H
#define B41_XML_SET_TAIL_H
#include "../b41_xml_config.h"
#define B41_XML_SET_BODY_CAPACITY 1024u
#define B41_XML_SET_WIRE_CAPACITY 1030u
#define B41_XML_SET_KIND 1u
#define B41_XML_SET_CATEGORY 5u
#define B41_XML_SET_LEVEL 0u
struct b41_xml_set_message {
    unsigned length, emitted_settings;
    uint8_t bytes[B41_XML_SET_WIRE_CAPACITY];
};
/* Pure bounded reproduction of the pinned SET diagnostic tail, not a setter.
 * Requires exact-asset GET output from b41_xml_config_get. Supports the15
 * enabled B4.1 stock profiles; never authenticates input or selects calibration.
 * Does not write globals, change policy, log, dispatch, or authorize INIT.
 * Caller owns C/POSIX numeric locale and nearest rounding, with no concurrent
 * locale changes. Refuses overflow instead of reproducing OEM truncation/OOB.
 * Success produces category5/level0/kind1 bytes; length excludes trailing NUL.
 * Input is borrowed synchronously. Error leaves the output untouched.
 */
int b41_xml_set_serialize(const struct b41_xml_feature *feature,
                         struct b41_xml_set_message *output);
#endif
