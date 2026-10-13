/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "selectors.h"
#include "../clock.h"

#include <errno.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <string.h>
#include "../ioctl_request.h"

_Static_assert(sizeof(uintptr_t) == 8, "B4.1 acquisition requires a 64-bit mapping");

static uint32_t read32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static int association_valid(const struct b41_library_association *image)
{
    return image && image->base && image->extent == B41_LIBRARY_IMAGE_END &&
        image->base <= UINTPTR_MAX - image->extent &&
        image->xml_global == image->base + 0x7178b8u &&
        image->chip_global == image->base + 0x6f2dacu;
}

int b41_bootstrap_chip_read(const struct b41_library_association *image,
    const char *chip, const char *adie, uint32_t hw, uint32_t sw,
    struct b41_bootstrap_chip *out)
{
    struct b41_bootstrap_chip result = {0};
    uintptr_t table;
    int status;

    if (!image || !chip || !adie || !out) return -EINVAL;
    if (!association_valid(image)) return -ERANGE;
    status = b41_capability_branch_read(image, chip, adie, hw, sw,
        &result.capability);
    if (status) return status;
    result.context_chip_30 = read32(result.capability.capability + 0x14);
    result.capabilities = read32(result.capability.capability + 0x18);
    result.navigation_mode_base = read32(result.capability.capability + 8);
    result.secure_download_default =
        (uint8_t)((result.capabilities & UINT32_C(0x0ffffff0)) > 0x30fu);
    memcpy(&table, (const void *)(image->base + 0x6e7b00u), sizeof(table));
    if (table != image->base + 0x6ee1a8u) return -ESTALE;
    result.profile_selector_717cb6 = 1;
    for (unsigned i = 0; i < 50; ++i) {
        uint8_t row[8];
        memcpy(row, (const void *)(table + 8u * i), sizeof(row));
        if (read32(row + 4) == result.context_chip_30) {
            result.profile_selector_717cb6 = (uint8_t)read32(row);
            break;
        }
    }
    *out = result;
    return 0;
}

static int secondary_feature(const uint8_t *name, size_t size, int32_t fd,
    unsigned *feature)
{
    const uint8_t *end;
    size_t bounded = size < 662u ? size : 662u;

    if (!name || !size) return -ENODATA;
    end = memchr(name, 0, bounded);
    if (!end) return size < 662u ? -ENODATA : -EBADMSG;
    *feature = (unsigned)(end - name > 4 && fd != -1);
    return 0;
}

int b41_bootstrap_mode_build(uint32_t input, uint32_t chip, uint8_t profile,
    const uint8_t *name, size_t size, int32_t fd, struct b41_bootstrap_mode *out)
{
    struct b41_bootstrap_mode result;
    uint8_t mode = (uint8_t)input, setting = 0, flags = 0;
    unsigned feature;
    int status;

    if (!out) return -EINVAL;
    /* 5ccac0/5ccc74 normalize unsupported modes before either store. */
    if (mode > 11u ||
        (profile <= 1u && mode != 2u && mode != 3u && mode != 6u &&
         mode != 10u && mode != 11u) ||
        (profile <= 2u && mode == 2u) ||
        (profile <= 3u && mode == 6u) ||
        (profile < 5u && mode == 10u) ||
        (profile <= 4u && mode == 11u)) {
        mode = profile == 1u ? 3u : 6u;
        setting = profile == 1u ? 5u : 0x17u;
        flags = profile == 1u ? 1u : 0x3fu;
    } else {
        switch (mode) {
        case 0: setting = 3; flags = 3; break;
        case 1: setting = 6; flags = 0x31; break;
        case 2: mode = 2; setting = 7; flags = 0x33; break;
        case 3: setting = 5; flags = 1; break;
        case 4: setting = 0x17; flags = 0x30; break;
        case 5: setting = 3; flags = 2; break;
        case 6: mode = 6; setting = 0x17; flags = 0x3f; break;
        case 7: setting = 3; flags = 0x0d; break;
        case 8: setting = 3; flags = 0x0f; break;
        case 9: setting = 3; flags = 0x0c; break;
        case 10:
        case 11:
            status = secondary_feature(name, size, fd, &feature);
            if (status) return status;
            if (mode == 10u && !feature && chip != UINT32_C(0xffff6789)) {
                mode = 6; setting = 0x17; flags = 0x3f;
            } else {
                setting = 0x27;
                flags = mode == 10u ? 0x7fu : 0x7eu;
                if (mode == 11u && !feature && chip == UINT32_C(0xffff6789)) {
                    setting = 0x17; flags = 0x3e;
                }
            }
            break;
        default: return -EOPNOTSUPP;
        }
    }
    result.mode_75c990 = mode;
    result.setting_717cb7 = setting;
    result.flags_717cb8 = flags;
    result.clock_717cb3 = (uint8_t)((flags >> 1) & 2u);
    *out = result;
    return 0;
}

