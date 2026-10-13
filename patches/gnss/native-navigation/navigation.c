/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "navigation.h"
#include <errno.h>
#include <float.h>
#include <math.h>
#include <string.h>
#include <time.h>

_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 && FLT_RADIX == 2, "binary64 ABI");
_Static_assert(sizeof(float) == 4 && FLT_MANT_DIG == 24, "binary32 ABI");

static uint16_t le16(const uint8_t *p)
{ return (uint16_t)((uint16_t)p[0] | (uint16_t)((uint16_t)p[1] << 8)); }
static uint32_t le32(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint32_t half_le(const uint8_t *p)
{ return (uint32_t)le16(p) << 16 | (uint32_t)le16(p + 2); }
static uint32_t half_be(const uint8_t *p)
{ return (uint32_t)p[2] << 24 | (uint32_t)p[3] << 16 | (uint32_t)p[0] << 8 | (uint32_t)p[1]; }
static void put16(uint8_t *p, uint16_t v)
{ p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v)
{ for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8u*i)); }
static void put64(uint8_t *p, uint64_t v)
{ for (unsigned i = 0; i < 8; ++i) p[i] = (uint8_t)(v >> (8u*i)); }
static double double_le(const uint8_t *p)
{
    uint64_t bits = 0; double value;
    for (unsigned i = 0; i < 8; ++i) bits |= (uint64_t)p[i] << (8u*i);
    memcpy(&value, &bits, sizeof(value));
    return value;
}
static float float_le(const uint8_t *p)
{
    uint32_t bits = le32(p); float value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}
static int overlap(const void *a, size_t n, const void *b, size_t m)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return x <= y ? y-x < n : x-y < m;
}

int b41_nav_packet_decode(const uint8_t *wire, size_t size, struct b41_nav_packet *out)
{
    uint8_t body[B41_NAV_PAYLOAD_MAX + 6u];
    struct b41_nav_packet result = {0};
    size_t count = 0;
    uint32_t sum = 0;
    uint16_t length;
    if (!wire || !out) return -EINVAL;
    if (size < 10 || size > B41_NAV_WIRE_MAX) return -EMSGSIZE;
    if (wire[0] != 0xaa || wire[1] != 0xf0 || wire[size-2] != 0xaa || wire[size-1] != 0x0f)
        return -EPROTO;
    for (size_t i = 2; i < size-2; ++i) {
        uint8_t value = wire[i];
        if (value == 0xaa) return -EPROTO;
        if (value == 0xde) {
            if (++i >= size-2) return -EPROTO;
            if (wire[i] == 0xdf) value = 0xaa;
            else if (wire[i] == 0xe0) value = 0xde;
            else return -EPROTO;
        }
        if (count == sizeof(body)) return -EMSGSIZE;
        body[count++] = value;
    }
    if (count < 6 || body[3] != 0xfe) return -EPROTO;
    length = le16(body);
    if ((length & 0xfffu) < 4u) return -EPROTO;
    result.payload_size = (uint16_t)((length & 0xfffu) - 4u);
    if (count != (size_t)result.payload_size + 6u) return -EMSGSIZE;
    for (size_t i = 0; i < count-2; ++i) sum += body[i];
    if (le16(body + count-2) != (uint16_t)sum) return -EBADMSG;
    result.command = body[2];
    result.length_high_nibble = (uint8_t)(length >> 12);
    memcpy(result.payload, body + 4, result.payload_size);
    *out = result;
    return 0;
}

static int fail(struct b41_nav_epoch_owner *owner, int error)
{
    if (!owner->first_error) owner->first_error = error;
    return owner->first_error;
}
int b41_nav_epoch_init(struct b41_nav_epoch_owner *owner, uint64_t now_ns, uint64_t deadline_ns)
{
    struct b41_nav_epoch_owner result = {0};
    if (!owner) return -EINVAL;
    if (owner->first_error) return owner->first_error;
    if (owner->deadline_ns || owner->active) return -EALREADY;
    if (now_ns >= deadline_ns) return -ETIMEDOUT;
    result.deadline_ns = deadline_ns; result.last_ns = now_ns;
    *owner = result;
    return 0;
}

