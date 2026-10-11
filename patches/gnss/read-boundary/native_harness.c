/* SPDX-License-Identifier: GPL-2.0 */
/* CI-only kernel/HAL boundary mocks around extracted production functions. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <stdbool.h>

_Static_assert(sizeof(size_t) >= 8, "CI fixture requires 64-bit size_t");

#define GPS_DL_ON_LINUX 1
#define __user
#define ERESTARTSYS 512
typedef uintptr_t dma_addr_t;
typedef int wait_queue_head_t;
struct cdev { int unused; };
#include "real_types.h"

enum gps_dl_link_id_enum { GPS_DATA_LINK_ID0, GPS_DATA_LINK_ID1 };
struct gps_each_link_waitable { int unused; };
struct gps_each_link {
    struct gps_dl_dma_buf rx_dma_buf;
    struct gps_each_link_waitable waitables[1];
};
struct file { void *private_data; unsigned int f_flags; };
struct task { int pid; };
static struct task fake_current = { 7 };
#define current (&fake_current)
#define GPS_DL_WAIT_READ 0
#define GPS_DL_SPINLOCK_FOR_DMA_BUF 0
#define GPS_DL_READ_SHOW_BUF_MAX_LEN 16
#define GPS_DL_HAL_EVT_D2A_RX_HAS_DATA 1
#define GPS_DSP_ST_RESET_DONE 0
#define DRW_ENTER 0
#define DRW_RETURN 1
#define GDL_LOGXI_DRW(...) ((void)0)
#define GDL_LOGXD_DRW(...) ((void)0)
#define GDL_LOGXW_DRW(...) ((void)0)
#define GDL_LOGD(...) ((void)0)
#define GDL_LOGI(...) ((void)0)
#define GDL_LOGW(...) ((void)0)
#define ASSERT_NOT_NULL(p, ret) do { if (!(p)) return (ret); } while (0)
#define ASSERT_NOT_ZERO(p, ret) ASSERT_NOT_NULL(p, ret)

static struct gps_each_link link_state;
static unsigned char ring[8192];
static unsigned int gets, records, copies, irq_waits, poll_first, poll_second;
static unsigned int lock_depth, dma_locks, events, no_data_retries;
static unsigned int copy_residual;
static bool invalid_link;
static bool invalidate_reader_on_second_lock;
static enum GDL_RET_STATUS wait_result, first_result, second_result;
static unsigned int last_copy, last_enter;

static void queue_data(unsigned int read_index, unsigned int length)
{
    struct gps_dl_dma_buf *dma = &link_state.rx_dma_buf;
    assert(length < sizeof(ring));
    memset(dma, 0, sizeof(*dma));
    dma->len = sizeof(ring);
    dma->dir = GDL_DMA_D2A;
    dma->vir_addr = ring;
    dma->read_index = read_index;
    dma->write_index = (read_index + length) % sizeof(ring);
    dma->entry_l = 2;
    dma->entry_w = length ? 1 : 0;
    dma->data_entries[0] = (struct gdl_dma_buf_entry) {
        .vir_addr = ring, .read_index = read_index,
        .write_index = dma->write_index, .buf_length = sizeof(ring),
        .is_valid = true, .is_nodata = true
    };
}

static void reset_case(void)
{
    for (unsigned int i = 0; i < sizeof(ring); i++)
        ring[i] = (unsigned char)(i % 251);
    memset(&link_state, 0, sizeof(link_state));
    queue_data(0, 0);
    gets = records = copies = irq_waits = poll_first = poll_second = 0;
    lock_depth = dma_locks = events = no_data_retries = 0;
    copy_residual = last_copy = last_enter = 0;
    invalid_link = false;
    invalidate_reader_on_second_lock = false;
    wait_result = first_result = second_result = GDL_OKAY;
}

static struct gps_each_link *gps_dl_link_get(enum gps_dl_link_id_enum id)
{
    assert(id == GPS_DATA_LINK_ID0);
    gets++;
    return invalid_link ? NULL : &link_state;
}

static void gps_dl_dma_buf_lock_take(struct gps_dl_dma_buf *dma, int type)
{
    (void)type;
    assert(lock_depth++ == 0);
    dma_locks++;
    /* Simulate ownership invalidation before locked rollback, without
     * replacing the real completion API or its returned STATE_MISMATCH. */
    if (invalidate_reader_on_second_lock && dma_locks == 2)
        dma->reader_working = false;
}

