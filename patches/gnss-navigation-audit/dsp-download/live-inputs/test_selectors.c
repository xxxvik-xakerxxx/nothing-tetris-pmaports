/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "selectors.h"

#include <assert.h>
#include <errno.h>
#include <fenv.h>
#include <fcntl.h>
#include <stdarg.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <stdlib.h>
#include <string.h>

#ifdef B41_NATIVE_L1_CLI_FIXTURE
/* Help and argument rejection must never reach profile or device acquisition. */
int __wrap_open(const char *path, int flags, ...)
{
    (void)path;
    (void)flags;
    _Exit(99);
}

int __wrap_ioctl(int fd, unsigned long command, ...)
{
    (void)fd;
    (void)command;
    _Exit(99);
}
#else

static void put32(uint8_t *p, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (8u*i));
}

static void pointer(uint8_t *image, uintptr_t offset, uintptr_t target)
{
    uintptr_t value = (uintptr_t)image + target;
    memcpy(image + offset, &value, sizeof(value));
}

static void check_mode(uint32_t input, uint8_t profile, uint32_t chip,
    const uint8_t *name, size_t length, int32_t fd,
    uint8_t mode, uint8_t setting, uint8_t flags)
{
    struct b41_bootstrap_mode out;
    memset(&out, 0xa5, sizeof(out));
    assert(b41_bootstrap_mode_build(input, chip, profile, name, length, fd, &out) == 0);
    assert(out.mode_75c990 == mode);
    assert(out.setting_717cb7 == setting);
    assert(out.flags_717cb8 == flags);
    assert(out.clock_717cb3 == ((flags >> 1) & 2u));
}

static void test_mode(void)
{
    static const uint8_t minimum[12] = {2, 2, 3, 0, 2, 2, 4, 2, 2, 2, 5, 5};
    static const uint8_t setting[12] = {3, 6, 7, 5, 0x17, 3, 0x17, 3, 3, 3, 0x27, 0x27};
    static const uint8_t flags[12] = {3, 0x31, 0x33, 1, 0x30, 2, 0x3f, 0x0d, 0x0f, 0x0c, 0x7f, 0x7e};
    static const uint8_t name[] = "gps-secondary";
    struct b41_bootstrap_mode out, before;
    uint8_t unterminated[662];

    for (unsigned profile = 0; profile < 256; ++profile) {
        for (unsigned mode = 0; mode < 256; ++mode) {
            if (mode >= 12 || profile < minimum[mode]) {
                check_mode(mode, (uint8_t)profile, 0xffff6878u, name, sizeof(name), 0,
                    (uint8_t)(profile == 1 ? 3u : 6u),
                    (uint8_t)(profile == 1 ? 5u : 0x17u),
                    (uint8_t)(profile == 1 ? 1u : 0x3fu));
            } else {
                check_mode(mode, (uint8_t)profile, 0xffff6878u, name, sizeof(name), 0,
                    (uint8_t)mode, setting[mode], flags[mode]);
            }
        }
    }
    check_mode(257, 5, 0xffff6878u, NULL, 0, -1, 1, 6, 0x31);
    check_mode(10, 5, 0xffff6878u, name, sizeof(name), -1, 6, 0x17, 0x3f);
    check_mode(10, 5, 0xffff6789u, name, sizeof(name), -1, 10, 0x27, 0x7f);
    check_mode(11, 5, 0xffff6789u, name, sizeof(name), -1, 11, 0x17, 0x3e);
    check_mode(11, 5, 0xffff6878u, name, sizeof(name), -1, 11, 0x27, 0x7e);
    check_mode(10, 5, 0xffff6878u, (const uint8_t *)"1234", 5, 0, 6, 0x17, 0x3f);
    check_mode(10, 5, 0xffff6878u, (const uint8_t *)"12345", 6, 0, 10, 0x27, 0x7f);
    check_mode(10, 4, 0xffff6878u, NULL, 0, -1, 6, 0x17, 0x3f);
    memset(&out, 0xa5, sizeof(out));
    memcpy(&before, &out, sizeof(before));
    assert(b41_bootstrap_mode_build(10, 0xffff6878u, 5, NULL, 0, 0, &out) == -ENODATA);
    assert(!memcmp(&out, &before, sizeof(out)));
    memset(unterminated, 'x', sizeof(unterminated));
    assert(b41_bootstrap_mode_build(11, 0xffff6878u, 5, unterminated, 661, 0, &out) == -ENODATA);
    assert(!memcmp(&out, &before, sizeof(out)));
    assert(b41_bootstrap_mode_build(11, 0xffff6878u, 5, unterminated, 662, 0, &out) == -EBADMSG);
    assert(!memcmp(&out, &before, sizeof(out)));
    assert(b41_bootstrap_mode_build(0, 0, 0, NULL, 0, 0, NULL) == -EINVAL);
}

