/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_SECOND_NUMERIC_H
#define B41_SECOND_NUMERIC_H
#include "b41_second_config.h"
struct b41_second_numeric_sources {
    uint32_t requested_dfff4, requested_dfff8;
    uint32_t float_bits_de4bc;
};
/* Exact63828..638c4 numeric/string producers, not inferred defaults. Inputs
 * must come from the legitimate requested-buffer/float producer owner. Does
 * not allocate the buffers or prove their ownership/size. Writes8+30 bytes;
 * preserves unrelated data/provenance, recounts unresolved bytes. Returns1
 * partial, no SECOND_POLICY/engine/AGPS gate clearing. Error leaves out intact.
 */
int b41_second_numeric_apply(const struct b41_second_config *base,
    const struct b41_second_numeric_sources *sources, struct b41_second_config *out);
#endif