static void gps_dl_dma_buf_lock_give(struct gps_dl_dma_buf *dma, int type)
{
    (void)dma; (void)type;
    assert(lock_depth-- == 1);
}

static void gps_each_link_spin_lock_take(enum gps_dl_link_id_enum id, int type)
{
    (void)id; (void)type;
    assert(lock_depth++ == 0);
}

static void gps_each_link_spin_lock_give(enum gps_dl_link_id_enum id, int type)
{
    (void)id; (void)type;
    assert(lock_depth-- == 1);
}

static void gps_dl_hal_event_send(int event, enum gps_dl_link_id_enum id)
{
    (void)id;
    assert(event == GPS_DL_HAL_EVT_D2A_RX_HAS_DATA && lock_depth == 0);
    events++;
}

static void gps_dma_buf_memcpy_from_rx(void *dst, const void *src, unsigned int len)
{
    assert(lock_depth == 0);
    memcpy(dst, src, len);
}

static int gps_dsp_state_get(enum gps_dl_link_id_enum id)
{
    (void)id;
    return GPS_DSP_ST_RESET_DONE;
}

static void gps_each_link_rec_read(enum gps_dl_link_id_enum id, int pid, int len, int phase)
{
    (void)id; (void)pid;
    if (phase == DRW_ENTER)
        last_enter = (unsigned int)len;
    records++;
}

static int copy_to_user(void *dst, const void *src, unsigned int len)
{
    assert(lock_depth == 0);
    copies++;
    last_copy = len;
    if (!copy_residual)
        memcpy(dst, src, len);
    return (int)copy_residual;
}

static void gps_dl_hal_show_buf(const char *label, unsigned char *buf, unsigned int len)
{
    (void)label; (void)buf; (void)len;
}

static const char *gdl_ret_to_name(enum GDL_RET_STATUS status)
{
    (void)status;
    return "mock";
}

static void after_wait(void)
{
    if (no_data_retries)
        no_data_retries--;
    else
        queue_data(0, 16);
}

#if GPS_DL_NO_USE_IRQ == 0
static enum GDL_RET_STATUS gps_dl_link_wait_on(struct gps_each_link_waitable *p, long *sig)
{
    (void)p; (void)sig;
    assert(lock_depth == 0);
    assert(++irq_waits <= 8); /* A missing zero-timeout guard must fail, never hang. */
    if (wait_result == GDL_OKAY)
        after_wait();
    return wait_result;
}
#else
static enum GDL_RET_STATUS gps_dl_hal_wait_and_handle_until_usrt_has_data(
    enum gps_dl_link_id_enum id, int timeout)
{
    (void)id; (void)timeout;
    assert(++poll_first <= 8 && lock_depth == 0);
    return first_result;
}

static enum GDL_RET_STATUS gps_dl_hal_wait_and_handle_until_usrt_has_nodata_or_rx_dma_done(
    enum gps_dl_link_id_enum id, int timeout, bool handle)
{
    (void)id; (void)timeout;
    assert(handle && ++poll_second <= 8 && lock_depth == 0);
    if (second_result == GDL_OKAY)
        after_wait();
    return second_result;
}
#endif

#include "real_source.c"

static void check_payload(const unsigned char *out, unsigned int read_index, unsigned int length)
{
    for (unsigned int i = 0; i < length; i++)
        assert(out[i] == ring[(read_index + i) % sizeof(ring)]);
}

