/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_CAPABILITY_BRANCH_H
#define B41_CAPABILITY_BRANCH_H
#include "b41_library_association.h"
#define B41_CAPABILITY_SIZE 0xd0u
struct b41_capability_branch {
    uint8_t capability[B41_CAPABILITY_SIZE];
    uint32_t index;
    uintptr_t source;
};
/* Read ONLY the legitimate associated immutable B4.1 image, retained by its
 * loader owner and whole-file SHA gate. No library calls or global writes.
 * chip/adie/hw/sw must be actual identity query outputs, not profile booleans.
 * This bounded constructor supports exact6878 strings and identified Adies;
 * unlike OEM empty-adie wildcard it refuses unresolved identity. Real table
 * record selection supplies property branch byte at+cc, not a caller flag.
 * Output unchanged on failure. No calibration/property/default/engine gates
 * clear merely because immutable capability bytes have been recovered.
 */
int b41_capability_branch_read(const struct b41_library_association *image,
    const char *chip, const char *adie, uint32_t hw, uint32_t sw,
    struct b41_capability_branch *out);
#endif
