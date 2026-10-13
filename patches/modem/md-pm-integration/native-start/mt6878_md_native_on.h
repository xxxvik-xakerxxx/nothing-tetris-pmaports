/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_MD_NATIVE_ON_H
#define MT6878_MD_NATIVE_ON_H
struct device;
/* Actual retained supplier + fresh readbacks, not a transferable grant/token. */
int mt6878_md_native_on_validate(struct device *consumer);
int mt6878_md_native_on_latch(struct device *consumer, int error);
#endif
