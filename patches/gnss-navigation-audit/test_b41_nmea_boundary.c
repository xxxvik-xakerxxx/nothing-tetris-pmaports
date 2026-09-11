#include "b41_nmea_boundary.h"
#include <assert.h>
#include <stdio.h>

int main(void)
{
    uintptr_t slots[24];
    unsigned char dst[8], src[] = {'$', 'G', 'N', 0, 'x'};
    size_t used;
    for (unsigned i = 0; i < 24; ++i)
        slots[i] = i + 1;
    assert(b41_registration_preflight(slots, 24) == 0);
    for (unsigned i = 0; i < 24; ++i) {
        uintptr_t saved = slots[i];
        slots[i] = 0;
        assert(b41_registration_preflight(slots, 24) ==
               ((i < 10 && (0x3fb & (1u << i))) ? -1 : 0));
        slots[i] = saved;
    }
    assert(b41_registration_preflight(NULL, 24) == -1);
    assert(b41_registration_preflight(slots, 23) == -1);
    assert(b41_registration_preflight(slots, 25) == -1);
    memset(dst, 0xa5, sizeof(dst));
    assert(b41_capture_output(dst, sizeof(dst), src, sizeof(src), &used) == 0);
    assert(used == sizeof(src) && !memcmp(dst, src, used) && dst[5] == 0xa5);
    src[1] = 'X';
    assert(dst[1] == 'G');
    assert(b41_capture_output(dst, 4, src, 5, &used) == -1 && used == 0);
    assert(dst[1] == 'G');
    assert(b41_capture_output(dst, 8, NULL, 1, &used) == -1 && used == 0);
    assert(b41_capture_output(NULL, 8, src, 1, &used) == -1 && used == 0);
    assert(b41_capture_output(dst, 8, src, 0, &used) == -1 && used == 0);
    assert(b41_capture_output(dst, 8, src, UINT32_MAX, &used) == -1 && used == 0);
    assert(b41_capture_output(dst, 8, src, 1, NULL) == -1);
    puts("PASS: registration preflight and bounded borrowed-output copy");
    return 0;
}