static void test_associated_acquisition(void)
{
    static const char *const adies[3] = {"0x6631", "0x6637", "0x6686"};
    static const uintptr_t keys[3] = {0x6ed710u, 0x6ed8a0u, 0x6eda30u};
    static const uintptr_t records[3] = {0x6ed7d0u, 0x6ed960u, 0x6edaf0u};
    static const uintptr_t got[7] = {0x6e6660u, 0x6e6618u, 0x6e6668u,
        0x6e6670u, 0x6e6650u, 0x6e6658u, 0x6e6688u};
    static const uintptr_t target[7] = {0x7178b8u, 0x717cb0u, 0x717cb3u,
        0x717cb6u, 0x717cb7u, 0x717cb8u, 0x7178b0u};
    uint8_t *bytes = calloc(1, B41_LIBRARY_IMAGE_END);
    struct b41_library_association image;
    struct b41_bootstrap_chip chip, before;
    struct b41_bootstrap_observation observation, previous;

    assert(bytes);
    image.base = (uintptr_t)bytes;
    image.xml_global = image.base + 0x7178b8u;
    image.chip_global = image.base + 0x6f2dacu;
    image.extent = B41_LIBRARY_IMAGE_END;
    pointer(bytes, 0x6e6ff8u, 0x6edd50u);
    pointer(bytes, 0x6e7b00u, 0x6ee1a8u);
    put32(bytes + 0x6ee1a8u, 5);
    put32(bytes + 0x6ee1acu, 0xffff6878u);
    for (unsigned i = 0; i < 3; ++i) {
        pointer(bytes, 0x6edd50u + 16u*(21u+i), keys[i]);
        pointer(bytes, 0x6edd58u + 16u*(21u+i), records[i]);
        memcpy(bytes + keys[i], "0x6878", 7);
        memcpy(bytes + keys[i] + 0x5cu, adies[i], 7);
        put32(bytes + records[i] + 0x14u, 0xffff6878u);
        put32(bytes + records[i] + 0x18u, 0x370);
        put32(bytes + records[i] + 8u, i == 0 ? 6u : 10u);
        bytes[records[i] + 0xccu] = 1;
        assert(b41_bootstrap_chip_read(&image, "0x6878", adies[i], 0, 0, &chip) == 0);
        assert(chip.context_chip_30 == 0xffff6878u && chip.capabilities == 0x370);
        assert(chip.profile_selector_717cb6 == 5 && chip.capability.index == 21u+i);
        assert(chip.navigation_mode_base == (i == 0 ? 6u : 10u));
        assert(chip.secure_download_default == 1);
    }
    memcpy(&before, &chip, sizeof(before));
    assert(b41_bootstrap_chip_read(&image, "0x6878", "", 0, 0, &chip) == -ENODATA);
    assert(!memcmp(&chip, &before, sizeof(chip)));
    assert(b41_bootstrap_chip_read(&image, "0x6878", adies[0], 1, 0, &chip) == -ENODEV);
    assert(!memcmp(&chip, &before, sizeof(chip)));
    assert(b41_bootstrap_chip_read(&image, "0x6789", adies[0], 0, 0, &chip) == -EOPNOTSUPP);
    assert(!memcmp(&chip, &before, sizeof(chip)));
    pointer(bytes, 0x6e7b00u, 0x6ee1a0u);
    assert(b41_bootstrap_chip_read(&image, "0x6878", adies[0], 0, 0, &chip) == -ESTALE);
    assert(!memcmp(&chip, &before, sizeof(chip)));

    for (unsigned i = 0; i < 7; ++i) pointer(bytes, got[i], target[i]);
    bytes[0x7178b8u + 0x33eu] = 1;
    bytes[0x717cb0u] = 63;
    bytes[0x717cb3u] = 2;
    bytes[0x717cb6u] = 5;
    bytes[0x717cb7u] = 0x27;
    bytes[0x717cb8u] = 3;
    put32(bytes + 0x7178b0u, 0x87654321u);
    assert(b41_bootstrap_observe(&image, &observation) == 0);
    assert(observation.route.secure_download_7178b8_33e == 1);
    assert(observation.route.dsp_selector_717cb0 == 63);
    assert(observation.clock_selector_717cb3 == 2);
    assert(observation.profile_selector_717cb6 == 5);
    assert(observation.setting_717cb7 == 0x27);
    assert(observation.feature_flags_717cb8 == 3);
    assert(observation.word_7178b0 == 0x87654321u);
    memcpy(&previous, &observation, sizeof(previous));
    for (unsigned i = 0; i < 7; ++i) {
        pointer(bytes, got[i], target[i] + 1u);
        assert(b41_bootstrap_observe(&image, &observation) == -ESTALE);
        assert(!memcmp(&observation, &previous, sizeof(previous)));
        pointer(bytes, got[i], target[i]);
    }
    --image.extent;
    assert(b41_bootstrap_observe(&image, &observation) == -ERANGE);
    assert(!memcmp(&observation, &previous, sizeof(previous)));
    free(bytes);
}


