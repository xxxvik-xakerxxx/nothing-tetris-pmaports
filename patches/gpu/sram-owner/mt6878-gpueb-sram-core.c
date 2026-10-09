// SPDX-License-Identifier: GPL-2.0-only
#ifdef GPUEB_SRAM_HOST_TEST
#include <errno.h>
#include <stddef.h>
#else
#include <linux/errno.h>
#endif
#include "mt6878-gpueb-sram-core.h"

static int window_profile(enum gpueb_sram_window type, u64 *offset, u64 *size)
{
	switch (type) {
	case GPUEB_WINDOW_GPR:
		*offset = GPUEB_GPR_OFFSET;
		*size = GPUEB_GPR_SIZE;
		return 0;
	case GPUEB_WINDOW_MBOX:
		*offset = GPUEB_MBOX_OFFSET;
		*size = GPUEB_MBOX_SIZE;
		return 0;
	default:
		return -EINVAL;
	}
}

int gpueb_sram_validate(u64 start, u64 size)
{
	if (!size || start > ~(u64)0 - (size - 1))
		return -ERANGE;
	if (start != GPUEB_SRAM_BASE || size != GPUEB_SRAM_SIZE)
		return -EINVAL;
	if (GPUEB_GPR_OFFSET > size || GPUEB_GPR_SIZE > size - GPUEB_GPR_OFFSET ||
	    GPUEB_GPR_OFFSET + GPUEB_GPR_SIZE != GPUEB_MBOX_OFFSET ||
	    GPUEB_MBOX_OFFSET > size || GPUEB_MBOX_SIZE != size - GPUEB_MBOX_OFFSET)
		return -ERANGE;
	return 0;
}

int gpueb_sram_open(struct gpueb_sram_core *core, u64 start, u64 size)
{
	int ret;

	if (!core)
		return -EINVAL;
	if (core->phase != GPUEB_SRAM_NEW)
		return -EBUSY;
	ret = gpueb_sram_validate(start, size);
	if (ret)
		return ret;
	core->whole = (struct gpueb_sram_range){ start, size };
	core->clients = 0;
	core->phase = GPUEB_SRAM_OWNED;
	return 0;
}

int gpueb_sram_claim_window(struct gpueb_sram_core *core, enum gpueb_sram_window type)
{
	u64 offset, size;

	if (!core || window_profile(type, &offset, &size))
		return -EINVAL;
	if (core->phase != GPUEB_SRAM_OWNED)
		return -ESHUTDOWN;
	if (core->clients & (1U << type))
		return -EBUSY;
	core->clients |= 1U << type;
	return 0;
}

int gpueb_sram_put_window(struct gpueb_sram_core *core, enum gpueb_sram_window type)
{
	u64 offset, size;

	if (!core || window_profile(type, &offset, &size))
		return -EINVAL;
	if (!(core->clients & (1U << type)))
		return -ENOENT;
	core->clients &= ~(1U << type);
	return 0;
}

int gpueb_sram_window_range(const struct gpueb_sram_core *core,
		enum gpueb_sram_window type, u64 offset, u64 size,
		struct gpueb_sram_range *range)
{
	u64 base, capacity;

	if (!core || !range || window_profile(type, &base, &capacity))
		return -EINVAL;
	if (core->phase != GPUEB_SRAM_OWNED)
		return -ESHUTDOWN;
	if (!(core->clients & (1U << type)))
		return -ENOENT;
	if (!size || (offset & 3) || (size & 3) ||
	    offset > capacity || size > capacity - offset)
		return -ERANGE;
	*range = (struct gpueb_sram_range){ core->whole.start + base + offset, size };
	return 0;
}

int gpueb_sram_quarantine(struct gpueb_sram_core *core)
{
	if (!core)
		return -EINVAL;
	if (core->phase == GPUEB_SRAM_QUARANTINED)
		return 0;
	if (core->phase != GPUEB_SRAM_OWNED)
		return -EINVAL;
	core->phase = GPUEB_SRAM_QUARANTINED;
	return 0;
}

int gpueb_sram_close(struct gpueb_sram_core *core)
{
	if (!core)
		return -EINVAL;
	if (core->phase == GPUEB_SRAM_QUARANTINED || core->clients)
		return -EBUSY;
	if (core->phase != GPUEB_SRAM_OWNED)
		return -EINVAL;
	core->phase = GPUEB_SRAM_CLOSED;
	return 0;
}
