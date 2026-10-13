#include "download.h"

#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <string.h>

/* Entirely synthetic profile/metadata. No descriptor or ROM session is opened. */
static const uint8_t name[] = "test";
struct fixture {
    struct b41_mvcd_bootstrap_inputs fields;
    struct b41_bootstrap_session session;
    struct b41_bootstrap_boot_info info;
    struct b41_bootstrap_query query;
    struct b41_download owner;
};

static void init(struct fixture *f, unsigned int count, int cw)
{
    memset(f, 0, sizeof(*f));
    f->fields.context_mode_13 = 0xff;
    f->fields.context_hz_18 = 26000000u;
    f->fields.context_baud_1c = 921600u;
    f->fields.context_chip_30 = UINT32_C(0xffff6725);
    f->fields.feature_name = name;
    f->fields.feature_name_size = sizeof(name);
    f->fields.secondary_fd_6edeec = -1;
    f->session.gps0_fd = 0;
    f->session.selectors.secure_download_7178b8_33e = 1;
    f->session.selectors.dsp_selector_717cb0 = (uint8_t)(cw ? 1 : 0);
    f->session.fields = &f->fields;
    f->info.code_size = 0x1234;
    f->info.start_addr = 0x5678;
    f->info.exec_addr = 0x9abc;
    f->info.cipher_key = 0x1357;
    f->info.frag_num = count;
    f->query.session = &f->session;
    f->query.gps0_fd = 0;
    f->query.selectors = f->session.selectors;
    f->query.command = cw ? 24u : 23u;
    f->query.info = &f->info;
    f->query.bytes_returned = sizeof(f->info);
}

static size_t ack(uint8_t *bytes, uint8_t command, unsigned int seq, size_t payload)
{
    unsigned int sum = 0;
    size_t size = payload + 10u;

    memset(bytes, 0, size);
    bytes[0] = 0xaa;
    bytes[1] = 0xf0;
    bytes[2] = (uint8_t)(payload + 4u);
    bytes[3] = (uint8_t)(((payload + 4u) >> 8) | 0xf0u);
    bytes[4] = command;
    bytes[5] = 0xfe;
    bytes[6] = (uint8_t)seq;
    bytes[7] = (uint8_t)(seq >> 8);
    if (payload >= 4u) {
        bytes[8] = 0xff; /* Opaque auxiliary word is not a failure flag/count. */
        bytes[9] = 0xff;
    }
    for (size_t i = 2; i < payload + 6u; ++i)
        sum += bytes[i];
    bytes[size - 4u] = (uint8_t)sum;
    bytes[size - 3u] = (uint8_t)(sum >> 8);
    bytes[size - 2u] = 0xaa;
    bytes[size - 1u] = 0x0f;
    return size;
}

static void erased(const struct b41_download *d)
{
    for (size_t i = 0; i < sizeof(d->tx); ++i)
        assert(d->tx[i] == 0);
    for (size_t i = 0; i < sizeof(d->rx); ++i)
        assert(d->rx[i] == 0);
}

static void boot_tx(struct fixture *f)
{
    struct b41_download_action action;

    assert(b41_download_begin(&f->owner, &f->session, &f->query, 1, 1000) == 0);
    assert(b41_download_begin(&f->owner, &f->session, &f->query, 1, 1000) == -EALREADY);
    assert(b41_download_next(&f->owner, 2, &action) == 0);
    assert(action.kind == B41_DOWNLOAD_WRITE && action.size == 116 && action.gps0_fd == 0);
    assert(b41_download_written(&f->owner, 3, -EAGAIN) == 0);
    assert(f->owner.tx_offset == 0);
    assert(b41_download_written(&f->owner, 4, 3) == 0);
    assert(b41_download_next(&f->owner, 4, &action) == 0);
    assert(action.kind == B41_DOWNLOAD_WRITE && action.size == 113);
    assert(b41_download_written(&f->owner, 5, 113) == 0);
    assert(f->owner.stage == B41_DOWNLOAD_BOOTSTRAP_RX);
    erased(&f->owner);
}

static void complete(void)
{
    struct fixture f;
    struct b41_download_action action;
    uint8_t bytes[1024];

    for (unsigned int count = 1; count <= 257u; ++count) {
        for (int cw = 0; cw <= 1; ++cw) {
            init(&f, count, cw);
            boot_tx(&f);
            for (unsigned int seq = 0; seq <= count; ++seq) {
                size_t size;

                if (seq > 0) {
                    assert(b41_download_next(&f.owner, 6, &action) == 0);
                    assert(action.kind == B41_DOWNLOAD_SUBMIT_FRAGMENT);
                    assert(action.command == (cw ? 26u : 25u) && action.argument == seq - 1u);
                    assert(action.bytes == NULL && action.size == 0); /* NO extra trigger. */
                    assert(b41_download_submitted(&f.owner, 6, 0) == 0);
                }
                assert(b41_download_next(&f.owner, 6, &action) == 0);
                assert(action.kind == B41_DOWNLOAD_READ);
                size = ack(bytes, seq == 0 ? 0x31 : 0x32, seq, seq == 0 ? 4u : 2u);
                for (size_t i = 0; i < size; ++i)
                    assert(b41_download_received(&f.owner, 6, bytes + i, 1) == 0);
            }
            assert(f.owner.matched_fragments == count && f.owner.fragment_sequence == count + 1u);
            assert(b41_download_next(&f.owner, 9999, &action) == 0);
            assert(action.kind == B41_DOWNLOAD_DONE && f.owner.stage == B41_DOWNLOAD_ACKS_COMPLETE);
            assert(f.owner.session == NULL);
            f.session.gps0_fd = -1;
            f.session.fields = NULL;
            assert(b41_download_next(&f.owner, 0, &action) == 0);
            assert(action.kind == B41_DOWNLOAD_DONE);
            assert(b41_download_abort(&f.owner, -EIO) == -EALREADY);
            assert(f.owner.stage == B41_DOWNLOAD_ACKS_COMPLETE);
            erased(&f.owner);
        }
    }
    /* Largest bounded ACK split at each possible byte boundary. */
    for (size_t split = 1; split < sizeof(bytes); ++split) {
        init(&f, 1, 0);
        boot_tx(&f);
        size_t size = ack(bytes, 0x31, 0, 1014);
        assert(b41_download_received(&f.owner, 6, bytes, split) == 0);
        assert(f.owner.stage == B41_DOWNLOAD_BOOTSTRAP_RX);
        assert(b41_download_received(&f.owner, 6, bytes + split, size - split) == 0);
        assert(f.owner.stage == B41_DOWNLOAD_FRAGMENT_IOCTL);
    }
}

