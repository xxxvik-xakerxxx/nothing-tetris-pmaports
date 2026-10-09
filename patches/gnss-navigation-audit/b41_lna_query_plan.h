/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_LNA_QUERY_PLAN_H
#define B41_LNA_QUERY_PLAN_H
#include "b41_first_queries.h"

/* Selected from the audited build/driver identity, never from a DT boolean.
 * The caller must verify the pinned mnld/libMNL and matching driver profile.
 */
enum b41_lna_query_profile {
    B41_LNA_UNRESOLVED,
    B41_LNA_OWNED_METADATA_REQUIRED,
    B41_LNA_PINNED_MCUDL_DISABLED,
    B41_LNA_PINNED_METADATA_ABSENT,
};
enum b41_lna_value_origin {
    B41_LNA_VALUE_UNKNOWN,
    B41_LNA_VALUE_QUERY,
    B41_LNA_VALUE_OEM_RETAINED_ZERO,
};
/* Distinct from frozen B41_FIRST_LNA_RESULT: NOT GPIO0 / successful ioctl. */
#define B41_FIRST_OEM_LNA_ZERO_PROVENANCE 0x80u

struct b41_lna_query_snapshot {
    struct b41_first_queries queries;
    enum b41_lna_query_profile profile;
    enum b41_lna_value_origin lna_origin;
    int lna_query_status;
    uint32_t first_config_lna_word;
};

/* All profiles attempt16 for diagnostics. Only the exact known unsupported
 * branch can retain the producer-initialized zero and continue to21.
 * No retry, reset, fd lifecycle change or native engine call.
 */
int b41_queries_collect_with_lna_plan(int fd, enum b41_lna_query_profile profile,
    b41_first_query_fn query, void *context, struct b41_lna_query_snapshot *out);
int b41_first_config_from_lna_plan(const struct b41_first_inputs *semantic,
    const struct b41_lna_query_snapshot *snapshot, struct b41_first_config *out);
#endif