static int observe_once(const struct b41_library_association *image,
    struct b41_bootstrap_observation *out)
{
    static const struct { uintptr_t got, target; } bindings[] = {
        {0x6e6660u, 0x7178b8u}, {0x6e6618u, 0x717cb0u},
        {0x6e6668u, 0x717cb3u}, {0x6e6670u, 0x717cb6u},
        {0x6e6650u, 0x717cb7u}, {0x6e6658u, 0x717cb8u},
        {0x6e6688u, 0x7178b0u},
    };
    const volatile uint8_t *base = (const volatile uint8_t *)image->base;
    uint8_t word[4];

    for (unsigned i = 0; i < sizeof(bindings) / sizeof(bindings[0]); ++i) {
        uintptr_t target;
        memcpy(&target, (const void *)(image->base + bindings[i].got), sizeof(target));
        if (target != image->base + bindings[i].target) return -ESTALE;
    }
    memset(out, 0, sizeof(*out));
    out->route.secure_download_7178b8_33e = base[0x7178b8u + 0x33eu];
    out->route.dsp_selector_717cb0 = base[0x717cb0u];
    out->clock_selector_717cb3 = base[0x717cb3u];
    out->profile_selector_717cb6 = base[0x717cb6u];
    out->setting_717cb7 = base[0x717cb7u];
    out->feature_flags_717cb8 = base[0x717cb8u];
    for (unsigned i = 0; i < 4; ++i) word[i] = base[0x7178b0u + i];
    out->word_7178b0 = read32(word);
    return 0;
}

int b41_bootstrap_observe(const struct b41_library_association *image,
    struct b41_bootstrap_observation *out)
{
    struct b41_bootstrap_observation first, second;
    int status;

    if (!image || !out) return -EINVAL;
    if (!association_valid(image)) return -ERANGE;
    status = observe_once(image, &first);
    if (status) return status;
    status = observe_once(image, &second);
    if (status) return status;
    if (memcmp(&first, &second, sizeof(first))) return -EAGAIN;
    *out = first;
    return 0;
}

static void write16(uint8_t *p, uint32_t word)
{
    p[0] = (uint8_t)word;
    p[1] = (uint8_t)(word >> 8);
}

static int known(const struct b41_first_config *first, unsigned start, unsigned count)
{
    for (unsigned i = 0; i < count; ++i)
        if (first->provenance[start+i] == B41_FIRST_UNKNOWN) return 0;
    return 1;
}

int b41_native_l1_identity_select(uint32_t hardware_chip, uint32_t gps_adie,
    struct b41_native_l1_identity *out)
{
    struct b41_native_l1_identity result = {0};
    if (!out) return -EINVAL;
    if (hardware_chip != 0x6878u) return -EOPNOTSUPP;
    /* 6ed7d0/6ed960/6edaf0: only needed immutable policy fields are copied,
     * not a fabricated complete capability/context object.
     */
    switch (gps_adie) {
    case 0x6631u: result.navigation_mode_base = 6; break;
    case 0x6637u: case 0x6686u: result.navigation_mode_base = 10; break;
    default: return -ENODEV;
    }
    result.hardware_chip = hardware_chip;
    result.gps_adie = gps_adie;
    result.context_chip_30 = UINT32_C(0xffff6878);
    result.capabilities = 0x370;
    result.profile_selector_717cb6 = 5;
    result.secure_download_default =
        (uint8_t)((result.capabilities & UINT32_C(0x0ffffff0)) > 0x30fu);
    *out = result;
    return 0;
}

