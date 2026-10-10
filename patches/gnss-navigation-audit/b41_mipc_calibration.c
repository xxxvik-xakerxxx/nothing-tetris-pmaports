/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_mipc_calibration.h"
#include <errno.h>
#include <pthread.h>
#include <string.h>

/* Machine-level signatures recovered from mnld7f440..7f8a8. Return values of
 * SETCOM/timeout/deinit are unused by OEM: do not invent success contracts.
 * get_val_ptr's third parameter is deliberately opaque and ALWAYS NULL as in
 * the producer. No unsupported claim that it returns a length is made here.
 * libmipc must supply its own valid four-byte tag values until msg_deinit.
 */
extern void SETCOM(const char *);
extern void mipc_msg_set_timeout_once(unsigned);
extern int mipc_init(const char *);
extern void *mipc_msg_init(unsigned, unsigned);
extern int mipc_msg_sync_timeout_with_cause(void *, void **);
extern void *mipc_msg_get_val_ptr(void *, unsigned, void *);
extern void mipc_msg_deinit(void *);
extern void mipc_deinit(void);

static pthread_mutex_t owner = PTHREAD_MUTEX_INITIALIZER;

static int tag_word(void *message, unsigned tag, uint32_t *out)
{
    const void *value = mipc_msg_get_val_ptr(message, tag, NULL);
    if (!value)
        return -ENODATA;
    /* OEM consumes ldr w at7f63c/678/718/760. memcpy avoids alignment UB. */
    memcpy(out, value, sizeof(*out));
    return 0;
}

int b41_mipc_calibration_collect(const struct b41_capability_branch *branch,
    struct b41_mipc_calibration *out)
{
    struct b41_mipc_calibration result;
    void *request = NULL, *response = NULL;
    uint32_t status;
    int error;
#ifndef __BIONIC__
    int old_cancel;
#endif
    if (!branch || !out)
        return -EINVAL;
    if (branch->capability[0xcc] != 1)
        return -ENOTSUP;
    error = pthread_mutex_trylock(&owner);
    if (error)
        return -error;
#ifndef __BIONIC__
    /* Bionic has no pthread cancellation API. Native libc callers disable it
     * while the process-global OEM owner and request/response are retained.
     */
    error = pthread_setcancelstate(PTHREAD_CANCEL_DISABLE, &old_cancel);
    if (error) {
        pthread_mutex_unlock(&owner);
        return -error;
    }
#endif
    SETCOM("/dev/ttyCMIPC5");
    mipc_msg_set_timeout_once(10000);
    error = -ENOTCONN;
    if (mipc_init("gnss") != 0)
        goto cleanup;
    request = mipc_msg_init(141, 1);
    if (!request) {
        error = -ENOMEM;
        goto cleanup;
    }
    mipc_msg_set_timeout_once(5000);
    error = -EREMOTEIO;
    if (mipc_msg_sync_timeout_with_cause(request, &response) != 0)
        goto cleanup;
    error = -EPROTO;
    /* Aliasing would make OEM double-deinit unsafe; reject and free once. */
    if (!response || response == request)
        goto cleanup;
    error = tag_word(response, 0, &status);
    if (error)
        goto cleanup;
    if (status != 0) {
        error = -EREMOTEIO;
        goto cleanup;
    }
    error = tag_word(response, 0x101, &result.c0);
    if (!error)
        error = tag_word(response, 0x102, &result.c1);
    if (!error)
        error = tag_word(response, 0x103, &result.temperature);
cleanup:
    if (response && response != request)
        mipc_msg_deinit(response);
    if (request)
        mipc_msg_deinit(request);
    /* OEM also deinitializes after mipc_init failure (7f6b4). */
    mipc_deinit();
    if (!error)
        *out = result;
    pthread_mutex_unlock(&owner);
#ifndef __BIONIC__
    pthread_setcancelstate(old_cancel, NULL);
#endif
    return error;
}

static void word(uint8_t *out, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i)
        out[i] = (uint8_t)(value >> (8 * i));
}

int b41_mipc_calibration_first(const struct b41_mipc_calibration *record,
    const struct b41_first_config *partial, struct b41_first_config *out)
{
    struct b41_first_config result;
    if (!record || !partial || !out)
        return -EINVAL;
    if (partial->missing_inputs & B41_FIRST_PLATFORM_PROFILE)
        return -ENODATA;
    /* Existing constructor only marks this field for producer de22c==0. */
    if (partial->provenance[0x14] != B41_FIRST_DEFAULT_PROFILE)
        return -ENOTSUP;
    result = *partial;
    /* Never overwrite independently established, conflicting calibration. */
    uint8_t bytes[8];
    word(bytes, record->c0);
    word(bytes + 4, record->c1);
    for (unsigned i = 0; i < 8; ++i) {
        unsigned p = result.provenance[0x3c + i];
        if (p != B41_FIRST_UNKNOWN &&
            (p != B41_FIRST_CLOCK_CALIBRATION ||
             result.bytes[0x3c + i] != bytes[i]))
            return -EEXIST;
    }
    memcpy(result.bytes + 0x3c, bytes, sizeof(bytes));
    memset(result.provenance + 0x3c, B41_FIRST_CLOCK_CALIBRATION, 8);
    result.unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i)
        result.unresolved_bytes += result.provenance[i] == B41_FIRST_UNKNOWN;
    for (unsigned i = 0x3c; i < 0x4c; ++i)
        if (result.provenance[i] != B41_FIRST_CLOCK_CALIBRATION)
            result.missing_inputs |= B41_FIRST_CALIBRATION;
    *out = result;
    return 1;
}
