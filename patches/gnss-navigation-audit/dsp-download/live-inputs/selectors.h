/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_BOOTSTRAP_SELECTOR_PRODUCERS_H
#define B41_BOOTSTRAP_SELECTOR_PRODUCERS_H

#include "../../b41_capability_branch.h"
#include "../bootstrap.h"
#include "../download.h"
#include "../../b41_first_config.h"

struct b41_bootstrap_chip {
    struct b41_capability_branch capability;
    uint32_t context_chip_30;
    uint32_t capabilities;
    uint32_t navigation_mode_base;
    uint8_t profile_selector_717cb6;
    /* B3 reset default, before XML bit7/SET policy and engine changes. */
    uint8_t secure_download_default;
};

/* Uses the existing exact capability matcher with acquired platform identities.
 * No ADIE-to-chip mapping, marketing-name selection, or vendor function call.
 */
int b41_bootstrap_chip_read(const struct b41_library_association *image,
    const char *chip, const char *adie, uint32_t hw, uint32_t sw,
    struct b41_bootstrap_chip *out);

struct b41_bootstrap_mode {
    uint8_t mode_75c990;
    uint8_t setting_717cb7;
    uint8_t flags_717cb8;
    uint8_t clock_717cb3;
};

/* Pure 5ccaa0 producer. Inputs are the actual context+38/+30 and table profile.
 * Modes10/11 require the retained secondary name and actual descriptor. Other
 * modes do not evaluate that predicate. No generic feature-success boolean.
 * Returns owned software mode/config, not firmware readiness. An OEM replay
 * must additionally account for its later policy; a standalone native owner
 * may intentionally select this mode without running an OEM engine.
 * Input mode is truncated to a byte exactly as stock does.
 */
int b41_bootstrap_mode_build(uint32_t context_mode_38,
    uint32_t context_chip_30, uint8_t profile_selector_717cb6,
    const uint8_t *secondary_name, size_t name_size, int32_t secondary_fd,
    struct b41_bootstrap_mode *out);

struct b41_bootstrap_observation {
    struct b41_bootstrap_selectors route;
    uint8_t clock_selector_717cb3;
    uint8_t profile_selector_717cb6;
    uint8_t setting_717cb7;
    uint8_t feature_flags_717cb8;
    uint32_t word_7178b0;
};

/* Read actual associated globals, not caller-set bytes. The loader must retain
 * its SHA-pinned image and readable GOT/global spans under exclusive engine
 * ownership. Extent validation does not prove mapped holes are readable.
 * Two matching reads detect observed changes, not atomicity or stage arrival.
 * Optional OEM comparison only. It is not an input gate for the standalone
 * native owner. An OEM-stage comparison must schedule at its real consumer.
 * This API does not initialize an engine or establish hardware readiness.
 */
int b41_bootstrap_observe(const struct b41_library_association *image,
    struct b41_bootstrap_observation *out);

/* Intentional native policy: primary L1/MVCD, GPS mode3, secondary disabled,
 * nominal physical26MHz with no OEM private frequency/adjustment correction.
 * FE/COTMS remains the physical clock marker, not a calibration certificate.
 */
struct b41_native_l1_nominal {
    struct b41_mvcd_bootstrap_inputs inputs;
    struct b41_mvcd_bootstrap_fields fields;
    struct b41_bootstrap_selectors selectors;
    struct b41_bootstrap_mode navigation;
};

struct b41_native_l1_identity {
    uint32_t hardware_chip, gps_adie;
    uint32_t context_chip_30, capabilities, navigation_mode_base;
    uint8_t profile_selector_717cb6, secure_download_default;
};
/* Immutable identity-specific table policy. Revision-independent matching is
 * intentional (51b3b0..51b414); no disabled revision query or fake query0.
 * Only actual conninfra chip and GPS ADIE results are accepted. No DSO needed.
 */
int b41_native_l1_identity_select(uint32_t hardware_chip, uint32_t gps_adie,
    struct b41_native_l1_identity *out);

/* Requires the source-selected identity policy and acquired first-context frequency,
 * profile, baud, FE marker and LNA value. Only the supported MT6878, 26MHz
 * COTMS route is implemented. ioctl results are real signed syscall results;
 * errors propagate, conflicting/unsupported clocks fail. No MNL globals or
 * private records are needed. Unrelated unresolved first-config bytes remain
 * outside this download-only constructor. Output is unchanged on failure.
 */
int b41_native_l1_nominal_build(const struct b41_native_l1_identity *chip,
    const struct b41_first_config *first, int clock_ioctl11, int clock_ioctl30,
    struct b41_native_l1_nominal *out);

/* Uses the documented106/116-byte grammar with the explicitly resolved native
 * fields above, not the OEM private-override field helper. Session->fields must
 * point to &policy->inputs and its selectors must match policy->selectors.
 * Query must be a real successful ioctl23 on that same exclusively owned gps0
 * lifetime, with its full20-byte metadata kept private. No readiness token,
 * metadata/default key fabrication, transport, engine or hardware operation.
 */
int b41_native_l1_nominal_payload_build(const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session,
    const struct b41_bootstrap_query *query, uint8_t *payload, size_t capacity);
int b41_native_l1_nominal_frame_build(const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session,
    const struct b41_bootstrap_query *query, uint8_t *frame, size_t capacity,
    size_t *written);

/* Begin the existing bounded ACK/fragment controller with native nominal
 * assembly. Continue with b41_download_linux_step; its real TX/RX, integer
 * ioctl25, sequence checks and absolute deadline remain unchanged.
 */
int b41_native_l1_download_begin(struct b41_download *owner,
    const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session, const struct b41_bootstrap_query *query,
    uint64_t now_ns, uint64_t deadline_ns);
int b41_native_l1_download_linux_begin(struct b41_download *owner,
    const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session, uint64_t deadline_ns);


#endif
