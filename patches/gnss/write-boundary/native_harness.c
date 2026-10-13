/* SPDX-License-Identifier: GPL-2.0 */
/* CI-only kernel/HAL mocks; TX device/link/DMA bodies are actual sources. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>

_Static_assert(sizeof(size_t) >= 8, "requires 64-bit size_t");
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
    struct gps_dl_dma_buf tx_dma_buf;
    struct gps_each_link_waitable waitables[1];
};
struct file { void *private_data; unsigned int f_flags; };
struct task { int pid; };
static struct task task = { 7 };
#define current (&task)
#define GPS_DL_WAIT_WRITE 0
#define GPS_DL_SPINLOCK_FOR_DMA_BUF 0
#define GPS_DL_EVT_LINK_WRITE 1
#define GPS_DL_HAL_EVT_A2D_TX_DMA_DONE 2
#define GPS_DSP_ST_RESET_DONE 0
#define LINK_OPENED 1
#define GPS_DL_READ_SHOW_BUF_MAX_LEN 32
#define DRW_ENTER 0
#define DRW_RETURN 1
#define GDL_LOGXI_DRW(...) ((void)0)
#define GDL_LOGXD_DRW(...) ((void)0)
#define GDL_LOGXW_DRW(...) ((void)0)
#define GDL_LOGXD(...) ((void)0)
#define GDL_LOGXW(...) ((void)0)
#define GDL_LOGD(...) ((void)0)
#define GDL_LOGI(...) ((void)0)
#define GDL_LOGW(...) ((void)0)
#define ASSERT_NOT_NULL(p, ret) do { if (!(p)) return (ret); } while (0)
#define ASSERT_NOT_ZERO(p, ret) ASSERT_NOT_NULL(p, ret)

static struct gps_each_link link;
static unsigned char ring[8192];
static unsigned int gets, records, copies, dma_locks, lock_depth, waits;
static unsigned int events, polls, completions, shows, state_checks, dsp_checks;
static unsigned int last_copy, last_enter, copy_residual, retry_count, drain_steps;
static bool invalid_link, closed_link, byte_mode;
static enum GDL_RET_STATUS wait_result;

static void reset_case(void)
{
    memset(&link, 0, sizeof(link));
    memset(ring, 0xa5, sizeof(ring));
    link.tx_dma_buf.len = sizeof(ring);
    link.tx_dma_buf.vir_addr = ring;
    link.tx_dma_buf.dir = GDL_DMA_A2D;
    link.tx_dma_buf.entry_l = 4;
    gets = records = copies = dma_locks = lock_depth = waits = 0;
    events = polls = completions = shows = state_checks = dsp_checks = 0;
    last_copy = last_enter = copy_residual = retry_count = 0;
    drain_steps = 1;
    invalid_link = closed_link = false;
    byte_mode = true;
    wait_result = GDL_OKAY;
}

static struct gps_each_link *gps_dl_link_get(enum gps_dl_link_id_enum id)
{
    assert(id == GPS_DATA_LINK_ID0);
    gets++;
    return invalid_link ? NULL : &link;
}

static int gps_each_link_get_state(enum gps_dl_link_id_enum id)
{
    (void)id;
    state_checks++;
    return closed_link ? 0 : LINK_OPENED;
}

static int gps_dsp_state_get(enum gps_dl_link_id_enum id)
{
    (void)id;
    dsp_checks++;
    return GPS_DSP_ST_RESET_DONE;
}

static void gps_each_link_rec_write(enum gps_dl_link_id_enum id, int pid, int len, int phase)
{
    (void)id; (void)pid;
    if (phase == DRW_ENTER)
        last_enter = (unsigned int)len;
    records++;
}

static void gps_dl_dma_buf_lock_take(struct gps_dl_dma_buf *dma, int type)
{
    (void)dma; (void)type;
    assert(lock_depth++ == 0);
    dma_locks++;
}

static void gps_dl_dma_buf_lock_give(struct gps_dl_dma_buf *dma, int type)
{
    (void)dma; (void)type;
    assert(lock_depth-- == 1);
}

static bool gps_dl_is_1byte_mode(void) { return byte_mode; }

static void gps_dma_buf_memcpy_to_tx(void *dst, const void *src, unsigned int len)
{
    assert(!lock_depth);
    memcpy(dst, src, len);
}

static void gps_dma_buf_memset_io(void *dst, int value, unsigned int len)
{
    assert(!lock_depth);
    memset(dst, value, len);
}

static void gps_dl_link_event_send(int event, enum gps_dl_link_id_enum id)
{
    (void)id;
    assert(event == GPS_DL_EVT_LINK_WRITE && !lock_depth);
    events++;
}

static void gps_dl_hal_show_buf(const char *label, unsigned char *buf, unsigned int len)
{
    (void)label; (void)buf; (void)len;
    shows++;
}

static void gps_dma_buf_show(struct gps_dl_dma_buf *dma, bool warning)
{
    (void)dma; (void)warning;
    shows++;
}

static const char *gdl_ret_to_name(enum GDL_RET_STATUS ret)
{
    (void)ret;
    return "mock";
}

static unsigned long copy_from_user(void *dst, const void *src, unsigned long len)
{
    assert(!lock_depth);
    copies++;
    last_copy = (unsigned int)len;
    if (!copy_residual)
        memcpy(dst, src, len);
    return copy_residual;
}

static enum GDL_RET_STATUS gps_dl_link_wait_on(struct gps_each_link_waitable *p, long *sig)
{
    (void)p; (void)sig;
    assert(!lock_depth && ++waits <= 8);
    if (wait_result != GDL_FAIL_SIGNALED && !retry_count) {
        link.tx_dma_buf.writer_working = false;
        link.tx_dma_buf.read_index = link.tx_dma_buf.write_index;
        link.tx_dma_buf.entry_r = link.tx_dma_buf.entry_w;
    } else if (retry_count)
        retry_count--;
    return wait_result;
}

#if GPS_DL_NO_USE_IRQ == 1
static void gps_dl_hal_a2d_tx_dma_wait_until_done_and_stop_it(
    enum gps_dl_link_id_enum id, int timeout, bool stop)
{
    (void)id;
    assert(timeout == GPS_DL_RW_NO_TIMEOUT && !stop && !lock_depth);
    assert(++polls <= 8);
}

static void gps_dl_hal_event_send(int event, enum gps_dl_link_id_enum id)
{
    (void)id;
    assert(event == GPS_DL_HAL_EVT_A2D_TX_DMA_DONE && !lock_depth);
    completions++;
    if (--drain_steps == 0) {
        link.tx_dma_buf.read_index = link.tx_dma_buf.write_index;
        link.tx_dma_buf.entry_r = link.tx_dma_buf.entry_w;
    }
}

static bool gps_dma_buf_is_empty(struct gps_dl_dma_buf *dma)
{
    return dma->read_index == dma->write_index;
}
#endif

#include "real_source.c"
#if WRITE_BOUNDARY_ORIGINAL
/* Baseline control has no new entry. Device zero test fails before this alias. */
#define gps_each_link_write_with_options(id, buf, len, done, nb) \
    gps_each_link_write_with_opt(id, buf, len, done)