static void failed(struct fixture *f, int error)
{
    struct b41_download_action action, before;
    uint8_t byte = 0;

    memset(&action, 0xa5, sizeof(action));
    memcpy(&before, &action, sizeof(before));
    assert(f->owner.stage == B41_DOWNLOAD_FAILED && f->owner.first_error == error);
    assert(b41_download_abort(&f->owner, -ENOSPC) == error);
    assert(b41_download_begin(&f->owner, &f->session, &f->query, 1, 1000) == error);
    assert(b41_download_next(&f->owner, 9000, &action) == error);
    assert(memcmp(&action, &before, sizeof(action)) == 0);
    assert(b41_download_written(&f->owner, 9000, 116) == error);
    assert(b41_download_submitted(&f->owner, 9000, 0) == error);
    assert(b41_download_received(&f->owner, 9000, &byte, 1) == error);
    erased(&f->owner);
}

static void faults(void)
{
    struct fixture f;
    struct b41_download_action action;
    uint8_t bytes[1025];
    size_t size;

    init(&f, 1, 0);
    f.query.status = -ENXIO;
    assert(b41_download_begin(&f.owner, &f.session, &f.query, 1, 1000) == -ENXIO);
    failed(&f, -ENXIO);
    init(&f, 258, 0);
    assert(b41_download_begin(&f.owner, &f.session, &f.query, 1, 1000) == B41_BOOTSTRAP_METADATA);
    failed(&f, B41_BOOTSTRAP_METADATA);
    init(&f, 1, 0);
    assert(b41_download_begin(&f.owner, &f.session, &f.query, 1, 1) == -ETIMEDOUT);
    failed(&f, -ETIMEDOUT);
    init(&f, 1, 0);
    boot_tx(&f);
    assert(b41_download_next(&f.owner, 1000, &action) == -ETIMEDOUT);
    failed(&f, -ETIMEDOUT);
    init(&f, 1, 0);
    boot_tx(&f);
    assert(b41_download_next(&f.owner, 4, &action) == -EINVAL);
    failed(&f, -EINVAL);
    init(&f, 1, 0);
    boot_tx(&f);
    ++f.session.gps0_fd;
    assert(b41_download_next(&f.owner, 6, &action) == -ESTALE);
    failed(&f, -ESTALE);
    init(&f, 1, 0);
    boot_tx(&f);
    ++f.session.selectors.dsp_selector_717cb0;
    assert(b41_download_next(&f.owner, 6, &action) == -ESTALE);
    failed(&f, -ESTALE);
    for (int result = -1; result <= 117; ++result) {
        if (result > 0 && result <= 116)
            continue;
        init(&f, 1, 0);
        assert(b41_download_begin(&f.owner, &f.session, &f.query, 1, 1000) == 0);
        int expected = result < 0 ? result : -EIO;
        assert(b41_download_written(&f.owner, 2, result) == expected);
        failed(&f, expected);
    }
    for (unsigned int fault = 0; fault < 6u; ++fault) {
        init(&f, 1, 0);
        boot_tx(&f);
        size = ack(bytes, fault == 1u ? 0x33 : 0x31, fault == 0u ? 1u : 0u, 4);
        if (fault == 2u)
            bytes[10] ^= 1;
        if (fault == 3u)
            bytes[0] ^= 1;
        if (fault == 4u)
            bytes[12] ^= 1;
        if (fault == 5u)
            bytes[size++] = 0; /* Extra/stale bytes may not seed the next request. */
        int result = b41_download_received(&f.owner, 6, bytes, size);
        assert(result < 0);
        failed(&f, result);
    }
    init(&f, 1, 0);
    boot_tx(&f);
    size = ack(bytes, 0x31, 0, 4);
    assert(b41_download_received(&f.owner, 6, bytes, size) == 0);
    assert(b41_download_submitted(&f.owner, 7, -EINTR) == -EINTR);
    failed(&f, -EINTR); /* No ioctl replay after uncertain submission. */
    init(&f, 1, 0);
    boot_tx(&f);
    size = ack(bytes, 0x31, 0, 4);
    assert(b41_download_received(&f.owner, 6, bytes, size) == 0);
    size = ack(bytes, 0x32, 1, 2);
    assert(b41_download_received(&f.owner, 6, bytes, size) == -EPROTO); /* Before submission. */
    failed(&f, -EPROTO);
}

int main(void)
{
    complete();
    faults();
    return 0;
}
