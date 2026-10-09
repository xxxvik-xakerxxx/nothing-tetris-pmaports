// SPDX-License-Identifier: GPL-2.0-only
#ifdef GPUEB_IO_HOST_TEST
#include <errno.h>
#include <string.h>
#else
#include <linux/errno.h>
#include <linux/string.h>
#endif
#include "mt6878-gpueb-io-core.h"

int gpueb_io_bounds(enum gpueb_io_region region, u32 offset, u32 size)
{
	u32 capacity;

	switch (region) {
	case GPUEB_IO_GPR: capacity = GPUEB_IO_GPR_SIZE; break;
	case GPUEB_IO_DATA: capacity = GPUEB_IO_DATA_SIZE; break;
	case GPUEB_IO_SEND: case GPUEB_IO_SET:
	case GPUEB_IO_RECV: case GPUEB_IO_CLEAR: capacity = 4; break;
	default: return -EINVAL;
	}
	if (!size || (offset & 3) || (size & 3) ||
	    offset > capacity || size > capacity - offset)
		return -ERANGE;
	return 0;
}

static int io_guard(struct gpueb_io_core *core, const struct gpueb_io_ops *ops)
{
	if (!core || !ops || !ops->read32 || !ops->write32)
		return -EINVAL;
	if (core->first_error)
		return core->first_error;
	if (core->phase != GPUEB_IO_TRANSACTION)
		return -EHOSTDOWN;
	if (!core->users)
		return -ENXIO;
	core->physical_uncertain = 1;
	return 0;
}

int gpueb_io_get(struct gpueb_io_core *core)
{
	if (!core)
		return -EINVAL;
	if (core->phase == GPUEB_IO_QUIESCED || core->phase == GPUEB_IO_QUARANTINED)
		return -ESHUTDOWN;
	if (core->users == ~0U)
		return -EOVERFLOW;
	core->users++;
	return 0;
}

int gpueb_io_put(struct gpueb_io_core *core)
{
	if (!core || !core->users)
		return -EINVAL;
	core->users--;
	return 0;
}

int gpueb_io_quarantine(struct gpueb_io_core *core, int error)
{
	if (!core || error >= 0)
		return -EINVAL;
	if (!core->first_error)
		core->first_error = error;
	core->physical_uncertain = 1;
	core->phase = GPUEB_IO_QUARANTINED;
	return core->first_error;
}

static int io_fault(struct gpueb_io_core *core, int error)
{
	return gpueb_io_quarantine(core, error < 0 ? error : -EIO);
}

int gpueb_io_tx(struct gpueb_io_core *core, const struct gpueb_io_ops *ops,
		void *context, const u32 *words, size_t count)
{
	u32 pending;
	unsigned int i;
	int ret;

	if (!words || count != GPUEB_IO_WORDS)
		return -EINVAL;
	ret = io_guard(core, ops);
	if (ret)
		return ret;
	ret = ops->read32(context, GPUEB_IO_SEND, 0, &pending);
	if (ret)
		return io_fault(core, ret);
	if (pending & GPUEB_IO_CHANNEL)
		return -EBUSY;
	/* Eight individual ordered writel operations, never memcpy_toio/SRAM upload.
	 * Doorbell occurs only after the complete frame; no read/modify/write ACK.
	 */
	for (i = 0; i < GPUEB_IO_WORDS; i++) {
		ret = ops->write32(context, GPUEB_IO_DATA, GPUEB_IO_TX + i * 4, words[i]);
		if (ret)
			return io_fault(core, ret);
	}
	ret = ops->write32(context, GPUEB_IO_SET, 0, GPUEB_IO_CHANNEL);
	return ret ? io_fault(core, ret) : 0;
}

int gpueb_io_rx(struct gpueb_io_core *core, const struct gpueb_io_ops *ops,
		void *context, u32 *words, size_t count)
{
	u32 pending, received[GPUEB_IO_WORDS];
	unsigned int i;
	int ret;

	if (!words || count != GPUEB_IO_WORDS)
		return -EINVAL;
	ret = io_guard(core, ops);
	if (ret)
		return ret;
	ret = ops->read32(context, GPUEB_IO_RECV, 0, &pending);
	if (ret)
		return io_fault(core, ret);
	if (!(pending & GPUEB_IO_CHANNEL))
		return -EAGAIN;
	for (i = 0; i < GPUEB_IO_WORDS; i++) {
		ret = ops->read32(context, GPUEB_IO_DATA, GPUEB_IO_RX + i * 4, &received[i]);
		if (ret)
			return io_fault(core, ret);
	}
	/* Read frame then clear only our bit, matching the vendor ISR path.
	 * No ownership of other IRQ channels and no invented response identifier.
	 */
	ret = ops->write32(context, GPUEB_IO_CLEAR, 0, GPUEB_IO_CHANNEL);
	if (ret)
		return io_fault(core, ret);
	memcpy(words, received, sizeof(received));
	return 0;
}

int gpueb_io_gpr_read(struct gpueb_io_core *core, const struct gpueb_io_ops *ops,
		void *context, u32 offset, u32 *value)
{
	u32 result;
	int ret;

	if (!value)
		return -EINVAL;
	ret = gpueb_io_bounds(GPUEB_IO_GPR, offset, 4);
	if (ret)
		return ret;
	ret = io_guard(core, ops);
	if (ret)
		return ret;
	ret = ops->read32(context, GPUEB_IO_GPR, offset, &result);
	if (ret)
		return io_fault(core, ret);
	*value = result;
	return 0;
}

int gpueb_io_quiesce(struct gpueb_io_core *core)
{
	if (!core)
		return -EINVAL;
	if (core->phase == GPUEB_IO_TRANSACTION)
		core->physical_uncertain = 1;
	if (core->phase != GPUEB_IO_QUARANTINED)
		core->phase = GPUEB_IO_QUIESCED;
	return 0;
}

int gpueb_io_can_destroy(const struct gpueb_io_core *core)
{
	if (!core)
		return -EINVAL;
	if (core->users || core->physical_uncertain || core->phase == GPUEB_IO_TRANSACTION ||
	    core->phase == GPUEB_IO_QUARANTINED)
		return -EBUSY;
	return 0;
}