int b41_nav_epoch_accept(struct b41_nav_epoch_owner *owner, const struct b41_nav_packet *packet,
                        uint64_t now_ns, struct b41_nav_epoch *complete)
{
    unsigned size, maximum;
    struct b41_nav_record *record;
    const uint8_t *p;
    if (!owner || !packet || !complete || overlap(owner, sizeof(*owner), packet, sizeof(*packet)) ||
        overlap(owner, sizeof(*owner), complete, sizeof(*complete))) return -EINVAL;
    if (owner->first_error) return owner->first_error;
    if (now_ns < owner->last_ns) return fail(owner, -ESTALE);
    if (now_ns >= owner->deadline_ns) return fail(owner, -ETIMEDOUT);
    switch (packet->command) {
    case 0x2c: size = 66; maximum = 0; break;
    case 0x4c: size = 10; maximum = 0; break;
    case 0x2b: size = 46; maximum = 11; break;
    case 0x3b: size = 14; maximum = 12; break;
    case 0x41: size = 32; maximum = 11; break;
    case 0x4b: size = 47; maximum = 15; break;
    case 0x4d: size = 47; maximum = 20; break;
    case 0x5c: size = 113; maximum = 17; break;
    case 0x91: size = 115; maximum = 11; break;
    default: return fail(owner, -EOPNOTSUPP);
    }
    if (packet->payload_size != size) return fail(owner, -EMSGSIZE);
    if (packet->command == 0x2c ? owner->active != 0 : owner->active != 1)
        return fail(owner, -EPROTO);
    owner->last_ns = now_ns;
    p = packet->payload;
    if (packet->command == 0x2c) {
        memset(&owner->pending, 0, sizeof(owner->pending));
        memcpy(owner->pending.header, p, size);
        owner->pending.header_word0 = half_le(p);
        owner->pending.header_word4 = half_le(p + 4);
        owner->pending.header_field8_9_44 = (uint32_t)p[8] << 2 | (uint32_t)p[9] << 10 | (p[44] & 3u);
        owner->pending.begin_ns = now_ns;
        owner->active = 1;
        return 0;
    }
    if (packet->command == 0x4c) {
        owner->pending.end.byte0 = p[0]; owner->pending.end.byte9 = p[9];
        owner->pending.end.word1 = half_le(p + 1);
        owner->pending.end.word5 = half_le(p + 5);
        owner->pending.end_ns = now_ns;
        *complete = owner->pending;
        owner->active = 0;
        return 1;
    }
    /* The source index is SHARED across these record commands, not a separate
     * per-constellation counter. Never fill omitted/short records with zeros.
     */
    if (owner->pending.count >= maximum || owner->pending.count >= B41_NAV_EPOCH_RECORDS)
        return fail(owner, -EOVERFLOW);
    record = &owner->pending.records[owner->pending.count];
    record->command = packet->command; record->index = owner->pending.count;
    record->size = (uint8_t)size;
    memcpy(record->wire, p, size);
    if (packet->command == 0x41) {
        record->decoded.fe41.byte0 = p[0]; record->decoded.fe41.byte1 = p[1];
        record->decoded.fe41.byte2 = p[2]; record->decoded.fe41.byte3 = p[3];
        for (unsigned i = 0; i < 7; ++i) record->decoded.fe41.words[i] = half_be(p + 4u + 4u*i);
    } else if (packet->command == 0x4d) {
        record->decoded.fe4d.prefix24 = (uint32_t)p[0] << 16 | (uint32_t)p[1] | (uint32_t)p[2] << 8;
        record->decoded.fe4d.byte3 = p[3]; record->decoded.fe4d.byte4 = p[4];
        record->decoded.fe4d.byte5 = p[5]; record->decoded.fe4d.byte6 = p[6];
        for (unsigned i = 0; i < 10; ++i) record->decoded.fe4d.words[i] = half_le(p + 7u + 4u*i);
    }
    owner->pending.count++;
    return 0;
}

