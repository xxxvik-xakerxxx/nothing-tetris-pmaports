/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_COLD_CAPTURE_H
#define MT6878_COLD_CAPTURE_H
#include "mt6878-native-video.h"

/* Layout/config come from the caller's real producer, never default metadata. */
int mt6878_cold_suppliers_check(const struct mt6878_native_video_suppliers *suppliers);
int mt6878_cold_capture_register(const struct mt6878_native_video_suppliers *suppliers,
	struct mt6878_native_video **result);
#endif
