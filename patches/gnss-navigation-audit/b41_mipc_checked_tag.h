/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MIPC_CHECKED_TAG_H
#define B41_MIPC_CHECKED_TAG_H
#include <stdint.h>
/* B4.1 aecc3444... accessor writes a uint16 length through argument3.
 * Caller exclusively owns the live response, with no concurrent mutation or
 * deinit. Returned bytes are borrowed from response's allocated hashmap node.
 * This check fixes the OEM consumer's missing word-size check, not bugs inside
 * the vendor deserializer. No unload/reinit is authorized by this operation.
 * Only calibration/status tags accepted; output unchanged on rejection.
 */
int b41_mipc_checked_tag_word(void *response, unsigned tag, uint32_t *out);
#endif
