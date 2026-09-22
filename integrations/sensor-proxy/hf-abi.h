/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <sys/ioctl.h>

/* Nothing OS 4.1 ee2be53c, sensor/2.0/core/hf_manager.h, LE ABI. */
struct hf_packet { uint8_t sensor, reserved[3], payload[64]; };
struct hf_info { uint8_t sensor, reserved[3]; uint32_t gain; char name[16], vendor[16]; };
struct hf_event {
        int64_t timestamp;
        uint8_t sensor, accuracy, action, reserved;
        int32_t words[16];
} __attribute__((packed));
struct hf_command { uint8_t sensor, action, length, reserved, data[48]; };
_Static_assert(sizeof(struct hf_packet) == 68, "HF ioctl ABI");
_Static_assert(sizeof(struct hf_info) == 40, "HF info ABI");
_Static_assert(sizeof(struct hf_event) == 76, "HF event ABI");
_Static_assert(offsetof(struct hf_event, words) == 12, "HF words ABI");
_Static_assert(sizeof(struct hf_command) == 52, "HF command ABI");

static inline struct hf_command
hf_make_command(uint8_t sensor, int enabled)
{
        struct hf_command cmd = { .sensor = sensor, .action = !!enabled, .length = 16 };
        int64_t period = 40000000, latency = 0;
        memcpy(cmd.data, &period, 8);
        memcpy(cmd.data + 8, &latency, 8);
        return cmd;
}

/* Other action types carry metadata/calibration, not sensor readings. */
static inline int
hf_valid_data(const struct hf_event *event, uint8_t sensor, int64_t previous)
{
        return event->sensor == sensor && event->action == 0 &&
               event->timestamp > 0 && event->timestamp > previous;
}