int b41_nav_post_init_reporting_encode(uint8_t *wire, size_t capacity, size_t *written)
{
    static const uint8_t frame[15] = {0xaa, 0xf0, 9, 0, 5, 0xfe, 0x32, 0, 0, 1, 0, 0x3f, 1, 0xaa, 0x0f};
    if (!wire || !written || overlap(wire, sizeof(frame), written, sizeof(*written))) return -EINVAL;
    if (capacity < sizeof(frame)) return -ENOSPC;
    memcpy(wire, frame, sizeof(frame)); *written = sizeof(frame);
    return 0;
}

int b41_nav_time_seed_build(const struct b41_nav_utc_sample *sample, uint64_t now_ns,
                           uint64_t deadline_ns, struct b41_nav_time_seed *out)
{
    const uint64_t gps_epoch_ms = 315964800000u, week_ns = 604800000000000u;
    uint64_t elapsed, uncertainty, utc_delta, gps_ns, leap_ns;
    struct b41_nav_time_seed result = {0};
    if (!sample || !out || !sample->uncertainty_ms) return -EINVAL;
    if (now_ns < sample->acquired_ns) return -ESTALE;
    if (now_ns >= deadline_ns) return -ETIMEDOUT;
    if (sample->unix_ms < gps_epoch_ms) return -ERANGE;
    elapsed = now_ns - sample->acquired_ns;
    utc_delta = sample->unix_ms - gps_epoch_ms;
    leap_ns = (uint64_t)sample->gps_minus_utc_seconds * 1000000000u;
    if (elapsed > UINT64_MAX - leap_ns || utc_delta > (UINT64_MAX - elapsed - leap_ns)/1000000u)
        return -EOVERFLOW;
    gps_ns = utc_delta*1000000u + elapsed + leap_ns;
    if (gps_ns/week_ns > 32767u) return -ERANGE;
    uncertainty = (uint64_t)sample->uncertainty_ms + elapsed/1000000u + (uint64_t)(elapsed%1000000u != 0);
    if (uncertainty > 2000000000u) return -ERANGE;
    result.gps_week = (uint16_t)(gps_ns/week_ns);
    result.tow_seconds = (double)(gps_ns%week_ns)/1000000000.0;
    result.uncertainty_ms = (float)uncertainty;
    *out = result;
    return 0;
}

int b41_nav_time_message_encode(const struct b41_nav_time_seed *seed, uint8_t *message, size_t capacity)
{
    uint8_t result[B41_NAV_TIME_MESSAGE_SIZE] = {0};
    uint64_t tow; uint32_t uncertainty;
    if (!seed || !message || !isfinite(seed->tow_seconds) || seed->tow_seconds < 0 ||
        seed->tow_seconds >= 604800.0 || !isfinite(seed->uncertainty_ms) ||
        seed->uncertainty_ms <= 0 || seed->uncertainty_ms > 2000000000.0f || seed->gps_week > 32767u)
        return -EINVAL;
    if (capacity < sizeof(result)) return -ENOSPC;
    memcpy(&tow, &seed->tow_seconds, sizeof(tow));
    memcpy(&uncertainty, &seed->uncertainty_ms, sizeof(uncertainty));
    put16(result, 1016); put16(result + 2, 232); put32(result + 4, 8);
    put16(result + 0x8c, seed->gps_week);
    put64(result + 0x94, tow); put32(result + 0x9c, uncertainty);
    memcpy(message, result, sizeof(result));
    return 0;
}

