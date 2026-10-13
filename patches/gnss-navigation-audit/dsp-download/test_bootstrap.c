#include "bootstrap.h"
#include "clock.h"

#include <assert.h>
#include <errno.h>
#include <fenv.h>
#include <limits.h>
#include <string.h>

static const uint8_t name[] = "abcde";

struct fixture {
    struct b41_mvcd_bootstrap_inputs fields;
    struct b41_bootstrap_session session;
    struct b41_bootstrap_boot_info info;
    struct b41_bootstrap_query query;
};

static void init(struct fixture *f)
{
    /* Synthetic public values only. This never opens a descriptor or queries
     * hardware; the key word is a test vector, not any device/session secret.
     */
    memset(f, 0, sizeof(*f));
    f->fields.context_mode_13 = 0xff;
    f->fields.context_hz_18 = 26000000u;
    f->fields.context_baud_1c = 921600u;
    f->fields.context_chip_30 = UINT32_C(0xffff6725);
    f->fields.context_lna_54 = 0xab;
    f->fields.setting_717cb7 = 3;
    f->fields.word_7178b0 = 0x1b2c;
    f->fields.feature_name = name;
    f->fields.feature_name_size = sizeof(name);
    f->fields.secondary_fd_6edeec = -1;
    f->session.gps0_fd = 0;
    f->session.selectors.secure_download_7178b8_33e = 1;
    f->session.fields = &f->fields;
    f->info.code_size = 0x1234;
    f->info.start_addr = 0x89ab;
    f->info.exec_addr = 0xcdef;
    f->info.cipher_key = 0x1357;
    f->info.frag_num = 3;
    f->query.session = &f->session;
    f->query.gps0_fd = f->session.gps0_fd;
    f->query.selectors = f->session.selectors;
    f->query.command = 23;
    f->query.info = &f->info;
    f->query.bytes_returned = sizeof(f->info);
}

static void failure(struct fixture *f, int expected)
{
    uint8_t payload[106], frame[116], p_before[106], f_before[116];
    struct fixture inputs_before;
    size_t written = 77;

    memset(payload, 0x5a, sizeof(payload));
    memset(frame, 0xa5, sizeof(frame));
    memcpy(p_before, payload, sizeof(payload));
    memcpy(f_before, frame, sizeof(frame));
    memcpy(&inputs_before, f, sizeof(*f));
    assert(b41_bootstrap_payload_build(&f->session, &f->query, payload, sizeof(payload)) == expected);
    assert(b41_bootstrap_frame_build(&f->session, &f->query, frame, sizeof(frame), &written) == expected);
    assert(memcmp(payload, p_before, sizeof(payload)) == 0);
    assert(memcmp(frame, f_before, sizeof(frame)) == 0 && written == 77);
    assert(memcmp(&inputs_before, f, sizeof(*f)) == 0);
}

static void golden(void)
{
    static const uint8_t expected[106] = {
        0x1a, 0x00, 0x00, 0x00, 0x00, 0x01, 0xc3, 0x01, 0xa5, 0x02, 0x00, 0x00,
        0x00, 0x00, 0x34, 0x12, 0xab, 0x89, 0xef, 0xcd, 0x57, 0x13, 0x03, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x05, 0x00, 0x9d, 0x00, 0x6f, 0x3c, 0x88, 0x89,
        0x00, 0x00, 0x00, 0x00, 0xdc, 0x00, 0xc1, 0x00, 0x28, 0x00, 0x5c, 0x4a,
        0x1e, 0x00, 0xc5, 0x37, 0x28, 0x00, 0x5c, 0x4a, 0x8f, 0x65, 0x03, 0x00,
        0x00, 0x00, 0x28, 0x00, 0xff, 0x00, 0x80, 0x00, 0x47, 0x00, 0x64, 0x00,
        0x50, 0x00, 0xd8, 0x00, 0x50, 0x00, 0xbb, 0x00, 0x03, 0x00, 0x3c, 0x00,
        0x6f, 0x00, 0x89, 0x00, 0x88, 0x00, 0x02, 0x00, 0xfb, 0x00, 0x2c, 0x1b,
        0x25, 0x67, 0x48, 0x49, 0x00, 0x00, 0x01, 0x00, 0x4e, 0x4f
    };
    struct fixture f;
    uint8_t payload[128], frame[128];
    size_t written = 0;

    init(&f);
    memset(payload, 0x5a, sizeof(payload));
    memset(frame, 0xa5, sizeof(frame));
    assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
    assert(memcmp(payload, expected, sizeof(expected)) == 0);
    assert(b41_bootstrap_frame_build(&f.session, &f.query, frame, sizeof(frame), &written) == 0);
    assert(written == 116 && memcmp(frame + 6, expected, sizeof(expected)) == 0);
    assert(frame[0] == 0xaa && frame[1] == 0xf0 && frame[2] == 0x6e && frame[3] == 0);
    assert(frame[4] == 8 && frame[5] == 0xfe);
    assert(frame[112] == 0x88 && frame[113] == 0x17);
    assert(frame[114] == 0xaa && frame[115] == 0x0f);
    for (size_t i = 106; i < sizeof(payload); ++i)
        assert(payload[i] == 0x5a);
    for (size_t i = 116; i < sizeof(frame); ++i)
        assert(frame[i] == 0xa5);
    /* Descriptors are query/transport inputs, never wire fields. */
    f.session.gps0_fd = INT_MAX;
    f.query.gps0_fd = INT_MAX;
    assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
    assert(memcmp(payload, expected, sizeof(expected)) == 0);
    f.session.selectors.dsp_selector_717cb0 = 63;
    f.query.selectors = f.session.selectors;
    f.query.command = 24;
    assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
    assert(memcmp(payload, expected, sizeof(expected)) == 0); /* CW uses same grammar. */
}

