/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_AGPS_ENDPOINT_H
#define B41_AGPS_ENDPOINT_H
#include "b41_agps_host.h"

enum b41_agps_endpoint_route {
    B41_AGPS_ENDPOINT_UNSELECTED,
    B41_AGPS_ENDPOINT_FILESYSTEM,
    B41_AGPS_ENDPOINT_ABSTRACT,
};
struct b41_agps_endpoint {
    unsigned entered;
    int first_error;
    enum b41_agps_endpoint_route route;
    struct b41_agps_owner ipc;
};
/* Pinned B4.1 mnld SHA256:
 * 285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83.
 * 39490/39540 -> 380a0: type150/152 use this AGPS IPC route, never gpsdl.
 * 380d4..38108 tests /data/agps_supl/mnl_to_agps (literal20a20).
 * 3815c..381c8: absent/directory -> abstract mtk_mnl2agps (20a3c), len15.
 * 383a4..38418: filesystem path88068, len strlen+3; pinned initial path
 * equals the stat literal. Redirected/mutated stock paths are unsupported.
 *
 * Fresh ZEROED process-lifetime endpoint; sole setup controller, before any
 * worker/callback exposure. Supervisor owns a stable, trusted local namespace
 * and the legitimate listener lifecycle. Peer name is NOT authentication.
 * One lstat, one nonblocking CLOEXEC socket/connect, existing owner_take; a
 * filesystem inode is rechecked before transfer. Unlike stock stat, symlinks,
 * nonsockets and errors other than ENOENT fail rather than select a fallback.
 * Filesystem connect replaces stock per-send sendto to fit the existing sole
 * connected-fd owner. No bind/mkdir/unlink/daemon launch, send, device/engine
 * call, delay, retry or readiness-bit mutation. No unbounded userspace loop;
 * filesystem syscalls still require the supervisor's process deadline.
 *
 * Success makes endpoint.ipc available to the existing frame/native owner;
 * zero means connected/owned only. Failure closes the private fd once and
 * closes the unused IPC owner, retaining the first error. Reentry never opens
 * another socket. Mutex/storage remain until process exit; after success use
 * existing worker quiescence/owner_stop rules, never close behind the worker.
 * AGPS_RECEIVER/config/INIT/fix gates remain unresolved.
 */
int b41_agps_endpoint_open(struct b41_agps_endpoint *endpoint);
#endif
