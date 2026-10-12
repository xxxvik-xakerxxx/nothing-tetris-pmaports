/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MVCD_CLOCK_H
#define B41_MVCD_CLOCK_H

#include <stdint.h>

enum b41_mvcd_clock_result {
    B41_MVCD_CLOCK_OK = 0,
    B41_MVCD_CLOCK_ARGUMENT = -1,
    B41_MVCD_CLOCK_ENVIRONMENT = -2,
    B41_MVCD_CLOCK_RANGE = -3
};

struct b41_mvcd_clock_fields {
    uint16_t parameter_a;
    uint16_t parameter_b;
    uint8_t synthesis[28];
};

/* Explicit effective frequency AFTER any validated stock frequency override.
 * mode is the independently produced w28 at4f2130, not ioctl11's raw flag.
 * This is the L1 secondary=0 call only; it constructs no profile or DSO state.
 */
int b41_mvcd_clock_synthesize(uint32_t effective_hz, uint8_t mode,
                              struct b41_mvcd_clock_fields *out);

/* 574f04: nearest signed integer, exact halves towards positive infinity. */
int b41_mvcd_clock_round(double value, int64_t *out);

#endif