int b41_native_l1_nominal_build(const struct b41_native_l1_identity *chip,
    const struct b41_first_config *first, int clock11, int clock30,
    struct b41_native_l1_nominal *out)
{
    static const uint8_t no_secondary[] = "";
    struct b41_native_l1_nominal result = {0};
    struct b41_mvcd_clock_fields clock;
    struct b41_native_l1_identity expected;
    uint8_t mode;
    int status;

    if (!chip || !first || !out) return -EINVAL;
    if (clock11 < 0) return clock11;
    if (clock30 < 0) return clock30;
    if (clock11 != 0x21 || clock30 != 0) return -EOPNOTSUPP;
    if (chip->context_chip_30 != UINT32_C(0xffff6878) ||
        chip->profile_selector_717cb6 != 5 || !chip->secure_download_default)
        return -EOPNOTSUPP;
    status = b41_native_l1_identity_select(chip->hardware_chip, chip->gps_adie, &expected);
    if (status) return status;
    if (chip->context_chip_30 != expected.context_chip_30 ||
        chip->capabilities != expected.capabilities ||
        chip->navigation_mode_base != expected.navigation_mode_base ||
        chip->profile_selector_717cb6 != expected.profile_selector_717cb6 ||
        chip->secure_download_default != expected.secure_download_default)
        return -ESTALE;
    if (!known(first, 0x13, 1) || !known(first, 0x18, 4) ||
        !known(first, 0x1c, 4) || !known(first, 0x24, 1) || !known(first, 0x54, 4))
        return -ENODATA;
    if (first->bytes[0x13] != 0xfe || read32(first->bytes + 0x18) != 26000000u ||
        read32(first->bytes + 0x1c) != 115200u)
        return -EOPNOTSUPP;

    /* Mode3 selects flags1 without evaluating OEM secondary state. The native
     * owner intentionally has no secondary transport; it owns this policy.
     */
    status = b41_bootstrap_mode_build(3, chip->context_chip_30,
        chip->profile_selector_717cb6, NULL, 0, -1, &result.navigation);
    if (status) return status;
    result.selectors.secure_download_7178b8_33e = chip->secure_download_default;
    result.selectors.dsp_selector_717cb0 = 0; /* Primary normal MVCD, not CW. */
    result.inputs.context_mode_13 = first->bytes[0x13];
    result.inputs.context_hz_18 = read32(first->bytes + 0x18);
    result.inputs.context_baud_1c = read32(first->bytes + 0x1c);
    result.inputs.context_profile_24 = first->bytes[0x24];
    result.inputs.context_chip_30 = chip->context_chip_30;
    result.inputs.context_lna_54 = read32(first->bytes + 0x54);
    result.inputs.clock_selector_717cb3 = result.navigation.clock_717cb3;
    result.inputs.profile_selector_717cb6 = chip->profile_selector_717cb6;
    result.inputs.setting_717cb7 = 0x27; /* 4f283c/44: profile>=5 download mutation. */
    result.inputs.feature_flags_717cb8 = result.navigation.flags_717cb8;
    result.inputs.feature_name = no_secondary;
    result.inputs.feature_name_size = sizeof(no_secondary);
    result.inputs.secondary_fd_6edeec = -1;
    /* Native initial auxiliary word0; no timesync/legacy ioctl29 producer. */
    result.inputs.word_7178b0 = 0;
    result.inputs.private_clock = NULL;

