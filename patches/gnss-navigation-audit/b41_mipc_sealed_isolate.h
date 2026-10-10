/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_MIPC_SEALED_ISOLATE_H
#define B41_MIPC_SEALED_ISOLATE_H
#include "b41_mipc_supervised_child.h"
/* Dedicated root launcher process only: prepares network/PID namespaces before
 * fork, just like the frozen isolate. Owner is already prepared with exactly
 *12 descriptors from ProbeResources.move. No INIT path or caller-selected
 * executable. Returns bind status; any attempted child bind must be followed
 * by supervisor finish/reap, including failed bind. Unreaped means retain the
 * launcher and lease, NOT exit/unload/restart. mode is only control or load.
 */
int b41_mipc_sealed_probe_spawn(struct b41_mipc_supervision *owner,
    const char *root, const char *mode);
/* Separate thirteen-FD admission with the fixed sealed XML at slot12.
 * Same load-only executable and constraints; no engine INIT or hardware grant.
 * mode remains control/load, not an operator-selected program.
 */
int b41_mipc_sealed_xml_probe_spawn(struct b41_mipc_supervision *owner,
    const char *root, const char *mode);
#endif
