/* SPDX-License-Identifier: GPL-2.0-only */
#include "b41_gpsdl_identity.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(void)
{
    struct b41_gpsdl_identity out, original;
    memset(&out, 0xa5, sizeof(out)); memcpy(&original, &out, sizeof(out));
    int p[2]; assert(!pipe(p));
    assert(b41_gpsdl_identity_snapshot(p[0], -1, &out) == -ENODEV);
    assert(!memcmp(&out, &original, sizeof(out)));
    assert(b41_gpsdl_identity_snapshot(p[0], p[0], &out) == -EINVAL);
    assert(!memcmp(&out, &original, sizeof(out)));
    int ro = open("/dev/null", O_RDONLY); assert(ro >= 0);
    assert(b41_gpsdl_identity_snapshot(ro, -1, &out) == -EACCES);
    assert(!memcmp(&out, &original, sizeof(out)));
    assert(b41_gpsdl_identity_snapshot(INT_MAX, -1, &out) == -EBADF);
    assert(!memcmp(&out, &original, sizeof(out)));
    assert(!close(p[0]) && !close(p[1]) && !close(ro));
    puts("B41 gpsdl identity: wrong transport/read mode/alias and unchanged output pass; GPS success not simulated");
    return 0;
}