    mode = result.inputs.clock_selector_717cb3;
    if (result.inputs.context_profile_24 == 1) mode = (uint8_t)(mode | 4u);
    /* Explicit NOMINAL choice: call pure synthesis at physical Hz, retaining
     * the FE wire marker. Never invoke 5523c0 or construct checksum records.
     */
    status = b41_mvcd_clock_synthesize(result.inputs.context_hz_18, mode, &clock);
    if (status) return status;
    result.fields.effective_hz = result.inputs.context_hz_18;
    result.fields.clock_mode = mode;
    write16(result.fields.baud_and_parameters + 2, clock.parameter_a);
    write16(result.fields.baud_and_parameters + 4, clock.parameter_b);
    memcpy(result.fields.synthesis_and_profile, clock.synthesis, sizeof(clock.synthesis));
    result.fields.synthesis_and_profile[28] = 7;
    result.fields.synthesis_and_profile[30] = 1; /* Actual FE/COTMS marker. */
    result.fields.effective_setting_717cb7 = 0x27;
    write16(result.fields.board_tail + 2, chip->context_chip_30);
    result.fields.board_tail[4] = (uint8_t)result.inputs.context_lna_54;
    result.fields.board_tail[5] = 10;
    result.fields.board_tail[8] = 1; /* Intentionally disabled secondary. */
    result.fields.board_tail[10] = 0x4e;
    result.fields.board_tail[11] = 0x4f;
    *out = result;
    return 0;
}

static int overlaps(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !an || !bn) return 0;
    return x <= y ? y-x < an : x-y < bn;
}

static int validate(const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session, const struct b41_bootstrap_query *query)
{
    const struct b41_bootstrap_boot_info *info;
    if (!policy || !session || !query) return B41_BOOTSTRAP_MISSING;
    if (session->fields != &policy->inputs || session->gps0_fd < 0 ||
        query->session != session || query->gps0_fd != session->gps0_fd ||
        session->selectors.secure_download_7178b8_33e != 1 ||
        session->selectors.dsp_selector_717cb0 != 0 ||
        memcmp(&session->selectors, &policy->selectors, sizeof(policy->selectors)) ||
        memcmp(&query->selectors, &policy->selectors, sizeof(policy->selectors)))
        return B41_BOOTSTRAP_SESSION;
    if (query->command != 23) return B41_BOOTSTRAP_QUERY;
    if (query->status < 0) return query->status;
    if (query->status) return B41_BOOTSTRAP_QUERY;
    if (!query->info || query->bytes_returned != sizeof(*query->info))
        return B41_BOOTSTRAP_MISSING;
    info = query->info;
    if (!info->code_size || info->code_size > UINT16_MAX ||
        info->start_addr > UINT16_MAX || info->exec_addr > UINT16_MAX ||
        info->cipher_key > UINT16_MAX || !info->frag_num || info->frag_num-1u > 256u)
        return B41_BOOTSTRAP_METADATA;
    return 0;
}

static int input_overlap(const void *out, size_t size,
    const struct b41_native_l1_nominal *policy, const struct b41_bootstrap_session *session,
    const struct b41_bootstrap_query *query)
{
    return overlaps(out, size, policy, sizeof(*policy)) ||
        overlaps(out, size, session, sizeof(*session)) ||
        overlaps(out, size, query, sizeof(*query)) ||
        overlaps(out, size, query->info, sizeof(*query->info));
}

static void assemble(const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_query *query, uint8_t payload[B41_MVCD_BOOTSTRAP_SIZE])
{
    /* 27934/4f35e8: exact decoded26MHz row, not private clock calibration. */
    static const uint16_t profile[16] = {
        40, 255, 128, 71, 100, 80, 216, 80, 187, 3, 60, 111, 137, 136, 2, 251
    };
    memset(payload, 0, B41_MVCD_BOOTSTRAP_SIZE);
    write16(payload, 0x1a);
    memcpy(payload + 4, policy->fields.baud_and_parameters, 6);
    write16(payload + 14, query->info->code_size);
    write16(payload + 16, query->info->start_addr);
    write16(payload + 18, query->info->exec_addr);
    write16(payload + 20, query->info->cipher_key);
    write16(payload + 22, query->info->frag_num);
    payload[28] = 5;
    memcpy(payload + 30, policy->fields.synthesis_and_profile, 32);
    for (unsigned i = 0; i < 16; ++i) write16(payload + 62u + 2u*i, profile[i]);
    memcpy(payload + 94, policy->fields.board_tail, 12);
}