#endif

static void no_wait(void)
{
    assert(!waits && !polls && !completions && !lock_depth);
}

static void no_effect(void)
{
    no_wait();
    assert(!gets && !records && !copies && !dma_locks && !events);
    assert(!shows && !state_checks && !dsp_checks);
}

static void unavailable(unsigned int kind)
{
    if (kind == 0)
        link.tx_dma_buf.writer_working = true;
    else if (kind == 1)
        link.tx_dma_buf.write_index = sizeof(ring) - 1; /* no ring capacity */
    else if (kind == 2)
        link.tx_dma_buf.entry_w = link.tx_dma_buf.entry_l - 1; /* no entry */
    else
        link.tx_dma_buf.write_index = sizeof(ring) - 3; /* copy-stage NOSPACE */
}

int main(void)
{
    struct { struct gps_each_device dev; unsigned char guard[32]; } storage;
    struct gps_each_device *dev = &storage.dev;
    struct file file = { .private_data = dev, .f_flags = O_NONBLOCK };
    unsigned char input[GPS_DATA_PATH_BUF_MAX + 16];
    const char *user = (const char *)input;
    const size_t counts[] = { 1, sizeof(dev->o_buf), sizeof(dev->o_buf) + 1,
        UINT32_MAX, (size_t)UINT32_MAX + 1, SIZE_MAX };
    memset(&storage, 0x5a, sizeof(storage));
    dev->index = GPS_DATA_LINK_ID0;
    for (unsigned int i = 0; i < sizeof(input); i++)
        input[i] = (unsigned char)(i % 251);

    for (unsigned int flags = 0; flags < 2; flags++) {
        reset_case();
        file.f_flags = flags ? O_NONBLOCK : 0;
        assert(gps_each_device_write(&file, NULL, 0, NULL) == 0);
        no_effect();
        file.private_data = NULL;
        assert(gps_each_device_write(&file, NULL, 0, NULL) == 0);
        no_effect();
        file.private_data = dev;
    }
    reset_case();
    invalid_link = closed_link = true;
    assert(gps_each_link_write_with_options(GPS_DATA_LINK_ID0, NULL, 0, true, true) == 0);
    no_effect();

    for (unsigned int flags = 0; flags < 2; flags++) {
        file.f_flags = flags ? O_NONBLOCK : 0;
        for (size_t n = 0; n < sizeof(counts) / sizeof(counts[0]); n++) {
            reset_case();
            memset(dev->o_buf, 0x5a, sizeof(dev->o_buf));
            unsigned int length = counts[n] > sizeof(dev->o_buf) ? sizeof(dev->o_buf) : counts[n];
            assert(gps_each_device_write(&file, user, counts[n], NULL) == length);
            assert(last_copy == length && last_enter == length && copies == 1 && records == 2);
            assert(memcmp(ring, input, length) == 0 && ring[length] == 0xa5);
            assert(events == 1 && dma_locks == 2 && !link.tx_dma_buf.writer_working);
            for (unsigned int i = 0; i < sizeof(storage.guard); i++)
                assert(storage.guard[i] == 0x5a);
            for (unsigned int i = 0; i < sizeof(dev->i_buf); i++)
                assert(dev->i_buf[i] == 0x5a);
            if (flags)
                no_wait();
            else {
                assert(!waits);
#if GPS_DL_NO_USE_IRQ == 1
                assert(polls == 1 && completions == 1);
#else
                assert(!polls && !completions);
#endif
            }
        }
    }
    file.f_flags = O_NONBLOCK;
    for (unsigned int kind = 0; kind < 4; kind++) {
        reset_case();
        unavailable(kind);
        struct gps_dl_dma_buf before;
        memcpy(&before, &link.tx_dma_buf, sizeof(before));
        unsigned char before_ring[sizeof(ring)];
        memcpy(before_ring, ring, sizeof(ring));
        assert(gps_each_device_write(&file, user, 16, NULL) == -EAGAIN);
        no_wait();
        assert(events == 0 && copies == 1 && dma_locks == (kind == 3 ? 2u : 1u));
        assert(memcmp(&before, &link.tx_dma_buf, sizeof(before)) == 0);
        assert(memcmp(before_ring, ring, sizeof(ring)) == 0);
    }

    /* Ring wrap and word padding use the production copy and completion APIs. */
    for (unsigned int word = 0; word < 2; word++) {
        reset_case();
        byte_mode = !word;
        link.tx_dma_buf.read_index = link.tx_dma_buf.write_index = sizeof(ring) - 4;
        assert(gps_each_device_write(&file, user, 7, NULL) == 7);
        for (unsigned int i = 0; i < 7; i++)
            assert(ring[(sizeof(ring) - 4 + i) % sizeof(ring)] == input[i]);
        assert(link.tx_dma_buf.write_index == (word ? 4u : 3u));
        assert(ring[3] == (word ? 0 : 0xa5));
        assert(events == 1 && link.tx_dma_buf.entry_w == 1 && dma_locks == 2);
        no_wait();
    }

    reset_case();
    invalid_link = true;
    assert(gps_each_device_write(&file, user, 16, NULL) == -EINVAL);
    assert(!dma_locks && !events);
    no_wait();
    reset_case();
    closed_link = true;
    assert(gps_each_device_write(&file, user, 16, NULL) == -EBUSY);
    assert(!dma_locks && !events);
    no_wait();
    reset_case();
    link.tx_dma_buf.len = 8;
    assert(gps_each_device_write(&file, user, 16, NULL) == -EINVAL);
    assert(!dma_locks && !events);
    no_wait();
    reset_case();
    copy_residual = 1;
    assert(gps_each_device_write(&file, user, 16, NULL) == -EFAULT);
    assert(!gets && !dma_locks && !events);
    no_wait();
    reset_case();
    assert(gps_each_link_write_with_options(GPS_DATA_LINK_ID0, NULL, 16, true, true) == -EFAULT);
    assert(!dma_locks && !events);
    no_wait();

    /* Nonblocking overrides either completion choice for this call only. */
    for (unsigned int done = 0; done < 2; done++) {
        reset_case();
        assert(gps_each_link_write_with_options(GPS_DATA_LINK_ID0, input, 16, done, true) == 0);
        assert(events == 1 && dma_locks == 2 && link.tx_dma_buf.entry_w == 1);
        no_wait();
    }

    /* wait_tx_done=false still waits for capacity in the legacy API. */
    for (unsigned int done = 0; done < 2; done++) {
        for (unsigned int kind = 0; kind < 4; kind++) {
            reset_case();
            unavailable(kind);
            retry_count = 2;
            drain_steps = 2;
            assert(gps_each_link_write_with_opt(GPS_DATA_LINK_ID0, input, 16, done) == 0);
            assert(waits == 3 && events == 1 && !lock_depth);
#if GPS_DL_NO_USE_IRQ == 1
            assert(polls == (done ? 2u : 0u) && completions == polls);
#else
            assert(!polls && !completions);
#endif
        }
        reset_case();
        unavailable(0);
        wait_result = GDL_FAIL_SIGNALED;
        assert(gps_each_link_write_with_opt(GPS_DATA_LINK_ID0, input, 16, done) == -ERESTARTSYS);
        assert(waits == 1 && !events && !polls && !completions);
        reset_case();
        unavailable(0);
        wait_result = GDL_FAIL_NOT_SUPPORT; /* Vendor retries non-signal errors. */
        assert(gps_each_link_write_with_opt(GPS_DATA_LINK_ID0, input, 16, done) == 0);
        assert(waits == 1 && events == 1);
    }
    reset_case();
    file.f_flags = 0;
    unavailable(1);
    assert(gps_each_device_write(&file, user, 16, NULL) == 16);
    assert(waits == 1 && events == 1);
    assert(!lock_depth);
    puts("PASS: actual GNSS TX device/link/DMA functions and legacy wait contract");
    return 0;
}