static void word(uint8_t *p, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (8u*i));
}

static uint16_t half(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static void seed(struct b41_native_l1_identity *chip, struct b41_first_config *first)
{
    memset(chip, 0, sizeof(*chip));
    memset(first, 0, sizeof(*first));
    assert(b41_native_l1_identity_select(0x6878, 0x6631, chip) == 0);
    first->bytes[0x13] = 0xfe;
    first->provenance[0x13] = B41_FIRST_CLOCK_RESULT;
    word(first->bytes + 0x18, 26000000);
    memset(first->provenance + 0x18, B41_FIRST_NVRAM_PROFILE, 4);
    word(first->bytes + 0x1c, 115200);
    memset(first->provenance + 0x1c, B41_FIRST_CONSTANT, 4);
    first->provenance[0x24] = B41_FIRST_NVRAM_PROFILE;
    word(first->bytes + 0x54, 0x1234);
    memset(first->provenance + 0x54, B41_FIRST_LNA_RESULT, 4);
    /* Remaining unknown bytes must not require an opaque complete MNL context. */
    first->unresolved_bytes = 99;
    first->xml_policy_missing = 1;
}

static void test_build(void)
{
    static const uint16_t synthesis[14] = {
        157, 15471, 35208, 0, 0, 220, 193, 40, 19036, 30, 14277, 40, 19036, 25999
    };
    static const unsigned needed[] = {0x13, 0x18, 0x19, 0x1a, 0x1b,
        0x1c, 0x1d, 0x1e, 0x1f, 0x24, 0x54, 0x55, 0x56, 0x57};
    struct b41_native_l1_identity chip;
    struct b41_first_config first;
    struct b41_native_l1_nominal policy, before;
    struct b41_mvcd_bootstrap_fields legacy;

    seed(&chip, &first);
    assert(b41_native_l1_nominal_build(&chip, &first, 33, 0, &policy) == 0);
    assert(policy.selectors.secure_download_7178b8_33e == 1);
    assert(policy.selectors.dsp_selector_717cb0 == 0);
    assert(policy.navigation.mode_75c990 == 3 && policy.navigation.flags_717cb8 == 1);
    assert(policy.inputs.context_mode_13 == 0xfe && !policy.inputs.private_clock);
    assert(policy.inputs.secondary_fd_6edeec == -1 && !policy.inputs.feature_name[0]);
    assert(policy.fields.effective_hz == 26000000 && policy.fields.clock_mode == 0);
    assert(half(policy.fields.baud_and_parameters) == 0);
    assert(half(policy.fields.baud_and_parameters + 2) == 451);
    assert(half(policy.fields.baud_and_parameters + 4) == 677);
    for (unsigned i = 0; i < 14; ++i)
        assert(half(policy.fields.synthesis_and_profile + 2u*i) == synthesis[i]);
    assert(policy.fields.synthesis_and_profile[28] == 7);
    assert(policy.fields.synthesis_and_profile[30] == 1);
    assert(half(policy.fields.board_tail) == 0);
    assert(half(policy.fields.board_tail + 2) == 0x6878);
    assert(policy.fields.board_tail[4] == 0x34 && policy.fields.board_tail[5] == 10);
    assert(policy.fields.board_tail[8] == 1);
    /* Nominal and OEM override contracts stay separate, even with FE retained. */
    assert(b41_mvcd_bootstrap_fields_build(&policy.inputs, &legacy) == B41_MVCD_FIELDS_MISSING);
    memcpy(&before, &policy, sizeof(before));
    assert(b41_native_l1_nominal_build(&chip, &first, -EFAULT, 0, &policy) == -EFAULT);
    assert(!memcmp(&before, &policy, sizeof(policy)));
    assert(b41_native_l1_nominal_build(&chip, &first, 33, -EIO, &policy) == -EIO);
    assert(!memcmp(&before, &policy, sizeof(policy)));
    assert(b41_native_l1_nominal_build(&chip, &first, 33, 1, &policy) == -EOPNOTSUPP);
    assert(!memcmp(&before, &policy, sizeof(policy)));
    assert(b41_native_l1_nominal_build(&chip, &first, 81, 0, &policy) == -EOPNOTSUPP);
    assert(!memcmp(&before, &policy, sizeof(policy)));
    for (unsigned i = 0; i < sizeof(needed)/sizeof(needed[0]); ++i) {
        uint8_t old = first.provenance[needed[i]];
        first.provenance[needed[i]] = B41_FIRST_UNKNOWN;
        assert(b41_native_l1_nominal_build(&chip, &first, 33, 0, &policy) == -ENODATA);
        assert(!memcmp(&before, &policy, sizeof(policy)));
        first.provenance[needed[i]] = old;
    }
    word(first.bytes + 0x18, 52000000);
    assert(b41_native_l1_nominal_build(&chip, &first, 33, 0, &policy) == -EOPNOTSUPP);
    assert(!memcmp(&before, &policy, sizeof(policy)));
    seed(&chip, &first);
    first.bytes[0x24] = 1;
    assert(b41_native_l1_nominal_build(&chip, &first, 33, 0, &policy) == 0);
    assert(policy.fields.clock_mode == 4);
    assert(half(policy.fields.synthesis_and_profile + 8) == 4);
    assert(policy.inputs.context_mode_13 == 0xfe);
}

static void test_grammar_and_queries(void)
{
    struct b41_native_l1_identity chip;
    struct b41_first_config first;
    struct b41_native_l1_nominal policy;
    struct b41_bootstrap_session session = {0}, other;
    /* Public synthetic values only; never retained hardware metadata. */
    struct b41_bootstrap_boot_info info = {5, 0, 0, 0, 257};
    struct b41_bootstrap_query query = {0};
    uint8_t payload[106], frame[116], before[116];
    size_t length = 99;
    uint32_t checksum = 0;

    seed(&chip, &first);
    assert(b41_native_l1_nominal_build(&chip, &first, 33, 0, &policy) == 0);
    session.gps0_fd = 0;
    session.fields = &policy.inputs;
    session.selectors = policy.selectors;
    query.session = &session;
    query.gps0_fd = 0;
    query.selectors = policy.selectors;
    query.command = 23;
    query.info = &info;
    query.bytes_returned = sizeof(info);
    assert(b41_native_l1_nominal_payload_build(&policy, &session, &query,
        payload, sizeof(payload)) == 0);
    assert(half(payload) == 0x1a && half(payload + 2) == 0);
    assert(half(payload + 14) == 5 && half(payload + 22) == 257);
    assert(payload[28] == 5 && payload[58] == 7 && payload[60] == 1);
    assert(half(payload + 62) == 40 && half(payload + 74) == 216);
    assert(half(payload + 94) == 0 && half(payload + 96) == 0x6878);
    assert(payload[102] == 1 && payload[104] == 0x4e && payload[105] == 0x4f);
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame), &length) == 0 && length == sizeof(frame));
    assert(frame[0] == 0xaa && frame[1] == 0xf0 && half(frame + 2) == 110);
    assert(frame[4] == 8 && frame[5] == 0xfe);
    assert(!memcmp(frame + 6, payload, sizeof(payload)));
    for (unsigned i = 2; i < 112; ++i) checksum += frame[i];
    assert(half(frame + 112) == (uint16_t)checksum);
    assert(frame[114] == 0xaa && frame[115] == 0x0f);
    memcpy(before, frame, sizeof(before));
    length = 99;
    query.status = -EFAULT;
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame), &length) == -EFAULT);
    assert(!memcmp(before, frame, sizeof(frame)) && length == 99);
    query.status = 18;
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame), &length) == B41_BOOTSTRAP_QUERY);
    assert(!memcmp(before, frame, sizeof(frame)) && length == 99);
    query.status = 0;
    query.command = 24;
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame), &length) == B41_BOOTSTRAP_QUERY);
    query.command = 23;
    other = session;
    query.session = &other;
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame), &length) == B41_BOOTSTRAP_SESSION);
    query.session = &session;
    query.bytes_returned = 19;
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame), &length) == B41_BOOTSTRAP_MISSING);
    query.bytes_returned = 20;
    info.frag_num = 258;
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame), &length) == B41_BOOTSTRAP_METADATA);
    info.frag_num = 257;
    assert(b41_native_l1_nominal_payload_build(&policy, &session, &query,
        (uint8_t *)&policy, sizeof(policy)) == B41_BOOTSTRAP_OVERLAP);
    assert(b41_native_l1_nominal_frame_build(&policy, &session, &query,
        frame, sizeof(frame)-1u, &length) == B41_BOOTSTRAP_CAPACITY);
    assert(!memcmp(before, frame, sizeof(frame)) && length == 99);
}