static void forget(uint8_t *p, size_t size)
{
    volatile uint8_t *private_bytes = p;
    while (size--) *private_bytes++ = 0;
}

int b41_native_l1_nominal_payload_build(const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session, const struct b41_bootstrap_query *query,
    uint8_t *payload, size_t capacity)
{
    uint8_t temporary[B41_MVCD_BOOTSTRAP_SIZE];
    int status;
    if (!payload) return B41_BOOTSTRAP_ARGUMENT;
    if (capacity < sizeof(temporary)) return B41_BOOTSTRAP_CAPACITY;
    status = validate(policy, session, query);
    if (status) return status;
    if (input_overlap(payload, sizeof(temporary), policy, session, query))
        return B41_BOOTSTRAP_OVERLAP;
    assemble(policy, query, temporary);
    memcpy(payload, temporary, sizeof(temporary));
    forget(temporary, sizeof(temporary));
    return 0;
}

int b41_native_l1_nominal_frame_build(const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session, const struct b41_bootstrap_query *query,
    uint8_t *frame, size_t capacity, size_t *written)
{
    uint8_t temporary[B41_MVCD_BOOTSTRAP_SIZE];
    int status;
    if (!frame || !written) return B41_BOOTSTRAP_ARGUMENT;
    if (capacity < B41_MVCD_BOOTSTRAP_FRAME_SIZE) return B41_BOOTSTRAP_CAPACITY;
    status = validate(policy, session, query);
    if (status) return status;
    if (input_overlap(frame, B41_MVCD_BOOTSTRAP_FRAME_SIZE, policy, session, query) ||
        input_overlap(written, sizeof(*written), policy, session, query) ||
        overlaps(frame, B41_MVCD_BOOTSTRAP_FRAME_SIZE, written, sizeof(*written)))
        return B41_BOOTSTRAP_OVERLAP;
    assemble(policy, query, temporary);
    status = b41_mvcd_encode_bootstrap(temporary, sizeof(temporary), frame, capacity, written);
    forget(temporary, sizeof(temporary));
    return status;
}

int b41_native_l1_download_begin(struct b41_download *owner,
    const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session, const struct b41_bootstrap_query *query,
    uint64_t now_ns, uint64_t deadline_ns)
{
    uint8_t frame[B41_MVCD_BOOTSTRAP_FRAME_SIZE];
    size_t size = 0;
    int status;
    if (!owner || !policy || !session || !query || !query->info) return -EINVAL;
    if (owner->stage != B41_DOWNLOAD_NEW)
        return owner->stage == B41_DOWNLOAD_FAILED ? owner->first_error : -EALREADY;
    if (input_overlap(owner, sizeof(*owner), policy, session, query)) return -EINVAL;
    if (now_ns >= deadline_ns) return b41_download_abort(owner, -ETIMEDOUT);
    status = b41_native_l1_nominal_frame_build(policy, session, query, frame, sizeof(frame), &size);
    if (status) {
        forget(frame, sizeof(frame));
        return b41_download_abort(owner, status);
    }
    owner->session = session;
    owner->gps0_fd = session->gps0_fd;
    owner->selectors = session->selectors;
    owner->fragment_count = query->info->frag_num;
    owner->fragment_sequence = 1;
    owner->deadline_ns = deadline_ns;
    owner->last_now_ns = now_ns;
    memcpy(owner->tx, frame, size);
    owner->tx_size = size;
    owner->stage = B41_DOWNLOAD_BOOTSTRAP_TX;
    forget(frame, sizeof(frame));
    return 0;
}

static int native_now(uint64_t *now)
{
    struct timespec time;
    if (clock_gettime(CLOCK_MONOTONIC, &time)) return -errno;
    if (time.tv_sec < 0 || time.tv_nsec < 0 || time.tv_nsec >= 1000000000L ||
        (uint64_t)time.tv_sec > (UINT64_MAX-(uint64_t)time.tv_nsec)/1000000000u)
        return -EOVERFLOW;
    *now = (uint64_t)time.tv_sec*1000000000u + (uint64_t)time.tv_nsec;
    return 0;
}

