/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include "gpsdl_v051_session.h"
#include "real_types.h"

#define __user
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define ASSERT_LINK_ID(id, value) do { if ((unsigned)(id) >= GPS_DATA_LINK_NUM) return (value); } while (0)
enum { GPS_DL_SPINLOCK_FOR_LINK_STATE };
struct gps_each_device { int index; bool is_open; };
struct gps_each_link { int session_id; enum gps_each_link_state_enum state_for_user; };
static struct gps_each_device dev;
static struct gps_each_link link;
static enum gps_dsp_state_t g_gps_dsp_state[GPS_DATA_LINK_NUM];
static unsigned locks, unlocks, copies;
static int no_link, change_dsp, lose_open, copy_fault;
static struct gpsdl_v051_session_snapshot copied;

static struct gps_each_link *gps_dl_link_get(enum gps_dl_link_id_enum id)
{
    assert(id == GPS_DATA_LINK_ID0 || id == GPS_DATA_LINK_ID1);
    return no_link ? NULL : &link;
}
static void gps_each_link_spin_lock_take(enum gps_dl_link_id_enum id, int kind)
{
    assert((int)id == dev.index && kind == GPS_DL_SPINLOCK_FOR_LINK_STATE);
    locks++;
}
static void gps_each_link_spin_lock_give(enum gps_dl_link_id_enum id, int kind)
{
    assert((int)id == dev.index && kind == GPS_DL_SPINLOCK_FOR_LINK_STATE);
    unlocks++;
    if (change_dsp) g_gps_dsp_state[id] = GPS_DSP_ST_RESET_DONE;
    if (lose_open) dev.is_open = false;
}
static unsigned long copy_to_user(void *destination, const void *source, size_t size)
{
    assert(destination == &copied && size == sizeof(copied));
    copies++;
    if (copy_fault) return 1;
    memcpy(destination, source, size);
    return 0;
}
#include "real_source.c"

int main(void)
{
    _Static_assert(sizeof(copied) == 32, "fixed ABI");
    _Static_assert(offsetof(struct gpsdl_v051_session_snapshot, dsp_state) == 20, "DSP offset");
    _Static_assert(GPSDL_V051_IOC_SESSION_SNAPSHOT == 31U, "no assert ioctl12");
    dev.index = 0; dev.is_open = true;
    link.session_id = 123; link.state_for_user = LINK_OPENED;
    g_gps_dsp_state[0] = GPS_DSP_ST_WORKING;
    assert(gps_each_device_session_snapshot(&dev, (unsigned long)&copied) == 0);
    assert(copied.abi_version == 1 && copied.size == 32 && copied.session_id == 123);
    assert(copied.link_id == 0 && copied.link_state == LINK_OPENED && copied.dsp_state == GPS_DSP_ST_WORKING);
    assert(!copied.reserved[0] && !copied.reserved[1] && locks == 1 && unlocks == 1 && copies == 1);
    assert(gps_each_device_session_snapshot(NULL, 1) == -ENODEV);
    assert(gps_each_device_session_snapshot(&dev, 0) == -EINVAL);
    dev.index = -1;
    assert(gps_each_device_session_snapshot(&dev, 1) == -ENODEV);
    dev.index = GPS_DATA_LINK_NUM;
    assert(gps_each_device_session_snapshot(&dev, 1) == -ENODEV);
    dev.index = 0; dev.is_open = false;
    assert(gps_each_device_session_snapshot(&dev, 1) == -ENOTCONN);
    dev.is_open = true; no_link = 1;
    assert(gps_each_device_session_snapshot(&dev, 1) == -ENODEV);
    no_link = 0; change_dsp = 1;
    assert(gps_each_device_session_snapshot(&dev, 1) == -EAGAIN);
    assert(copies == 1);
    change_dsp = 0; lose_open = 1;
    assert(gps_each_device_session_snapshot(&dev, 1) == -ENOTCONN);
    assert(copies == 1);
    lose_open = 0; dev.is_open = true; copy_fault = 1;
    assert(gps_each_device_session_snapshot(&dev, (unsigned long)&copied) == -EFAULT);
    assert(copies == 2 && locks == unlocks);
    assert(gps_dsp_state_snapshot(GPS_DATA_LINK_NUM) == GPS_DSP_ST_MAX);
    return 0;
}
