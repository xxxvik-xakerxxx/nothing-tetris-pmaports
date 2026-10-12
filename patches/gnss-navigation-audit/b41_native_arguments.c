/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_native_arguments.h"
#include "b41_slot6_service.h"
#include <errno.h>
#include <string.h>
#include <unistd.h>

unsigned b41_native_arguments_config_missing(const struct b41_startup_bundle *b)
{
    unsigned missing;
    if (!b) return ~0u;
    missing = b->missing_contracts & ~(B41_MISSING_HOST_SERVICES |
        B41_MISSING_TRANSPORT_OWNER | B41_MISSING_STOP_CONTRACT);
    missing |= B41_MISSING_SECOND_POLICY | B41_MISSING_AGPS_RECEIVER;
    if (b->runtime.first.missing_inputs || b->runtime.first.unresolved_bytes ||
        b->runtime.first.xml_policy_missing) missing |= B41_MISSING_FIRST_CONFIG;
    for (unsigned i = 0; i < B41_FIRST_CONFIG_SIZE; ++i)
        if (!b->runtime.first.provenance[i]) missing |= B41_MISSING_FIRST_CONFIG;
    return missing;
}

#if defined(__aarch64__) && defined(__BIONIC__)
static uint32_t word(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
        (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
/* Same source preconditions as the frozen session: nonoffload and unused
 * native table. No thread marker is written; actual ACK is deferred to stop.
 */
static int stop_profile(const struct b41_library_association *image)
{
    uintptr_t flag;
    uint32_t offload;
    struct b41_native_thread_record record;
    memcpy(&flag, (const void *)(image->base + 0x6e6d00u), sizeof(flag));
    if (flag != image->base + 0x6fa3d8u) return -ESTALE;
    memcpy(&offload, (const void *)flag, sizeof(offload));
    if (offload) return -EOPNOTSUPP;
    for (unsigned i = 0; i < B41_NATIVE_THREADS; ++i) {
        memcpy(&record, (const void *)(image->base + 0x6edef0u + 32u*i), sizeof(record));
        if (record.marker != -1 || record.handle != UINT64_MAX || record.index != i ||
            record.stop != image->base + 0x529f18u ||
            record.wake != image->base + 0x529418u) return -EALREADY;
    }
    return 0;
}
#endif

int b41_native_arguments_prepare(struct b41_native_arguments_owner *o,
    const struct b41_startup_bundle *b,
    const void *elf, size_t elf_size, const struct b41_library_view *view,
    struct b41_agps_owner *ipc, int fds[2], unsigned count, int *app, int *raw,
    pid_t peer_pid, uid_t peer_uid)
{
#if !defined(__aarch64__) || !defined(__BIONIC__)
    (void)o; (void)b; (void)elf; (void)elf_size; (void)view;
    (void)ipc; (void)fds; (void)count; (void)app; (void)raw;
    (void)peer_pid; (void)peer_uid;
    return -EOPNOTSUPP;
#else
    struct b41_known_callbacks callbacks;
    struct b41_library_association image;
    struct b41_gpsdl_identity devices;
    struct b41_engine_arguments arguments;
    int status;
    if (!o || !b || !ipc || !fds || !app || !raw || count < 1 || count > 2)
        return -EINVAL;
    if (o->entered) return -EALREADY;
    if (!ipc->initialized || ipc->state != B41_AGPS_OWNED) return -ENODATA;
    if (peer_pid <= 0) return -EINVAL;
    /* Reject stale fd snapshots BEFORE binding or transferring anything. */
    if (word(b->second.bytes + 0x10) != (uint32_t)fds[0] ||
        word(b->second.bytes + 0x14) != (count == 2 ? (uint32_t)fds[1] : 0u))
        return -ESTALE;
    for (unsigned i = 0x10; i < 0x18; ++i)
        if (!b->second.provenance[i]) return -ENODATA;
    for (unsigned i = 0x10; i < 0x14; ++i)
        if (b->second.provenance[i] != B41_SECOND_RECEIVER_FD) return -ENODATA;
    for (unsigned i = 0x14; i < 0x18; ++i)
        if (b->second.provenance[i] != (count == 2 ? B41_SECOND_RECEIVER_FD :
            B41_SECOND_INACTIVE_SECONDARY)) return -ENODATA;
    for (unsigned i = 0x68; i < 0x6c; ++i)
        if (!b->runtime.first.provenance[i] || b->runtime.first.bytes[i])
            return -EOPNOTSUPP;
    if (memcmp(b->second.bytes + 0x1cc, "UseCallback", 11) || b->second.bytes[0x1d7])
        return -EOPNOTSUPP;
    status = b41_library_associate(elf, elf_size, view, &image);
    if (status) return status;
    status = stop_profile(&image);
    if (status) return status;
    status = b41_gpsdl_identity_snapshot(fds[0], count == 2 ? fds[1] : -1, &devices);
    if (status) return status;
    if (*app == ipc->fd || *raw == ipc->fd || *app == fds[0] || *raw == fds[0] ||
        (count == 2 && (*app == fds[1] || *raw == fds[1]))) return -EINVAL;

    o->entered = 1;
    o->image = image;
    o->devices = devices;
    status = b41_agps_receiver_open(&o->agps, peer_pid, peer_uid);
    if (status) goto fail;
    status = b41_agps_receiver_prepare(&o->agps, elf, elf_size, view);
    if (status < 0) goto fail;
    if (o->agps.image.base != image.base || o->agps.image.extent != image.extent ||
        o->agps.image.xml_global != image.xml_global ||
        o->agps.image.chip_global != image.chip_global) { status = -ESTALE; goto fail; }
    status = b41_host_adapter_init(&o->adapter);
    if (status) goto fail;
    status = b41_host_adapter_bind(&o->adapter, &callbacks);
    if (status) goto fail;
    status = b41_native_control_init(&o->control);
    if (status) goto fail;
    status = b41_native_control_bind(&o->control, &callbacks);
    if (status) goto fail;
    status = b41_slot6_service_bind(&o->adapter, &callbacks);
    if (status) goto fail;
    status = b41_navigation_output_take(&o->output, app, raw);
    if (status) goto fail;
    status = b41_navigation_output_bind(&o->output);
    if (status) goto fail;
    status = b41_engine_arguments_build(b, &callbacks, &arguments);
    if (status < 0) goto fail;
    o->worker.dispatch = b41_slot6_service_dispatch;
    status = b41_frame_worker_start(&o->worker, &o->adapter, ipc, fds, count);
    if (status) goto fail;
    status = b41_frame_worker_expose(&o->worker);
    if (status) goto fail;
    /* Only THIS producer removes its own fulfilled requirements, after actual
     * binding, device identity, fd move and running output worker. Never accept
     * caller-clearable readiness bits. Keep all config and AGPS source gates.
     * STOP means supported supervised lifecycle, not an already-observed ACK.
     */
    arguments.missing_contracts = b41_native_arguments_config_missing(b);
    o->arguments = arguments;
    return 1;
fail:
    o->first_error = status;
    return status;
#endif
}

int b41_native_arguments_execute(struct b41_native_arguments_owner *o,
    const struct timespec *run, const struct timespec *worker,
    struct b41_native_session_result *result)
{
    int status;
    if (!o || !o->entered) return -EINVAL;
    if (o->first_error) return o->first_error;
#if defined(__aarch64__) && defined(__BIONIC__)
    if (o->agps.controller_pid != getpid() ||
        !pthread_equal(o->agps.controller, pthread_self())) return -EPERM;
#endif
    if (!result) return -EINVAL;
    if (o->executed) return -EALREADY;
    o->executed = 1;
    memset(result, 0, sizeof(*result));
    status = b41_native_session_execute(&o->image, &o->arguments, &o->control,
        &o->worker, &o->stop, &o->agps, run, worker, result);
#if defined(__aarch64__) && defined(__BIONIC__)
    /* Session admission may refuse before entering registration. Its parked
     * reverse worker still belongs to this owner and must be stopped once. */
    if (!result->agps_quiesce_entered &&
        (o->agps.state == B41_AGPS_RX_PREPARED || o->agps.state == B41_AGPS_RX_RUNNING)) {
        result->agps_quiesce_entered = 1;
        result->agps_quiesce_status = b41_agps_receiver_quiesce(&o->agps, worker);
        result->native_stop_status = -ECANCELED;
        result->worker_stop_status = -EBUSY;
        if (!status) status = result->agps_quiesce_status;
    }
#endif
    if (status && !o->first_error) o->first_error = status;
    return status;
}
