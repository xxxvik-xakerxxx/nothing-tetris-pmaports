/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_XML_GLOBALS_H
#define B41_XML_GLOBALS_H
#include "b41_xml_config.h"
#define B41_XML_GLOBAL_SIZE 0x400u
#define B41_XML_GLOBAL_VADDR 0x7178b8u
#define B41_XML_GLOBAL_GOT 0x6e6660u
#define B41_XML_CHIP_GOT 0x6e6610u
#define B41_XML_CHIP_VADDR 0x6f2dacu
struct b41_xml_set_inputs { unsigned chip_present; uint32_t chip_id; };
struct b41_xml_global_patch {
    uint8_t bytes[B41_XML_GLOBAL_SIZE], written[B41_XML_GLOBAL_SIZE];
};
/* Exact pinned XML document feature order, including its four disabled entries.
 * Receipt covers global writes only; SET output/log tail and engine ordering
 * are separate contracts. Unrelated mapped bytes are never default-filled.
 */
#define B41_XML_STOCK_FEATURES 19u
struct b41_xml_stock_receipt {
    uint32_t enabled, disabled;
    uint8_t written[B41_XML_GLOBAL_SIZE];
    unsigned committed_features;
};
/* Proven SET consumers only, not serialization/PMTK transport. Input must be
 * decoded by the exact-asset GET service. Preserves unrelated current bytes.
 * Unsupported/disabled/version/range errors leave output untouched. Never
 * clears first-config XML policy or host/transport/stop gates.
 */
int b41_xml_global_plan(const struct b41_xml_feature *feature,
    const uint8_t current[B41_XML_GLOBAL_SIZE], const struct b41_xml_set_inputs *inputs,
    struct b41_xml_global_patch *out);
enum b41_xml_global_state { B41_XML_GLOBAL_EMPTY, B41_XML_GLOBAL_OWNED,
    B41_XML_GLOBAL_EXPOSED, B41_XML_GLOBAL_FAILED };
struct b41_xml_global_owner {
    enum b41_xml_global_state state;
    uint8_t *image, *global;
    size_t image_size;
    int first_error;
    unsigned applied_features;
    unsigned stock_applied;
};
/* Fresh zeroed process-lifetime owner. Real Bionic loader must provide the
 * associated ELF bytes and mapped image, retain its handle, and guarantee
 * exclusive pre-engine ownership of writable globals. This is NOT a loader.
 * Verifies exact file digest and relocated GOT target before accepting mapping.
 * Caller guarantees GOT/global spans are readable/writable in that mapping;
 * image_size is an extent, NOT proof that ELF holes are mapped.
 */
int b41_xml_global_owner_bind(struct b41_xml_global_owner *owner,
    const void *elf, size_t elf_size, void *image, size_t image_size);
/* Actual writes to owned libMNL globals after exact XML decoding and complete
 * per-feature preflight. First failure latches; no retry/reset/unload API.
 * Zero means that supported feature's global writes, NOT engine readiness.
 */
int b41_xml_global_owner_apply(struct b41_xml_global_owner *owner,
    const void *xml, size_t xml_size, const char *feature);
/* Preflight all19 exact GET/SET consumers into temporary storage, using the
 * actual associated chip global for DCB. Commit once only after every enabled
 * consumer and GOT/current-byte snapshot still matches. Failure latches and
 * changes no global/output bytes. Receipt cannot authorize engine init.
 * After stock commit no more setters are accepted; exposure remains explicit.
 */
int b41_xml_global_owner_apply_stock(struct b41_xml_global_owner *owner,
    const void *xml, size_t xml_size, struct b41_xml_stock_receipt *receipt);
/* Mark BEFORE native registration/init: further global writes are forbidden.
 * This does not authorize those calls or establish a native stop contract.
 */
int b41_xml_global_owner_expose(struct b41_xml_global_owner *owner);
#endif