static void selection(void)
{
    struct fixture f;
    struct b41_bootstrap_route route, before;
    uint8_t payload[106];

    for (unsigned int flag = 0; flag <= 255u; ++flag) {
        for (unsigned int selector = 0; selector <= 255u; ++selector) {
            struct b41_bootstrap_selectors input = {(uint8_t)flag, (uint8_t)selector};

            memset(&route, 0x5a, sizeof(route));
            memcpy(&before, &route, sizeof(route));
            if (flag == 0) {
                assert(b41_bootstrap_route_select(&input, &route) == B41_BOOTSTRAP_EMBEDDED_IMAGE);
                assert(memcmp(&before, &route, sizeof(route)) == 0);
            } else {
                uint8_t expected = (uint8_t)(selector >= 1u && selector <= 63u ? 24u : 23u);

                assert(b41_bootstrap_route_select(&input, &route) == 0);
                assert(route.metadata_ioctl == expected && route.fragment_ioctl == expected + 2u);
            }
        }
    }
    assert(b41_bootstrap_route_select(NULL, &route) == B41_BOOTSTRAP_ARGUMENT);
    init(&f);
    for (unsigned int selector = 0; selector <= 255u; ++selector) {
        f.session.selectors.dsp_selector_717cb0 = (uint8_t)selector;
        f.query.selectors = f.session.selectors;
        f.query.command = selector >= 1u && selector <= 63u ? 24u : 23u;
        assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
        f.query.command = f.query.command == 24u ? 23u : 24u;
        failure(&f, B41_BOOTSTRAP_QUERY);
    }
    f.session.selectors.secure_download_7178b8_33e = 0;
    f.query.selectors = f.session.selectors;
    failure(&f, B41_BOOTSTRAP_EMBEDDED_IMAGE);
}

