/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef IMX882_STREAM_CORE_H
#define IMX882_STREAM_CORE_H

#ifdef __KERNEL__
#include <linux/errno.h>
#else
#include <errno.h>
#endif

/* Matching Nothing 4.1: e96f60dc081ae3525ef43d4bcf0ee5ee97e53835.
 * The caller owns power, bus serialization and stream lifecycle.
 */
struct imx882_reg {
	unsigned short address;
	unsigned char value;
};

struct imx882_bus {
	int (*write)(void *context, unsigned short address, unsigned char value);
	void *context;
};

static inline int imx882_write_table(const struct imx882_bus *bus,
				   const struct imx882_reg *table,
				   unsigned int count)
{
	unsigned int i;
	int ret;

	for (i = 0; i < count; i++) {
		ret = bus->write(bus->context, table[i].address, table[i].value);
		if (ret)
			return ret;
	}
	return 0;
}

static inline int imx882_write_word(const struct imx882_bus *bus,
				  unsigned short address, unsigned short value)
{
	int ret = bus->write(bus->context, address, value >> 8);

	if (ret)
		return ret;
	return bus->write(bus->context, address + 1, value & 0xff);
}

/* Short exposure only: no undocumented long-exposure state transitions.
 * Always attempt to release group hold, including an ambiguous hold write.
 */
static inline int imx882_write_controls(const struct imx882_bus *bus,
				       unsigned int frame_length,
				       unsigned int exposure,
				       unsigned int gain)
{
	unsigned int reg_gain;
	int ret, release;

	if (frame_length < 3900 || frame_length > 65535 ||
	    exposure < 6 || exposure > frame_length - 64 ||
	    gain < 1463 || gain > 65536)
		return -EINVAL;

	reg_gain = 16384 - (16384 * 1024) / gain;
	ret = bus->write(bus->context, 0x0104, 1);
	if (!ret)
		ret = imx882_write_word(bus, 0x0340, frame_length);
	/* Do not let auto-extension violate the exposed VBLANK contract. */
	if (!ret)
		ret = bus->write(bus->context, 0x0350, 0);
	if (!ret)
		ret = imx882_write_word(bus, 0x0202, exposure);
	if (!ret)
		ret = imx882_write_word(bus, 0x0204, reg_gain);
	release = bus->write(bus->context, 0x0104, 0);
	return ret ? ret : release;
}

#endif
