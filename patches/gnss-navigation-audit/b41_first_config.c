/* SPDX-License-Identifier: GPL-2.0-only */
#include <errno.h>
#include <string.h>
#include "b41_first_config.h"

static void mark(struct b41_first_config *out, unsigned offset, unsigned count,
                 enum b41_first_provenance source)
{
    memset(out->provenance + offset, source, count);
}

static void word(struct b41_first_config *out, unsigned offset, uint32_t value,
                 unsigned width, enum b41_first_provenance source)
{
    for (unsigned i = 0; i < width; ++i)
        out->bytes[offset + i] = (uint8_t)(value >> (8 * i));
    mark(out, offset, width, source);
}

static uint8_t clock_selector(int flag)
{
    /* Pinned82-entry producer table22fe8. Stock masks the flag to8 bits. */
    switch ((unsigned)flag & 255u) {
    case 0: case 2: case 3: case 16: case 32: case 48: case 64:
        return 255;
    default:
        return 254;
    }
}

int b41_first_config_build(const struct b41_first_inputs *inputs,
                           struct b41_first_config *out)
{
    const unsigned all = B41_FIRST_PLATFORM_PROFILE | B41_FIRST_CLOCK_QUERY |
        B41_FIRST_LNA_QUERY | B41_FIRST_MODEM_QUERY | B41_FIRST_CALIBRATION |
        B41_FIRST_TRANSPORT | B41_FIRST_XML_ASSET;
    struct b41_first_config result = {0};
    if (!inputs || !out || (inputs->present & ~all))
        return -EINVAL;
    if ((inputs->present & B41_FIRST_PLATFORM_PROFILE) &&
        inputs->default_platform_profile != 1)
        return -EOPNOTSUPP;
    if ((inputs->present & B41_FIRST_CLOCK_QUERY) && inputs->clock_ioctl_result < 0)
        return -EIO;
    if ((inputs->present & B41_FIRST_LNA_QUERY) && inputs->lna_ioctl_result < 0)
        return -EIO;
    if ((inputs->present & B41_FIRST_LNA_QUERY) && inputs->lna_ioctl_result != 0)
        return -EPROTO;
    if ((inputs->present & B41_FIRST_MODEM_QUERY) && inputs->modem_ioctl_result < 0)
        return -EIO;
    if ((inputs->present & B41_FIRST_MODEM_QUERY) && inputs->modem_ioctl_result != 0)
        return -EPROTO;
    if ((inputs->present & B41_FIRST_CALIBRATION) &&
        (!inputs->clock_calibration || inputs->clock_calibration_size != 16))
        return -EMSGSIZE;
    if ((inputs->present & B41_FIRST_TRANSPORT) &&
        (inputs->primary_fd < 0 || (inputs->transport != B41_FIRST_HOST &&
                                  inputs->transport != B41_FIRST_OFFLOAD)))
        return -EINVAL;
    if ((inputs->present & B41_FIRST_XML_ASSET) &&
        (!inputs->xml_bytes || !inputs->xml_size ||
         (inputs->xml_asset != B41_FIRST_XML_DATA &&
          inputs->xml_asset != B41_FIRST_XML_VENDOR)))
        return -EINVAL;

    result.missing_inputs = all & ~inputs->present;
    result.xml_policy_missing = 1;
    word(&result, 0, 1, 4, B41_FIRST_CONSTANT);
    mark(&result, 4, 12, B41_FIRST_CONSTANT);
    word(&result, 0x10, 100, 2, B41_FIRST_CONSTANT);
    mark(&result, 0x12, 1, B41_FIRST_CONSTANT);
    mark(&result, 0x16, 2, B41_FIRST_CONSTANT);
    word(&result, 0x1c, 115200, 4, B41_FIRST_CONSTANT);
    /* Only final source-backed zero spans, not blanket zero provenance. */
    mark(&result, 0x25, 3, B41_FIRST_CONSTANT);
    mark(&result, 0x4c, 4, B41_FIRST_CONSTANT);
    mark(&result, 0x51, 3, B41_FIRST_CONSTANT);
    mark(&result, 0x58, 3, B41_FIRST_CONSTANT);
    mark(&result, 0x5c, 8, B41_FIRST_CONSTANT);
    mark(&result, 0x6d, 3, B41_FIRST_CONSTANT);

    if (inputs->present & B41_FIRST_PLATFORM_PROFILE) {
        word(&result, 0x14, 2000, 2, B41_FIRST_DEFAULT_PROFILE);
        word(&result, 0x18, 26000000, 4, B41_FIRST_DEFAULT_PROFILE);
        mark(&result, 0x24, 1, B41_FIRST_DEFAULT_PROFILE);
    }
    if (inputs->present & B41_FIRST_CLOCK_QUERY) {
        word(&result, 0x13, clock_selector(inputs->clock_ioctl_result), 1,
             B41_FIRST_CLOCK_RESULT);
        if (((unsigned)inputs->clock_ioctl_result & 255u) == 81)
            word(&result, 0x18, 52000000, 4, B41_FIRST_CLOCK_RESULT);
    }
    if (inputs->present & B41_FIRST_LNA_QUERY)
        word(&result, 0x54, inputs->lna_pin, 4, B41_FIRST_LNA_RESULT);
    if (inputs->present & B41_FIRST_MODEM_QUERY)
        word(&result, 0x64, inputs->modem_status, 4, B41_FIRST_MODEM_RESULT);
    if ((inputs->present & (B41_FIRST_CALIBRATION | B41_FIRST_PLATFORM_PROFILE)) ==
        (B41_FIRST_CALIBRATION | B41_FIRST_PLATFORM_PROFILE)) {
        memcpy(result.bytes + 0x3c, inputs->clock_calibration, 16);
        mark(&result, 0x3c, 16, B41_FIRST_CLOCK_CALIBRATION);
    }
    if (inputs->present & B41_FIRST_TRANSPORT)
        word(&result, 0x68, inputs->transport, 4, B41_FIRST_TRANSPORT_MODE);
    for (unsigned i = 0; i < B41_FIRST_SIZE; ++i)
        result.unresolved_bytes += result.provenance[i] == B41_FIRST_UNKNOWN;
    *out = result;
    return 1;
}