static void metadata_and_session(void)
{
    struct fixture f;
    struct b41_bootstrap_session other;
    uint8_t payload[106], frame[116];
    size_t written = 0;

    init(&f);
    f.query.session = NULL;
    failure(&f, B41_BOOTSTRAP_SESSION);
    f.query.session = &f.session;
    other = f.session;
    f.query.session = &other; /* Same fd/inputs, distinct open lifetime identity. */
    failure(&f, B41_BOOTSTRAP_SESSION);
    f.query.session = &f.session;
    f.query.gps0_fd = 1;
    failure(&f, B41_BOOTSTRAP_SESSION);
    f.query.gps0_fd = 0;
    f.session.gps0_fd = -1;
    f.query.gps0_fd = -1;
    failure(&f, B41_BOOTSTRAP_SESSION);
    init(&f);
    f.query.selectors.secure_download_7178b8_33e = 2;
    failure(&f, B41_BOOTSTRAP_SESSION);
    init(&f);
    f.query.selectors.dsp_selector_717cb0 = 64;
    failure(&f, B41_BOOTSTRAP_SESSION); /* Even though both choose ioctl23. */
    init(&f);
    f.query.info = NULL;
    f.query.bytes_returned = 0;
    f.query.status = -EIO;
    failure(&f, -EIO); /* Preserve actual failure before touching absent output. */
    f.query.status = -EINVAL;
    failure(&f, -EINVAL); /* Syscall error must not alias the embedded-path code. */
    f.query.status = 2;
    failure(&f, B41_BOOTSTRAP_QUERY);
    f.query.status = 18;
    failure(&f, B41_BOOTSTRAP_QUERY);
    f.query.status = 0;
    failure(&f, B41_BOOTSTRAP_MISSING);
    init(&f);
    for (size_t size = 0; size < 20u; ++size) {
        f.query.bytes_returned = size;
        failure(&f, B41_BOOTSTRAP_MISSING);
    }
    f.query.bytes_returned = 21;
    failure(&f, B41_BOOTSTRAP_MISSING);
    init(&f);
    for (unsigned int word = 0; word < 5u; ++word) {
        uint32_t *fields[] = {&f.info.code_size, &f.info.start_addr, &f.info.exec_addr,
                             &f.info.cipher_key, &f.info.frag_num};
        uint32_t old = *fields[word];

        *fields[word] = 0x10000u;
        failure(&f, B41_BOOTSTRAP_METADATA);
        *fields[word] = old;
    }
    f.info.code_size = 0;
    failure(&f, B41_BOOTSTRAP_METADATA);
    init(&f);
    f.info.frag_num = 0;
    failure(&f, B41_BOOTSTRAP_METADATA);
    f.info.frag_num = 258;
    failure(&f, B41_BOOTSTRAP_METADATA);
    for (uint32_t count = 256; count <= 257; ++count) {
        f.info.frag_num = count;
        assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
        assert(payload[22] == (uint8_t)count && payload[23] == 1);
    }
    /* Zero addresses/key are not invented defaults or universally invalid. */
    f.info.code_size = UINT16_MAX;
    f.info.start_addr = 0;
    f.info.exec_addr = 0;
    f.info.cipher_key = 0;
    f.info.frag_num = 1;
    assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
    assert(payload[14] == 255 && payload[15] == 255);
    for (size_t byte = 16; byte < 22u; ++byte)
        assert(payload[byte] == 0);
    f.session.fields = NULL;
    failure(&f, B41_BOOTSTRAP_MISSING);
    init(&f);
    f.fields.feature_name = NULL;
    failure(&f, B41_MVCD_FIELDS_MISSING);
    init(&f);
    f.fields.context_hz_18 = 0;
    failure(&f, B41_MVCD_CLOCK_ARGUMENT);
    init(&f);
    f.fields.context_mode_13 = 0xfe;
    failure(&f, B41_MVCD_FIELDS_MISSING);
    init(&f);
    assert(fesetround(FE_DOWNWARD) == 0);
    failure(&f, B41_MVCD_CLOCK_ENVIRONMENT);
    assert(fesetround(FE_TONEAREST) == 0);
    assert(b41_bootstrap_payload_build(NULL, &f.query, payload, sizeof(payload)) == B41_BOOTSTRAP_MISSING);
    assert(b41_bootstrap_frame_build(&f.session, NULL, frame, sizeof(frame), &written) == B41_BOOTSTRAP_MISSING);
}

static void frequency_table(void)
{
    static const uint32_t low[] = {
        11999976u, 15999968u, 19199962u, 19999960u, 23999952u,
        25999948u, 31999936u, 38399924u, 39999920u, 51999896u
    };
    static const uint32_t high[] = {
        12000024u, 16000032u, 19200038u, 20000040u, 24000048u,
        26000052u, 32000064u, 38400076u, 40000080u, 52000104u
    };
    static const uint8_t table[32] = {
        40, 0, 255, 0, 128, 0, 71, 0, 100, 0, 80, 0, 216, 0, 80, 0,
        187, 0, 3, 0, 60, 0, 111, 0, 137, 0, 136, 0, 2, 0, 251, 0
    };
    static const uint8_t zero[32] = {0};
    struct fixture f;
    struct b41_mvcd_private_clock private = {
        {0xcc, 0, 0, 0, 0x80, 0xba, 0x8c, 1}, /* Synthetic26000000 valid record. */
        {0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff} /* Invalid adjustment. */
    };
    uint8_t payload[106];

    init(&f);
    for (size_t row = 0; row < sizeof(low) / sizeof(low[0]); ++row) {
        uint32_t frequencies[] = {low[row] - 1u, low[row], high[row], high[row] + 1u};

        for (size_t i = 0; i < sizeof(frequencies) / sizeof(frequencies[0]); ++i) {
            f.fields.context_hz_18 = frequencies[i];
            assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
            assert(memcmp(payload + 62, i == 1u || i == 2u ? table : zero, 32) == 0);
        }
    }
    f.fields.context_mode_13 = 0xfe;
    f.fields.context_hz_18 = 33000000u;
    f.fields.private_clock = &private;
    assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
    assert(payload[30] == 157 && memcmp(payload + 62, zero, 32) == 0);
    {
        static const uint8_t synthetic33m[8] = {0x28, 2, 0, 0, 0x40, 0x8a, 0xf7, 1};

        memcpy(private.frequency_1670, synthetic33m, 8);
    }
    f.fields.context_hz_18 = 26000000u;
    assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, sizeof(payload)) == 0);
    assert(payload[30] == 250 && memcmp(payload + 62, table, 32) == 0);
    assert(payload[60] == 1);
}