static unsigned metadata_calls;
static int metadata_error;

int __wrap_clock_gettime(clockid_t clock_id, struct timespec *time);
int __wrap_fcntl(int fd, int command, ...);
int __wrap_fstat(int fd, struct stat *st);
int __wrap_ioctl(int fd, unsigned long command, ...);

int __wrap_clock_gettime(clockid_t clock_id, struct timespec *time)
{
    assert(clock_id == CLOCK_MONOTONIC);
    time->tv_sec = 0;
    time->tv_nsec = 10;
    return 0;
}

int __wrap_fcntl(int fd, int command, ...)
{
    assert(fd == 0 && command == F_GETFL);
    return O_RDWR | O_NONBLOCK;
}

int __wrap_fstat(int fd, struct stat *st)
{
    assert(fd == 0);
    memset(st, 0, sizeof(*st));
    st->st_mode = (mode_t)0020000;
    return 0;
}

int __wrap_ioctl(int fd, unsigned long command, ...)
{
    struct b41_bootstrap_boot_info *info;
    va_list args;
    assert(fd == 0 && command == 23);
    ++metadata_calls;
    if (metadata_error == 1) { errno = EFAULT; return -1; }
    if (metadata_error == 2) return 18;
    va_start(args, command);
    info = va_arg(args, struct b41_bootstrap_boot_info *);
    va_end(args);
    *info = (struct b41_bootstrap_boot_info){5, 0, 0, 0, 1};
    return 0;
}