int b41_nav_host_position_decode(const uint8_t *record, size_t size, struct b41_nav_host_position *out)
{
    static const unsigned days[12] = {31,28,31,30,31,30,31,31,30,31,30,31};
    struct b41_nav_host_position result = {0};
    struct tm civil;
    int64_t unix_seconds;
    time_t utc;
    unsigned limit;
    if (!record || !out) return -EINVAL;
    if (size != B41_NAV_POSITION_SIZE) return -EMSGSIZE;
    if (le32(record) != 0x0c600000u) return -EPROTO;
    result.quality_byte = record[0x18]; result.dimension_byte = record[0x19];
    if (result.dimension_byte != 1 && result.dimension_byte != 2 && result.dimension_byte != 3 &&
        result.dimension_byte != 0xff) return -EPROTO;
    result.utc_correction_seconds = (int16_t)(le16(record + 0x10) < 32768u ?
        (int32_t)le16(record + 0x10) : (int32_t)le16(record + 0x10) - 65536);
    result.gps_week = le16(record + 0x12);
    result.gps_tow_seconds = le32(record + 0x14);
    if (result.dimension_byte < 2 || result.dimension_byte == 0xff || !result.quality_byte) {
        *out = result; return 0;
    }
    if (result.quality_byte != 1 && result.quality_byte != 2 && result.quality_byte != 3 &&
        result.quality_byte != 5) return -EOPNOTSUPP;
    /* gmtime's tm_year/tm_mon are stored unadjusted by50e4a0..50e4c8. */
    if (le16(record + 4) > 8099u || record[6] > 11) return -ERANGE;
    result.year = (uint16_t)(1900u + le16(record + 4)); result.month = (uint8_t)(record[6] + 1u);
    result.day = record[7]; result.hour = record[8]; result.minute = record[9]; result.second = record[10];
    result.milliseconds = le16(record + 12);
    limit = days[result.month-1u] + (unsigned)(result.month == 2 && result.year%4u == 0 &&
                                            (result.year%100u != 0 || result.year%400u == 0));
    if (!result.day || result.day > limit || result.hour > 23 || result.minute > 59 ||
        result.second > 60 || result.milliseconds > 999) return -ERANGE;
    if (result.gps_week > 32767u || result.gps_tow_seconds >= 604800u) return -ERANGE;
    /* Match the actual68b094 ->55391c/gmtime producer. This converts record
     * time, never queries or changes a clock. Leap-second civil60 has no such
     * source encoding in this POSIX path and is not silently normalized.
     */
    unix_seconds = (int64_t)result.gps_week*604800 + result.gps_tow_seconds +
                   315964800 - result.utc_correction_seconds;
    utc = (time_t)unix_seconds;
    if ((int64_t)utc != unix_seconds || !gmtime_r(&utc, &civil)) return -ERANGE;
    if (civil.tm_year + 1900 != (int)result.year || civil.tm_mon + 1 != result.month ||
        civil.tm_mday != result.day || civil.tm_hour != result.hour || civil.tm_min != result.minute ||
        civil.tm_sec != result.second) return -EPROTO;
    result.latitude_degrees = double_le(record + 0x30);
    result.longitude_degrees = double_le(record + 0x38);
    if (!isfinite(result.latitude_degrees) || fabs(result.latitude_degrees) > 90 ||
        !isfinite(result.longitude_degrees) || fabs(result.longitude_degrees) > 180) return -ERANGE;
    result.speed_field50 = float_le(record + 0x50);
    if (!isfinite(result.speed_field50) || result.speed_field50 < 0) return -ERANGE;
    /* Actual output admission534cd4..534d00, not an invented accuracy bound. */
    if (result.speed_field50 > 515.0f && double_le(record + 0x40) > 18270.0) return -ERANGE;
    result.state = result.dimension_byte == 2 ? B41_NAV_POSITION_2D : B41_NAV_POSITION_3D;
    if (result.state == B41_NAV_POSITION_3D) {
        result.altitude = double_le(record + 0x40);
        if (!isfinite(result.altitude)) return -ERANGE;
    }
    *out = result;
    return 0;
}
