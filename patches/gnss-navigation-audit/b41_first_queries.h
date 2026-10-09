/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_FIRST_QUERIES_H
#define B41_FIRST_QUERIES_H
#include "b41_first_config.h"

/* Return the ioctl value or negative errno, not libc's -1/errno pair.
 * Injection is for CI fixtures; the real boundary is b41_first_ioctl().
 */
typedef int (*b41_first_query_fn)(void *context, int fd, unsigned command,
                                uint32_t *output);

struct b41_first_queries {
    unsigned present;
    int clock_flag;
    int platform_clock_selector; /* ioctl30: 0=26MHz, 1=52MHz, NOT Hz. */
    unsigned platform_clock_valid;
    uint32_t lna_pin;
    uint32_t modem_status;
    unsigned failed_command;
    int first_error;
};

/* Borrowed descriptor must already be exclusively owned by the runtime.
 * No open, close, reset, retry, registration or engine call. A failure retains
 * earlier valid results as evidence, not permission to proceed to startup.
 */
int b41_first_queries_collect(int fd, b41_first_query_fn query, void *context,
                              struct b41_first_queries *out);
int b41_first_ioctl(void *context, int fd, unsigned command, uint32_t *output);
/* Only a complete, successful query snapshot can supply builder inputs.
 * Remaining semantic inputs still come from the caller; no default promotion.
 */
int b41_first_config_from_queries(const struct b41_first_inputs *semantic,
                                  const struct b41_first_queries *queries,
                                  struct b41_first_config *out);
#endif