int b41_native_l1_download_linux_begin(struct b41_download *owner,
    const struct b41_native_l1_nominal *policy,
    const struct b41_bootstrap_session *session, uint64_t deadline_ns)
{
    struct b41_bootstrap_boot_info info = {0};
    struct b41_bootstrap_query query = {0};
    struct stat st;
    uint64_t now;
    int flags, status;
    if (!owner || !policy || !session) return -EINVAL;
    if (owner->stage != B41_DOWNLOAD_NEW)
        return owner->stage == B41_DOWNLOAD_FAILED ? owner->first_error : -EALREADY;
    if (overlaps(owner, sizeof(*owner), policy, sizeof(*policy)) ||
        overlaps(owner, sizeof(*owner), session, sizeof(*session))) return -EINVAL;
    if (session->fields != &policy->inputs ||
        session->selectors.secure_download_7178b8_33e != 1 ||
        session->selectors.dsp_selector_717cb0 != 0)
        return b41_download_abort(owner, -EINVAL);
    flags = fcntl(session->gps0_fd, F_GETFL);
    if (flags < 0) return b41_download_abort(owner, -errno);
    if ((flags & O_ACCMODE) != O_RDWR || !(flags & O_NONBLOCK))
        return b41_download_abort(owner, -EINVAL);
    if (fstat(session->gps0_fd, &st)) return b41_download_abort(owner, -errno);
    if (!S_ISCHR(st.st_mode)) return b41_download_abort(owner, -ENODEV);
    status = native_now(&now);
    if (status) return b41_download_abort(owner, status);
    if (now >= deadline_ns) return b41_download_abort(owner, -ETIMEDOUT);
    status = ioctl(session->gps0_fd, 23UL, &info);
    if (status < 0) status = -errno;
    if (!status) {
        query.session = session;
        query.gps0_fd = session->gps0_fd;
        query.selectors = session->selectors;
        query.command = 23;
        query.info = &info;
        query.bytes_returned = sizeof(info);
        status = native_now(&now);
        if (!status) status = b41_native_l1_download_begin(owner, policy, session,
            &query, now, deadline_ns);
    }
    forget((uint8_t *)&info, sizeof(info));
    forget((uint8_t *)&query, sizeof(query));
    return status ? b41_download_abort(owner, status) : 0;
}

#ifdef B41_NATIVE_L1_RUNNER
#include "../download_linux.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>

static volatile sig_atomic_t interrupted;

static void stop_attempt(int signal_number)
{
    (void)signal_number;
    interrupted = 1;
}

static void first_word(struct b41_first_config *first, unsigned offset,
    uint32_t value, unsigned count, uint8_t provenance)
{
    for (unsigned i = 0; i < count; ++i) {
        first->bytes[offset+i] = (uint8_t)(value >> (8u*i));
        first->provenance[offset+i] = provenance;
    }
    first->unresolved_bytes = 0;
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i)
        first->unresolved_bytes += first->provenance[i] == B41_FIRST_UNKNOWN;
}

