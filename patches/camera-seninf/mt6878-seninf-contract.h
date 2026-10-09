/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_SENINF_CONTRACT_H
#define MT6878_SENINF_CONTRACT_H

#ifdef __KERNEL__
#include <linux/errno.h>
#else
#include <errno.h>
#endif

/* Restricted to the two audited IMX882 binned modes, not a generic PHY. */
static inline int mt6878_seninf_check_trios(unsigned int count,
					 const unsigned int lanes[3])
{
	if (count != 3 || lanes[0] != 0 || lanes[1] != 1 || lanes[2] != 2)
		return -EINVAL;
	return 0;
}

struct mt6878_seninf_packet {
	unsigned int vc;
	unsigned int dt;
	unsigned int length;
};

static inline int mt6878_seninf_check_packets(unsigned int width,
	unsigned int height, unsigned int count,
	const struct mt6878_seninf_packet packets[2])
{
	unsigned int raw = 0, pdaf = 0, i;
	unsigned int raw_length, pdaf_length;

	if (!((width == 4000 && height == 3000) ||
	      (width == 4096 && height == 2304)) || count != 2)
		return -EINVAL;
	raw_length = width * height * 10 / 8;
	pdaf_length = width * (height / 4) * 10 / 8;
	for (i = 0; i < count; i++) {
		if (packets[i].vc)
			return -EINVAL;
		if (packets[i].dt == 0x2b && packets[i].length == raw_length)
			raw++;
		else if (packets[i].dt == 0x30 && packets[i].length == pdaf_length)
			pdaf++;
		else
			return -EINVAL;
	}
	return raw == 1 && pdaf == 1 ? 0 : -EINVAL;
}

#endif
