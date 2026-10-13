/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MVCD_BOOTSTRAP_FIELDS_H
#define B41_MVCD_BOOTSTRAP_FIELDS_H

#include <stddef.h>
#include <stdint.h>

enum b41_mvcd_fields_result {
    B41_MVCD_FIELDS_OK = 0,
    B41_MVCD_FIELDS_ARGUMENT = -10,
    B41_MVCD_FIELDS_MISSING = -11,
    B41_MVCD_FIELDS_FORMAT = -12
};

/* Exact eight-byte records from the retained configuration at 8ca018.
 * Supply both real records for FE mode, including checksum-invalid records.
 * NULL means acquisition is missing, never evidence of absent overrides.
 */
struct b41_mvcd_private_clock {
    uint8_t frequency_1670[8];
    uint8_t adjustment_1668[8];
};

/* Values from one legitimate first/retained 112-byte context and its live
 * selector owner. These inputs do not certify acquisition or session ownership.
 * No ADIE, PMIC selector or platform-name substitution is valid here.
 */
struct b41_mvcd_bootstrap_inputs {
    uint8_t context_mode_13;
    uint32_t context_hz_18;
    uint32_t context_baud_1c;
    uint8_t context_profile_24;
    uint32_t context_chip_30;
    uint32_t context_lna_54;
    uint8_t clock_selector_717cb3;
    uint8_t profile_selector_717cb6;
    uint8_t setting_717cb7;
    uint8_t feature_flags_717cb8;
    uint32_t word_7178b0;
    /* 5211a4: __strlen_chk(75c99c+1ae, 0x296) and secondary fd6edeec != -1.
     * Snapshot must include its NUL within the 662-byte object boundary.
     */
    const uint8_t *feature_name;
    size_t feature_name_size;
    int32_t secondary_fd_6edeec;
    const struct b41_mvcd_private_clock *private_clock;
};

struct b41_mvcd_bootstrap_fields {
    uint8_t baud_and_parameters[6]; /* payload4..9 */
    uint8_t synthesis_and_profile[32]; /* payload30..61 */
    uint8_t board_tail[12]; /* payload94..105 */
    uint32_t effective_hz;
    uint8_t clock_mode;
    /* Stock writes 27 to717cb7 when profile_selector >=5. */
    uint8_t effective_setting_717cb7;
};

/* Pure producers only. Clock errors retain their B41_MVCD_CLOCK_* values.
 * All output is unchanged on failure. No native DSO, query or transport call.
 */
int b41_mvcd_bootstrap_fields_build(const struct b41_mvcd_bootstrap_inputs *in,
                                   struct b41_mvcd_bootstrap_fields *out);

/* Write only the 50 produced bytes into an existing exact106-byte payload.
 * Leaves subtype, sequence, ROM-session metadata and other bytes untouched.
 * Success is field construction, never a complete/authentic bootstrap claim.
 */
int b41_mvcd_bootstrap_fields_apply(const struct b41_mvcd_bootstrap_inputs *in,
                                   uint8_t *payload, size_t payload_size);

#endif
