/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef B41_FIRST_CONFIG_H
#define B41_FIRST_CONFIG_H
#include <stddef.h>
#include <stdint.h>

#define B41_FIRST_SIZE 0x70u

enum b41_first_input {
    B41_FIRST_PLATFORM_PROFILE = 1u << 0,
    B41_FIRST_CLOCK_QUERY = 1u << 1,
    B41_FIRST_LNA_QUERY = 1u << 2,
    B41_FIRST_MODEM_QUERY = 1u << 3,
    B41_FIRST_CALIBRATION = 1u << 4,
    B41_FIRST_TRANSPORT = 1u << 5,
    B41_FIRST_XML_ASSET = 1u << 6,
};

enum b41_first_provenance {
    B41_FIRST_UNKNOWN = 0,
    B41_FIRST_CONSTANT,
    B41_FIRST_DEFAULT_PROFILE,
    B41_FIRST_CLOCK_RESULT,
    B41_FIRST_LNA_RESULT,
    B41_FIRST_MODEM_RESULT,
    B41_FIRST_CLOCK_CALIBRATION,
    B41_FIRST_TRANSPORT_MODE,
};

enum b41_first_transport { B41_FIRST_HOST = 0, B41_FIRST_OFFLOAD = 1 };
enum b41_first_xml_asset { B41_FIRST_XML_DATA, B41_FIRST_XML_VENDOR };

struct b41_first_inputs {
    unsigned present;
    /* Explicit producer branch de22c==0 only. Alternate profile is unresolved. */
    unsigned default_platform_profile;
    int clock_ioctl_result;             /* ioctl11 returns the clock flag. */
    int lna_ioctl_result;               /* ioctl16 status, separate output. */
    uint32_t lna_pin;
    int modem_ioctl_result;             /* ioctl21 status, separate output. */
    uint32_t modem_status;
    const uint8_t *clock_calibration;   /* Actual same-unit16-byte read only. */
    size_t clock_calibration_size;
    enum b41_first_transport transport;
    int primary_fd;                     /* Owned open fd, no opening here. */
    enum b41_first_xml_asset xml_asset;
    const void *xml_bytes;
    size_t xml_size;
};

struct b41_first_config {
    uint8_t bytes[B41_FIRST_SIZE];
    uint8_t provenance[B41_FIRST_SIZE];
    unsigned missing_inputs;
    unsigned unresolved_bytes;
    /* Asset presence is not parsed XML policy. This gate cannot be asserted
     * away by a caller; the policy decoder is not implemented yet.
     */
    unsigned xml_policy_missing;
};

/* Returns1 for a built partial configuration, negative errno on invalid input.
 * Rejection leaves out untouched. No native engine/device/property call occurs.
 * No output can currently authorize engine startup: policy fields stay unknown.
 */
int b41_first_config_build(const struct b41_first_inputs *inputs,
                           struct b41_first_config *out);
#endif
