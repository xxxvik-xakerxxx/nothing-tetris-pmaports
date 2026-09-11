#include "b41_frame_sync.h"
#include <assert.h>

static void vector(unsigned slot, uint32_t value)
{
    unsigned char out[32];
    size_t used;
    memset(out, 0xa5, sizeof(out));
    assert(b41_frame_sync_encode(slot, value, out, sizeof(out), &used) == 0);
    assert(used > 0 && out[used - 1] == '\r' && out[used] == 0xa5);
    for (size_t i = 0; i < used; ++i)
        printf("%02x", out[i]);
    putchar('\n');
    assert(b41_frame_sync_encode(slot, value, out, used, &used) == 0);
}

int main(void)
{
    unsigned char out[32];
    size_t used = 99;
    for (unsigned i = 0; i < 256; ++i)
        vector(3, i);
    vector(3, 256);
    vector(3, 257);
    vector(3, UINT32_MAX);
    vector(4, 0);
    vector(4, 1);
    vector(4, UINT32_MAX);
    memset(out, 0xa5, sizeof(out));
    assert(b41_frame_sync_encode(3, 1, out, 1, &used) == -1 && used == 0);
    assert(out[0] == 0xa5);
    assert(b41_frame_sync_encode(2, 1, out, 32, &used) == -1 && used == 0);
    assert(b41_frame_sync_encode(3, 1, NULL, 32, &used) == -1 && used == 0);
    assert(b41_frame_sync_encode(3, 1, out, 32, NULL) == -1);
    return 0;
}