static void bounds_and_overlap(void)
{
    struct fixture f;
    uint8_t payload[106], frame[116], p_before[106], f_before[116];
    _Alignas(size_t) uint8_t alias[128];
    size_t written = 99;

    init(&f);
    memset(payload, 0x5a, sizeof(payload));
    memset(frame, 0xa5, sizeof(frame));
    memcpy(p_before, payload, sizeof(payload));
    memcpy(f_before, frame, sizeof(frame));
    for (size_t size = 0; size < sizeof(payload); ++size)
        assert(b41_bootstrap_payload_build(&f.session, &f.query, payload, size) == B41_BOOTSTRAP_CAPACITY);
    for (size_t size = 0; size < sizeof(frame); ++size)
        assert(b41_bootstrap_frame_build(&f.session, &f.query, frame, size, &written) == B41_BOOTSTRAP_CAPACITY);
    assert(memcmp(payload, p_before, sizeof(payload)) == 0);
    assert(memcmp(frame, f_before, sizeof(frame)) == 0 && written == 99);
    assert(b41_bootstrap_payload_build(&f.session, &f.query, NULL, 106) == B41_BOOTSTRAP_ARGUMENT);
    assert(b41_bootstrap_frame_build(&f.session, &f.query, NULL, 116, &written) == B41_BOOTSTRAP_ARGUMENT);
    assert(b41_bootstrap_frame_build(&f.session, &f.query, frame, 116, NULL) == B41_BOOTSTRAP_ARGUMENT);
    for (size_t offset = 0; offset < 116u; offset += sizeof(size_t)) {
        memset(alias, 0x5a, sizeof(alias));
        assert(b41_bootstrap_frame_build(&f.session, &f.query, alias, sizeof(alias),
                                        (size_t *)(void *)(alias + offset)) == B41_BOOTSTRAP_OVERLAP);
        for (size_t byte = 0; byte < sizeof(alias); ++byte)
            assert(alias[byte] == 0x5a);
    }
    {
        void *inputs[] = {&f.session, &f.query, &f.info, &f.fields};
        struct fixture before;

        memcpy(&before, &f, sizeof(f));
        for (size_t i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i) {
            assert(b41_bootstrap_payload_build(&f.session, &f.query, inputs[i], 106) == B41_BOOTSTRAP_OVERLAP);
            assert(b41_bootstrap_frame_build(&f.session, &f.query, inputs[i], 116, &written) == B41_BOOTSTRAP_OVERLAP);
            assert(memcmp(&before, &f, sizeof(f)) == 0 && written == 99);
        }
        assert(b41_bootstrap_frame_build(&f.session, &f.query, frame, 116,
                                        &f.query.bytes_returned) == B41_BOOTSTRAP_OVERLAP);
        assert(memcmp(&before, &f, sizeof(f)) == 0);
    }
    {
        union {
            struct b41_bootstrap_selectors selectors;
            struct b41_bootstrap_route route;
        } input = {.selectors = {1, 0}};

        assert(b41_bootstrap_route_select(&input.selectors, &input.route) == B41_BOOTSTRAP_OVERLAP);
        assert(input.selectors.secure_download_7178b8_33e == 1);
        assert(input.selectors.dsp_selector_717cb0 == 0);
        assert(b41_bootstrap_route_select(&input.selectors, NULL) == B41_BOOTSTRAP_ARGUMENT);
    }
    {
        uint8_t borrowed_name[128], before[128];
        struct b41_mvcd_private_clock private, private_before;

        memset(borrowed_name, 0x5a, sizeof(borrowed_name));
        memcpy(borrowed_name, name, sizeof(name));
        memcpy(before, borrowed_name, sizeof(before));
        f.fields.feature_name = borrowed_name;
        assert(b41_bootstrap_frame_build(&f.session, &f.query, borrowed_name,
                                        sizeof(borrowed_name), &written) == B41_BOOTSTRAP_OVERLAP);
        assert(memcmp(before, borrowed_name, sizeof(before)) == 0);
        memset(&private, 0x5a, sizeof(private));
        memcpy(&private_before, &private, sizeof(private));
        f.fields.private_clock = &private;
        assert(b41_bootstrap_payload_build(&f.session, &f.query, (void *)&private,
                                          106) == B41_BOOTSTRAP_OVERLAP);
        assert(memcmp(&private, &private_before, sizeof(private)) == 0);
    }
}

int main(void)
{
    assert(fesetround(FE_TONEAREST) == 0);
    golden();
    selection();
    metadata_and_session();
    frequency_table();
    bounds_and_overlap();
    return 0;
}