static int profile_read(const char *path, struct b41_first_config *first,
    uint16_t *interval, uint8_t *nv_mode)
{
    struct stat st;
    uint8_t name_first, numeric[10];
    int fd, status = 0;
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return -errno;
    if (fstat(fd, &st)) status = -errno;
    else if (!S_ISREG(st.st_mode) || st.st_size != 54) status = -EMSGSIZE;
    /* Read only the allowed public profile fields. Never read calibration36..51
     * or invent a full logical52-byte record from an incomplete acquisition.
     */
    if (!status) {
        ssize_t count = pread(fd, &name_first, 1, 0);
        if (count < 0) status = -errno;
        else if (count != 1) status = -EMSGSIZE;
    }
    if (!status) {
        ssize_t count = pread(fd, numeric, sizeof(numeric), 24);
        if (count < 0) status = -errno;
        else if (count != (ssize_t)sizeof(numeric)) status = -EMSGSIZE;
        else if (!name_first) status = -ENODATA;
    }
    if (close(fd) && !status) status = -errno;
    if (status) return status;
    memset(first, 0, sizeof(*first));
    first->xml_policy_missing = 1;
    first->missing_inputs = B41_FIRST_CLOCK_QUERY | B41_FIRST_LNA_QUERY |
        B41_FIRST_MODEM_QUERY | B41_FIRST_CALIBRATION | B41_FIRST_TRANSPORT |
        B41_FIRST_XML_ASSET;
    *interval = (uint16_t)((uint16_t)numeric[4] | ((uint16_t)numeric[5] << 8));
    if (!*interval) *interval = 2000;
    *nv_mode = numeric[8];
    first_word(first, 0x14, *interval, 2, B41_FIRST_NVRAM_PROFILE);
    first_word(first, 0x18, read32(numeric), 4, B41_FIRST_NVRAM_PROFILE);
    first_word(first, 0x24, numeric[9], 1, B41_FIRST_NVRAM_PROFILE);
    first_word(first, 0x1c, 115200, 4, B41_FIRST_CONSTANT);
    forget(numeric, sizeof(numeric));
    return 0;
}

static int scalar_query(int fd, uint32_t command, unsigned long argument)
{
    int result = ioctl(fd, b41_ioctl_request(command), argument);
    return result < 0 ? -errno : result;
}

