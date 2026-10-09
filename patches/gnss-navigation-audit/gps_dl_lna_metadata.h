/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GPS_DL_LNA_METADATA_H
#define GPS_DL_LNA_METADATA_H
#include <linux/errno.h>

/* MT6878 binding GPS_L1_ELNA_EN alternatives, not a board default.
 * The selected value must come from the GPS owner's actual DT state.
 * This returns a SoC pin index, never a global Linux GPIO number.
 */
static inline int gps_dl_lna_decode_pinmux(unsigned int mux, unsigned int *pin)
{
	if (!pin)
		return -EINVAL;
	switch (mux) {
	case (18u << 8) | 6u:
	case (20u << 8) | 4u:
	case (33u << 8) | 3u:
	case (143u << 8) | 2u:
	case (154u << 8) | 3u:
	case (181u << 8) | 3u:
	case (186u << 8) | 2u:
		*pin = mux >> 8;
		return 0;
	default:
		return -EINVAL;
	}
}
#endif