int main(void)
{
    struct gps_each_device dev;
    struct file file = { .private_data = &dev, .f_flags = O_NONBLOCK };
    unsigned char out[GPS_DATA_PATH_BUF_MAX + 16];
    char *user_out = (char *)out;
    const size_t counts[] = { sizeof(dev.i_buf), sizeof(dev.i_buf) + 1,
        UINT32_MAX, (size_t)UINT32_MAX + 1, SIZE_MAX };
    memset(&dev, 0, sizeof(dev));

    for (unsigned int flags = 0; flags < 2; flags++) {
        reset_case();
        file.f_flags = flags ? O_NONBLOCK : 0;
        assert(gps_each_device_read(&file, NULL, 0, NULL) == 0);
        assert(!gets && !copies && !records && !dma_locks);
    }
    file.f_flags = O_NONBLOCK;
    reset_case();
    assert(gps_each_device_read(&file, user_out, sizeof(out), NULL) == -EAGAIN);
    assert(!irq_waits && !poll_first && !poll_second && !copies);
    assert(dma_locks == 1 && !link_state.rx_dma_buf.reader_working);

    for (size_t n = 0; n < sizeof(counts) / sizeof(counts[0]); n++) {
        reset_case();
        queue_data(0, sizeof(dev.i_buf));
        memset(out, 0xa5, sizeof(out));
        memset(dev.o_buf, 0x5a, sizeof(dev.o_buf));
        assert(gps_each_device_read(&file, user_out, counts[n], NULL) == (int)sizeof(dev.i_buf));
        assert(last_enter == sizeof(dev.i_buf) && last_copy == sizeof(dev.i_buf));
        check_payload(out, 0, sizeof(dev.i_buf));
        for (unsigned int i = sizeof(dev.i_buf); i < sizeof(out); i++)
            assert(out[i] == 0xa5);
        for (unsigned int i = 0; i < sizeof(dev.o_buf); i++)
            assert(dev.o_buf[i] == 0x5a);
        assert(!irq_waits && !poll_first && !poll_second && !lock_depth);
    }

    for (unsigned int wrap = 0; wrap < 2; wrap++) {
        reset_case();
        unsigned int start = wrap ? sizeof(ring) - 7 : 20;
        queue_data(start, 16);
        link_state.rx_dma_buf.has_pending_rx = true;
        assert(gps_each_device_read(&file, user_out, 512, NULL) == 16);
        check_payload(out, start, 16);
        assert(events == 1 && !link_state.rx_dma_buf.has_pending_rx);
        assert(!link_state.rx_dma_buf.reader_working && !lock_depth);
    }

    reset_case();
    queue_data(0, 1);
    assert(gps_each_device_read(&file, user_out, 1, NULL) == 1);
    reset_case();
    invalid_link = true;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -EINVAL);
    assert(!copies && !irq_waits && !poll_first);
    reset_case();
    link_state.rx_dma_buf.reader_working = true;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -EFAULT);
    assert(!copies && !irq_waits && !poll_first);
    reset_case();
    link_state.rx_dma_buf.write_index = 1; /* Data with no entry. */
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -EFAULT);
    assert(!copies && !link_state.rx_dma_buf.reader_working);
    reset_case();
    queue_data(0, 16);
    copy_residual = 1;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -EFAULT);
    assert(copies == 1 && link_state.rx_dma_buf.read_index == 16);

    /* Failed short reads release ownership and preserve the queued entry. */
    for (unsigned int flags = 0; flags < 2; flags++) {
        for (unsigned int wrap = 0; wrap < 2; wrap++) {
            struct gps_dl_dma_buf before;
            unsigned int start = wrap ? sizeof(ring) - 7 : 20;
            reset_case();
            file.f_flags = flags ? O_NONBLOCK : 0;
            queue_data(start, 16);
            link_state.rx_dma_buf.has_pending_rx = true;
            memcpy(&before, &link_state.rx_dma_buf, sizeof(before));
            memset(out, 0xa5, sizeof(out));
            assert(gps_each_device_read(&file, user_out, 1, NULL) == -EFAULT);
            assert(!link_state.rx_dma_buf.reader_working && !copies && !lock_depth);
            assert(dma_locks == 2 && !events && !irq_waits && !poll_first && !poll_second);
            assert(memcmp(&before, &link_state.rx_dma_buf, sizeof(before)) == 0);
            for (unsigned int i = 0; i < sizeof(out); i++)
                assert(out[i] == 0xa5);
            assert(gps_each_device_read(&file, user_out, 512, NULL) == 16);
            check_payload(out, start, 16);
            assert(!link_state.rx_dma_buf.reader_working && events == 1);
            assert(link_state.rx_dma_buf.read_index == (start + 16) % sizeof(ring));
        }
    }
    file.f_flags = O_NONBLOCK;

    /* Preserve the copy error even when locked cleanup reports a mismatch. */
    for (unsigned int invalidated = 0; invalidated < 2; invalidated++) {
        struct gps_dl_dma_buf before;
        unsigned int length = 99;
        bool nodata = false;
        reset_case();
        queue_data(0, 16);
        memcpy(&before, &link_state.rx_dma_buf, sizeof(before));
        invalidate_reader_on_second_lock = invalidated;
        assert(gdl_dma_buf_get(&link_state.rx_dma_buf, out, 1, &length, &nodata) == GDL_FAIL_NOSPACE);
        assert(length == 0 && !nodata && dma_locks == 2 && !lock_depth);
        assert(memcmp(&before, &link_state.rx_dma_buf, sizeof(before)) == 0);
        invalidate_reader_on_second_lock = false;
        assert(gdl_dma_buf_get(&link_state.rx_dma_buf, out, 512, &length, &nodata) == GDL_OKAY);
        assert(length == 16 && nodata && !link_state.rx_dma_buf.reader_working);
        check_payload(out, 0, 16);
    }

    /* Acquisition failures must not release a different reader's ownership. */
    reset_case();
    link_state.rx_dma_buf.reader_working = true;
    unsigned int length = 99;
    assert(gdl_dma_buf_get(&link_state.rx_dma_buf, out, 512, &length, NULL) == GDL_FAIL_BUSY);
    assert(link_state.rx_dma_buf.reader_working && dma_locks == 1 && length == 99);
    reset_case();
    assert(gdl_dma_buf_get(&link_state.rx_dma_buf, out, 512, &length, NULL) == GDL_FAIL_NODATA);
    assert(!link_state.rx_dma_buf.reader_working && dma_locks == 1 && length == 99);
    reset_case();
    link_state.rx_dma_buf.write_index = 1;
    assert(gdl_dma_buf_get(&link_state.rx_dma_buf, out, 512, &length, NULL) == GDL_FAIL_NOENTRY);
    assert(!link_state.rx_dma_buf.reader_working && dma_locks == 1 && length == 99);
    reset_case();
    assert(gdl_dma_buf_get(&link_state.rx_dma_buf, NULL, 512, &length, NULL) == GDL_FAIL_ASSERT);
    assert(!dma_locks && !link_state.rx_dma_buf.reader_working);

    /* Clamp must not permit oversized DMA entries to overwrite o_buf. */
    reset_case();
    queue_data(0, sizeof(dev.i_buf) + 1);
    struct gps_dl_dma_buf oversized_before;
    memcpy(&oversized_before, &link_state.rx_dma_buf, sizeof(oversized_before));
    memset(dev.o_buf, 0x5a, sizeof(dev.o_buf));
    assert(gps_each_device_read(&file, user_out, SIZE_MAX, NULL) == -EFAULT);
    assert(!link_state.rx_dma_buf.reader_working && dma_locks == 2 && !copies);
    assert(memcmp(&oversized_before, &link_state.rx_dma_buf, sizeof(oversized_before)) == 0);
    for (unsigned int i = 0; i < sizeof(dev.o_buf); i++)
        assert(dev.o_buf[i] == 0x5a);
    /* Device reads remain clamped; a larger direct DMA buffer can recover. */
    assert(gps_each_device_read(&file, user_out, SIZE_MAX, NULL) == -EFAULT);
    assert(!link_state.rx_dma_buf.reader_working && dma_locks == 4);
    assert(memcmp(&oversized_before, &link_state.rx_dma_buf, sizeof(oversized_before)) == 0);
    memset(out, 0xa5, sizeof(out));
    assert(gdl_dma_buf_get(&link_state.rx_dma_buf, out, sizeof(out), &length, NULL) == GDL_OKAY);
    assert(length == sizeof(dev.i_buf) + 1 && !link_state.rx_dma_buf.reader_working);
    assert(link_state.rx_dma_buf.read_index == length);
    check_payload(out, 0, length);
    for (unsigned int i = length; i < sizeof(out); i++)
        assert(out[i] == 0xa5);

    /* Blocking retries and finite-timeout behavior retain the vendor contract. */
    reset_case();
    file.f_flags = 0;
    no_data_retries = 2;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == 16);
#if GPS_DL_NO_USE_IRQ == 0
    assert(irq_waits == 3 && !poll_first && !poll_second);
    reset_case();
    wait_result = GDL_FAIL_SIGNALED;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -ERESTARTSYS);
    reset_case();
    wait_result = GDL_FAIL_NOT_SUPPORT;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -EFAULT);
    reset_case();
    assert(gps_each_link_read_with_timeout(GPS_DATA_LINK_ID0, out, 512, 1, NULL) == 16);
    assert(irq_waits == 1); /* No finite IRQ deadline is implemented. */
#else
    assert(!irq_waits && poll_first == 3 && poll_second == 3);
    reset_case();
    first_result = GDL_FAIL_TIMEOUT;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -EAGAIN);
    assert(poll_first == 1 && !poll_second);
    reset_case();
    second_result = GDL_FAIL_TIMEOUT;
    assert(gps_each_device_read(&file, user_out, 512, NULL) == -EAGAIN);
    assert(poll_first == 1 && poll_second == 1);
#endif
    assert(!lock_depth);
    puts("PASS: real GPS read/DMA functions, boundary and error paths");
    return 0;
}