int main(int argc, char **argv)
{
    struct b41_native_l1_identity chip;
    struct b41_first_config first;
    struct b41_native_l1_nominal policy;
    struct b41_bootstrap_session session = {0};
    struct b41_download owner = {0};
    struct sigaction action = {0};
    uint64_t now = 0, deadline;
    uint32_t auxiliary = 0, lna = 0;
    uint16_t interval = 0;
    uint8_t nv_mode = 0;
    unsigned long timeout_ms = 5000;
    int conn_fd = -1, gps_fd = -1, hw, adie, clock11, clock30;
    int aux_status = 0, lna_status = 0, status;

    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("usage: gnss-l1-nominal GPS_PHYSICAL_PROFILE [TIMEOUT_MS:1..30000]");
        return 0;
    }
    if (argc < 2 || argc > 3 || !argv[1][0] || argv[1][0] == '-') return 2;
    if (argc == 3) {
        char *end;
        if (!argv[2][0] || strspn(argv[2], "0123456789") != strlen(argv[2])) return 2;
        errno = 0;
        timeout_ms = strtoul(argv[2], &end, 10);
        if (errno || !argv[2][0] || *end || timeout_ms < 1 || timeout_ms > 30000) return 2;
    }
    status = native_now(&now);
    if (status) goto done;
    if (now > UINT64_MAX - (uint64_t)timeout_ms*1000000u) { status = -EOVERFLOW; goto done; }
    deadline = now + (uint64_t)timeout_ms*1000000u;
    action.sa_handler = stop_attempt;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) {
        status = -errno; goto done;
    }
    action.sa_handler = SIG_DFL;
    if (sigaction(SIGALRM, &action, NULL)) { status = -errno; goto done; }
    /* Default SIGALRM terminates a stuck syscall without restarting/resetting
     * the device. A kernel-uninterruptible stall still needs external recovery.
     */
    alarm((unsigned int)((timeout_ms + 999u)/1000u + 2u));
    status = profile_read(argv[1], &first, &interval, &nv_mode);
    if (status) goto done;
    conn_fd = open("/dev/conninfra_dev", O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (conn_fd < 0) { status = -errno; goto done; }
    hw = scalar_query(conn_fd, 0x8004c200UL, 0UL);
    if (hw < 0) { status = hw; goto done; }
    adie = scalar_query(conn_fd, 0x8004c203UL, 2UL); /* Actual GPS radio selector. */
    if (adie < 0) { status = adie; goto done; }
    status = b41_native_l1_identity_select((uint32_t)hw, (uint32_t)adie, &chip);
    if (status) goto done;
    if (close(conn_fd)) { conn_fd = -1; status = -errno; goto done; }
    conn_fd = -1;
    status = native_now(&now);
    if (status) goto done;
    if (interrupted || now >= deadline) { status = interrupted ? -EINTR : -ETIMEDOUT; goto done; }
    /* Pinned gps_each_device_open rejects a second open with EBUSY. There is
     * exactly one fresh open and no secondary descriptor, reset or reopen.
     */
    gps_fd = open("/dev/gpsdl0", O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (gps_fd < 0) { status = -errno; goto done; }
    clock11 = scalar_query(gps_fd, 11UL, 0UL);
    if (clock11 < 0) { status = clock11; goto done; }
    clock30 = scalar_query(gps_fd, 30UL, 0UL);
    if (clock30 < 0) { status = clock30; goto done; }
    if (clock11 != 33 || clock30 != 0) { status = -EOPNOTSUPP; goto done; }
    first_word(&first, 0x13, clock11 == 33 ? 0xfeu : 0xffu, 1, B41_FIRST_CLOCK_RESULT);
    first.missing_inputs &= ~(unsigned)B41_FIRST_CLOCK_QUERY;
    /* Exact unsupported legacy outputs are retained as failed queries. Stock
     * initialized these buffers to0; that is a native initial wire value,
     * never successful HW-version/timesync/LNA discovery.
     */
    lna_status = ioctl(gps_fd, 16UL, &lna);
    if (lna_status < 0) lna_status = -errno;
    if (lna_status && (lna_status != -EFAULT || lna)) {
        status = lna_status < 0 ? lna_status : -EPROTO; goto done;
    }
    first_word(&first, 0x54, lna, 4,
        (uint8_t)(lna_status ? B41_FIRST_CONSTANT : B41_FIRST_LNA_RESULT));
    if (!lna_status) first.missing_inputs &= ~(unsigned)B41_FIRST_LNA_QUERY;
    aux_status = ioctl(gps_fd, 29UL, &auxiliary);
    if (aux_status < 0) aux_status = -errno;
    if (aux_status != -EFAULT || auxiliary) {
        status = aux_status < 0 ? aux_status : -EOPNOTSUPP; goto done;
    }
    status = b41_native_l1_nominal_build(&chip, &first, clock11, clock30, &policy);
    if (status) goto done;
    printf("chip=0x%x gps_adie=0x%x hz=%u interval=%u nv_mode=%u profile=%u "
        "clock11=%d clock30=%d ioctl16_status=%d ioctl29_status=%d policy=nominal-L1-MVCD\n",
        (unsigned)hw, (unsigned)adie, (unsigned)policy.inputs.context_hz_18,
        (unsigned)interval, (unsigned)nv_mode, (unsigned)policy.inputs.context_profile_24,
        clock11, clock30, lna_status, aux_status);
    session.gps0_fd = gps_fd;
    session.fields = &policy.inputs;
    session.selectors = policy.selectors;
    status = b41_native_l1_download_linux_begin(&owner, &policy, &session, deadline);
    while (!status && owner.stage != B41_DOWNLOAD_ACKS_COMPLETE) {
        struct timespec idle = {0, 1000000};
        if (interrupted) { status = b41_download_abort(&owner, -EINTR); break; }
        status = b41_download_linux_step(&owner);
        if (!status && owner.stage != B41_DOWNLOAD_ACKS_COMPLETE && nanosleep(&idle, NULL))
            status = b41_download_abort(&owner, -errno);
    }
    if (!status) puts("matched ACKs complete; RAM_CODE_READY/WORKING/fix not established");
done:
    forget(owner.tx, sizeof(owner.tx));
    forget(owner.rx, sizeof(owner.rx));
    if (gps_fd >= 0 && close(gps_fd) && !status) status = -errno;
    if (conn_fd >= 0 && close(conn_fd) && !status) status = -errno;
    alarm(0);
    if (status) fprintf(stderr, "attempt_failed status=%d stage=%d\n", status, (int)owner.stage);
    return status ? 1 : 0;
}
#endif
