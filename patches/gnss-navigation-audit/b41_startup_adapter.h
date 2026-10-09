/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_STARTUP_ADAPTER_H
#define B41_STARTUP_ADAPTER_H
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include "b41_frame_sync.h"

#define B41_FIRST_CONFIG_SIZE 0x70u
#define B41_SECOND_CONFIG_SIZE 0x444u
#define B41_HOST_QUEUE_SIZE 16u
#define B41_HOST_OUTPUT_MAX 1024u

struct b41_startup_config {
    uint8_t first[B41_FIRST_CONFIG_SIZE];
    uint8_t second[B41_SECOND_CONFIG_SIZE];
    /* Clearing storage does not establish the policy of any field. */
    uint8_t resolved_second[B41_SECOND_CONFIG_SIZE];
};

enum b41_startup_missing {
    B41_MISSING_FIRST_CONFIG = 1u << 0,
    B41_MISSING_SECOND_POLICY = 1u << 1,
    B41_MISSING_CALLBACK_ABI = 1u << 2, /* Mandatory0..9 shapes now recovered. */
    B41_MISSING_TRANSPORT_OWNER = 1u << 3,
    B41_MISSING_AGPS_RECEIVER = 1u << 4,
    B41_MISSING_STOP_CONTRACT = 1u << 5,
    B41_MISSING_HOST_SERVICES = 1u << 6,
};

enum b41_host_event_kind {
    B41_HOST_APP_OUTPUT = 1,
    B41_HOST_OUTPUT = 2,
    B41_HOST_FRAME_SLEEP = 3,
    B41_HOST_FRAME_NETWORK = 4,
    B41_HOST_FRAME_MEASUREMENT = 5,
    B41_HOST_AGPS_DATA = 6,
};

struct b41_host_event {
    enum b41_host_event_kind kind;
    uint32_t length;
    uint8_t bytes[B41_HOST_OUTPUT_MAX];
};

struct b41_host_adapter {
    atomic_flag lock;
    atomic_int first_error;
    unsigned head, count;
    struct b41_host_event events[B41_HOST_QUEUE_SIZE];
};

typedef int32_t (*b41_slot2_output_fn)(const void *, uint32_t);
typedef int32_t (*b41_slot0_notify_fn)(uint32_t);
typedef int32_t (*b41_slot5_frame_measurement_fn)(uint32_t);
typedef int32_t (*b41_slot6_agps_fn)(uint32_t, uint32_t, const void *);
typedef uint32_t (*b41_slot7_passthrough_fn)(uint32_t);
typedef uint32_t (*b41_slot8_encode_fn)(const void *, void *, uint32_t);
typedef uint32_t (*b41_slot9_decode_fn)(void *, const void *, uint32_t);

/* This is deliberately not a fabricated 24-slot vendor registration struct. */
struct b41_known_callbacks {
    b41_slot0_notify_fn notify;
    b41_slot2_output_fn app_output;
    b41_slot2_output_fn output;
    b41_slot3_frame_sync_sleep_fn frame_sleep;
    b41_slot4_frame_sync_network_fn frame_network;
    b41_slot5_frame_measurement_fn frame_measurement;
    b41_slot6_agps_fn agps;
    b41_slot7_passthrough_fn passthrough;
    b41_slot8_encode_fn encode;
    b41_slot9_decode_fn decode;
};

void b41_startup_config_init(struct b41_startup_config *config);
int b41_startup_set_path(struct b41_startup_config *config, unsigned offset,
                         const char *path);
int b41_startup_set_build_policy(struct b41_startup_config *config,
                                const char *build_type, const char *debuggable);
int b41_startup_set_callback_output(struct b41_startup_config *config);
int b41_startup_set_b41_identity(struct b41_startup_config *config);
unsigned b41_startup_missing_contracts(void);
int b41_host_adapter_init(struct b41_host_adapter *adapter);
/* Bind once, before any vendor threads. Adapter must live until process exit.
 * There is no unsafe unbind while the opaque engine may retain callbacks.
 */
int b41_host_adapter_bind(struct b41_host_adapter *adapter,
                          struct b41_known_callbacks *callbacks);
int b41_host_adapter_take(struct b41_host_adapter *adapter,
                          struct b41_host_event *event);
int b41_host_adapter_error(const struct b41_host_adapter *adapter);
#endif
