/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_NATIVE_NAVIGATION_H
#define B41_NATIVE_NAVIGATION_H
#include <stddef.h>
#include <stdint.h>

#define B41_NAV_PAYLOAD_MAX 1014u
#define B41_NAV_WIRE_MAX (2u * (B41_NAV_PAYLOAD_MAX + 6u) + 4u)
#define B41_NAV_RECORD_MAX 115u
#define B41_NAV_EPOCH_RECORDS 20u
#define B41_NAV_POSITION_SIZE 0xc60u
#define B41_NAV_TIME_MESSAGE_SIZE 236u

struct b41_nav_packet {
    uint16_t payload_size;
    uint8_t command, length_high_nibble;
    uint8_t payload[B41_NAV_PAYLOAD_MAX];
};
/* A complete primary AA/F0 frame, including actual DE escaping. No UART NMEA
 * cast, RX worker, I/O, guessed firmware reply or checksum-only readiness.
 */
int b41_nav_packet_decode(const uint8_t *wire, size_t size, struct b41_nav_packet *out);

struct b41_nav_record41 {
    uint8_t byte0, byte1, byte2, byte3;
    uint32_t words[7]; /* BE halfwords, low halfword first: 5040f4..5041d0. */
};
struct b41_nav_record4d {
    uint32_t prefix24;
    uint8_t byte3, byte4, byte5, byte6;
    uint32_t words[10]; /* LE halfwords, high halfword first: 505294..5053fc. */
};
struct b41_nav_record {
    uint8_t command, index, size;
    uint8_t wire[B41_NAV_RECORD_MAX];
    union { struct b41_nav_record41 fe41; struct b41_nav_record4d fe4d; } decoded;
};
struct b41_nav_epoch_end {
    uint8_t byte0, byte9;
    uint32_t word1, word5; /* Source504a24..80; units not yet established. */
};
struct b41_nav_epoch {
    uint64_t begin_ns, end_ns;
    uint8_t header[66]; /* Actual FE2C bytes, never synthesized/calibrated. */
    uint32_t header_word0, header_word4, header_field8_9_44;
    uint8_t count;
    struct b41_nav_record records[B41_NAV_EPOCH_RECORDS];
    struct b41_nav_epoch_end end;
};
struct b41_nav_epoch_owner {
    uint64_t deadline_ns, last_ns;
    int first_error;
    unsigned active;
    struct b41_nav_epoch pending;
};
/* Fresh zeroed software owner only; no deadline extension/revival after error. */
int b41_nav_epoch_init(struct b41_nav_epoch_owner *owner, uint64_t now_ns, uint64_t deadline_ns);
/* One sole native RX owner, after actual same-session WORK in native-session.
 * Return0 pending,1 actual FE2C..FE4C completed epoch, negative first error.
 * Complete means wire grouping only, never a position, pseudorange or fix.
 * Records2B/3B/4B/5C/91 are retained with exact source length/index bounds;
 * their physical field semantics are not fabricated. Only41/4D fields above
 * are converted. Unknown commands latch EOPNOTSUPP, never a successful drop.
 */
int b41_nav_epoch_accept(struct b41_nav_epoch_owner *owner, const struct b41_nav_packet *packet,
                        uint64_t now_ns, struct b41_nav_epoch *complete);

/* The proven post-DSP-init parameter42/subtype3 configuration operation.
 * This is NOT a complete navigation initializer or a firmware-ready gate.
 * Encoder only; the existing sole session/download owner controls any TX.
 */
int b41_nav_post_init_reporting_encode(uint8_t *wire, size_t capacity, size_t *written);

struct b41_nav_utc_sample {
    uint64_t unix_ms, acquired_ns;
    uint32_t uncertainty_ms;
    uint8_t gps_minus_utc_seconds;
};
struct b41_nav_time_seed {
    uint16_t gps_week;
    double tow_seconds;
    float uncertainty_ms;
};
/* Supplied human-accepted UTC and explicit GPS/UTC offset, not RTC/NTP queries.
 * Monotonic age/deadline only. Conservative uncertainty adds the whole age;
 * it is a native policy, not a claim of OEM clock calibration or UTC accuracy.
 */
int b41_nav_time_seed_build(const struct b41_nav_utc_sample *sample, uint64_t now_ns,
                           uint64_t deadline_ns, struct b41_nav_time_seed *out);
/* Exact host message1016/length232/subtype8 at510aa4..510b98. NOT AA/F0,
 * NOT a DSP time-injection packet and never pass this message to gpsdl write.
 * The real consumer at5324d0 invokes host solver513080/5ba794; no solver/DSO
 * execution or claim of sufficient standalone INIT is made by this encoder.
 */
int b41_nav_time_message_encode(const struct b41_nav_time_seed *seed, uint8_t *message, size_t capacity);

enum b41_nav_position_state { B41_NAV_POSITION_NOT_VALID, B41_NAV_POSITION_2D, B41_NAV_POSITION_3D };
struct b41_nav_host_position {
    enum b41_nav_position_state state;
    uint8_t quality_byte, dimension_byte;
    int16_t utc_correction_seconds;
    uint16_t gps_week;
    uint32_t gps_tow_seconds;
    uint16_t year, milliseconds;
    uint8_t month, day, hour, minute, second;
    double latitude_degrees, longitude_degrees, altitude;
    float speed_field50; /* Retained scalar; no guessed accuracy field. */
};
/* Parse the actual0xc60-byte getter/MCU-host POSITION record, NOT UART payload.
 * Dimension comes from+19; coordinates+30/+38 are degrees. Header/layout,
 * finite/range/civil-time checks do not authenticate the record's producer or
 * prove a physical GNSS fix. No guessed accuracy, NMEA, solution generation,
 * getter call or raw measurement->position conversion is provided here.
 */
int b41_nav_host_position_decode(const uint8_t *record, size_t size, struct b41_nav_host_position *out);
#endif
