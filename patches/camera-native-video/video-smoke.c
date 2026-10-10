// SPDX-License-Identifier: GPL-2.0-only
#include "mt6878-native-video.h"

static_assert(sizeof(((struct mt6878_native_video_suppliers *)0)->layout.raw_layout.bytesperline)
	== sizeof(unsigned int));

static int __maybe_unused mt6878_native_video_api_smoke(void)
{
	struct mt6878_native_video *owner = NULL;
	int ret;

	/* Real argument rejection only; no platform registration or suppliers. */
	ret = mt6878_native_video_register(NULL, &owner);
	return ret ? ret : mt6878_native_video_wait_ready(owner, 1);
}
