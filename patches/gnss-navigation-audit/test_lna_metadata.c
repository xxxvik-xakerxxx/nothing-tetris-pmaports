/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include "gps_dl_lna_metadata.h"

int main(void)
{
	const unsigned int muxes[] = {
		(18u << 8) | 6u, (20u << 8) | 4u, (33u << 8) | 3u,
		(143u << 8) | 2u, (154u << 8) | 3u,
		(181u << 8) | 3u, (186u << 8) | 2u,
	};
	unsigned int pin, matches = 0;
	for (unsigned int mux = 0; mux < 65536; ++mux) {
		int expected = 0;
		for (unsigned int i = 0; i < sizeof(muxes) / sizeof(muxes[0]); ++i)
			expected |= mux == muxes[i];
		pin = 0xa5a5a5a5;
		int ret = gps_dl_lna_decode_pinmux(mux, &pin);
		if (expected) {
			assert(ret == 0 && pin == mux >> 8);
			++matches;
		} else {
			assert(ret == -EINVAL && pin == 0xa5a5a5a5);
		}
	}
	assert(matches == 7);
	for (unsigned int i = 0; i < sizeof(muxes) / sizeof(muxes[0]); ++i) {
		pin = 0xa5a5a5a5;
		assert(gps_dl_lna_decode_pinmux(muxes[i] | 0x10000u, &pin) == -EINVAL);
		assert(pin == 0xa5a5a5a5);
	}
	assert(gps_dl_lna_decode_pinmux(muxes[0], NULL) == -EINVAL);
	puts("PASS: 65536 pinmux values, exact MT6878 L1 alternatives, no fallback or failed-output mutation");
	return 0;
}
