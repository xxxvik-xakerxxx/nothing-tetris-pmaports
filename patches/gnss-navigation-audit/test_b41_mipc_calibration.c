/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_mipc_calibration.h"
#include <assert.h>
#include <errno.h>
#include <string.h>

static unsigned fault, freed, finished, timeout, tags, calls;
static int request, response;
static uint32_t values[] = {0, 0x12345678, 0x87654321, 0xfffffffa};
static struct b41_capability_branch branch;

void SETCOM(const char *path)
{
    assert(strcmp(path, "/dev/ttyCMIPC5") == 0);
    ++calls;
}
void mipc_msg_set_timeout_once(unsigned ms)
{
    assert(ms == (timeout++ ? 5000u : 10000u));
}
int mipc_init(const char *name)
{
    assert(strcmp(name, "gnss") == 0);
    return fault == 1 ? -1 : 0;
}
void *mipc_msg_init(unsigned id, unsigned kind)
{
    assert(id == 141 && kind == 1);
    return fault == 2 ? NULL : &request;
}
int mipc_msg_sync_timeout_with_cause(void *req, void **resp)
{
    assert(req == &request);
    *resp = fault == 4 ? NULL : fault == 5 ? &request : &response;
    return fault == 3 ? -1 : 0;
}
void *mipc_msg_get_val_ptr(void *msg, unsigned tag, void *opaque)
{
    unsigned index = tag == 0 ? 0 : tag - 0x100;
    assert(msg == &response && opaque == NULL && index < 4);
    ++tags;
    /* Trylock rejects recursive competing ownership without changing output. */
    struct b41_mipc_calibration sentinel = {9, 8, 7}, copy = sentinel;
    assert(b41_mipc_calibration_collect(&branch, &copy) == -EBUSY);
    assert(memcmp(&sentinel, &copy, sizeof(copy)) == 0);
    if (fault >= 7 && index == fault - 7)
        return NULL;
    return values + index;
}
void mipc_msg_deinit(void *msg)
{
    if (msg == &response) {
        assert(freed == 0);
        freed |= 1;
    } else {
        assert(msg == &request && !(freed & 2));
        freed |= 2;
    }
}
void mipc_deinit(void) { ++finished; }

int main(void)
{
    struct b41_mipc_calibration record = {9, 8, 7}, original = record;
    branch.capability[0xcc] = 1;
    assert(b41_mipc_calibration_collect(NULL, &record) == -EINVAL);
    branch.capability[0xcc] = 0;
    assert(b41_mipc_calibration_collect(&branch, &record) == -ENOTSUP);
    assert(!calls);
    branch.capability[0xcc] = 1;
    for (fault = 0; fault <= 10; ++fault) {
        freed = finished = timeout = tags = 0;
        values[0] = fault == 6 ? 1 : 0;
        record = original;
        int rc = b41_mipc_calibration_collect(&branch, &record);
        if (!fault) {
            assert(rc == 0 && record.c0 == values[1]);
            assert(record.c1 == values[2] && record.temperature == values[3]);
            assert(tags == 4);
        } else {
            assert(rc < 0);
            assert(memcmp(&record, &original, sizeof(record)) == 0);
        }
        assert(finished == 1);
        assert(freed == (fault <= 2 && fault ? 0u :
                        fault == 4 || fault == 5 ? 2u : 3u));
    }
    struct b41_first_config partial = {0}, out, unchanged;
    memset(partial.bytes, 0xa5, sizeof(partial.bytes));
    partial.provenance[0x14] = B41_FIRST_DEFAULT_PROFILE;
    partial.missing_inputs = B41_FIRST_CALIBRATION;
    partial.xml_policy_missing = 1;
    record = (struct b41_mipc_calibration){0x12345678, 0x87654321, 42};
    assert(b41_mipc_calibration_first(&record, &partial, &out) == 1);
    assert(out.bytes[0x3c] == 0x78 && out.bytes[0x43] == 0x87);
    assert(memcmp(out.bytes + 0x44, partial.bytes + 0x44, 8) == 0);
    assert(out.provenance[0x44] == B41_FIRST_UNKNOWN);
    assert(out.missing_inputs & B41_FIRST_CALIBRATION);
    assert(out.xml_policy_missing == 1);
    unchanged = out;
    partial.missing_inputs |= B41_FIRST_PLATFORM_PROFILE;
    assert(b41_mipc_calibration_first(&record, &partial, &out) == -ENODATA);
    assert(memcmp(&out, &unchanged, sizeof(out)) == 0);
    partial.missing_inputs &= ~B41_FIRST_PLATFORM_PROFILE;
    partial.provenance[0x3c] = B41_FIRST_CLOCK_CALIBRATION;
    assert(b41_mipc_calibration_first(&record, &partial, &out) == -EEXIST);
    assert(memcmp(&out, &unchanged, sizeof(out)) == 0);
    return 0;
}