static size_t native_ack(uint8_t *bytes, uint8_t command, uint16_t sequence)
{
    unsigned sum = 0;
    size_t payload = command == 0x31 ? 4u : 2u;
    size_t size = payload + 10u;
    memset(bytes, 0, size);
    bytes[0] = 0xaa; bytes[1] = 0xf0; bytes[2] = (uint8_t)(payload + 4u);
    bytes[3] = 0xf0; bytes[4] = command; bytes[5] = 0xfe;
    bytes[6] = (uint8_t)sequence; bytes[7] = (uint8_t)(sequence >> 8);
    for (size_t i = 2; i < payload + 6u; ++i) sum += bytes[i];
    bytes[size-4u] = (uint8_t)sum; bytes[size-3u] = (uint8_t)(sum >> 8);
    bytes[size-2u] = 0xaa; bytes[size-1u] = 0x0f;
    return size;
}

static void test_native_downloader(void)
{
    struct b41_native_l1_identity chip, before;
    struct b41_first_config first;
    struct b41_native_l1_nominal policy;
    struct b41_bootstrap_session session = {0};
    struct b41_download owner = {0}, failed = {0}, positive = {0}, expired = {0};
    struct b41_download_action action;
    uint8_t ack[14];

    seed(&chip, &first);
    memcpy(&before, &chip, sizeof(before));
    assert(b41_native_l1_identity_select(0x6878, 0, &chip) == -ENODEV);
    assert(!memcmp(&before, &chip, sizeof(chip)));
    assert(b41_native_l1_identity_select(0x1234, 0x6631, &chip) == -EOPNOTSUPP);
    assert(!memcmp(&before, &chip, sizeof(chip)));
    assert(b41_native_l1_nominal_build(&chip, &first, 33, 0, &policy) == 0);
    session.fields = &policy.inputs;
    session.selectors = policy.selectors;
    assert(b41_native_l1_download_linux_begin(&owner, &policy, &session, 1000) == 0);
    assert(metadata_calls == 1 && owner.stage == B41_DOWNLOAD_BOOTSTRAP_TX);
    assert(b41_native_l1_download_linux_begin(&owner, &policy, &session, 1000) == -EALREADY);
    assert(metadata_calls == 1);
    assert(b41_download_next(&owner, 11, &action) == 0);
    assert(action.kind == B41_DOWNLOAD_WRITE && action.gps0_fd == 0 && action.size == 116);
    assert(b41_download_written(&owner, 12, 116) == 0);
    assert(b41_download_received(&owner, 13, ack, native_ack(ack, 0x31, 0)) == 0);
    assert(b41_download_next(&owner, 14, &action) == 0);
    assert(action.kind == B41_DOWNLOAD_SUBMIT_FRAGMENT && action.command == 25 && action.argument == 0);
    assert(b41_download_submitted(&owner, 15, 0) == 0);
    assert(b41_download_received(&owner, 16, ack, native_ack(ack, 0x32, 1)) == 0);
    assert(owner.stage == B41_DOWNLOAD_ACKS_COMPLETE && owner.matched_fragments == 1);
    metadata_error = 1;
    assert(b41_native_l1_download_linux_begin(&failed, &policy, &session, 1000) == -EFAULT);
    assert(failed.stage == B41_DOWNLOAD_FAILED && failed.first_error == -EFAULT);
    assert(metadata_calls == 2);
    assert(b41_native_l1_download_linux_begin(&failed, &policy, &session, 1000) == -EFAULT);
    assert(metadata_calls == 2);
    metadata_error = 2;
    assert(b41_native_l1_download_linux_begin(&positive, &policy, &session, 1000) == -EPROTO);
    assert(positive.stage == B41_DOWNLOAD_FAILED && positive.first_error == -EPROTO);
    assert(metadata_calls == 3);
    assert(b41_native_l1_download_linux_begin(&expired, &policy, &session, 10) == -ETIMEDOUT);
    assert(metadata_calls == 3);
}

int main(void)
{
    assert(fesetround(FE_TONEAREST) == 0);
    test_mode();
    test_associated_acquisition();
    test_build();
    test_grammar_and_queries();
    test_native_downloader();
    return 0;
}
#endif
