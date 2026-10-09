/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_IO_CORE_H
#define MT6878_GPUEB_IO_CORE_H
#ifdef GPUEB_IO_HOST_TEST
#include <stdint.h>
#include <stddef.h>
typedef uint32_t u32;
#else
#include <linux/types.h>
#endif

#define GPUEB_IO_WORDS 8U
#define GPUEB_IO_TX 0x10U
#define GPUEB_IO_RX 0xe8U
#define GPUEB_IO_CHANNEL (1U << 1)
#define GPUEB_IO_GPR_SIZE 0x64U
#define GPUEB_IO_DATA_SIZE 0x280U
enum gpueb_io_region { GPUEB_IO_GPR, GPUEB_IO_DATA, GPUEB_IO_SEND,
	GPUEB_IO_SET, GPUEB_IO_RECV, GPUEB_IO_CLEAR, GPUEB_IO_REGION_COUNT };
enum gpueb_io_phase { GPUEB_IO_UNPROVEN, GPUEB_IO_TRANSACTION,
	GPUEB_IO_QUIESCED, GPUEB_IO_QUARANTINED };
struct gpueb_io_core {
	enum gpueb_io_phase phase;
	unsigned int users;
	/* Latched attempt, never a power/physical OFF acknowledgement. */
	unsigned int physical_uncertain;
	int first_error;
};
/* MMIO operations, NOT readiness/power callbacks. Caller holds its IRQ-safe
 * parent scope lock across the entire operation. No production transition
 * into TRANSACTION is provided until the physical owner is reviewed.
 */
struct gpueb_io_ops {
	int (*read32)(void *context, enum gpueb_io_region region, u32 offset, u32 *value);
	int (*write32)(void *context, enum gpueb_io_region region, u32 offset, u32 value);
};
int gpueb_io_bounds(enum gpueb_io_region region, u32 offset, u32 size);
int gpueb_io_get(struct gpueb_io_core *core);
int gpueb_io_put(struct gpueb_io_core *core);
int gpueb_io_tx(struct gpueb_io_core *core, const struct gpueb_io_ops *ops,
		void *context, const u32 *words, size_t count);
int gpueb_io_rx(struct gpueb_io_core *core, const struct gpueb_io_ops *ops,
		void *context, u32 *words, size_t count);
int gpueb_io_gpr_read(struct gpueb_io_core *core, const struct gpueb_io_ops *ops,
		void *context, u32 offset, u32 *value);
int gpueb_io_quiesce(struct gpueb_io_core *core);
int gpueb_io_quarantine(struct gpueb_io_core *core, int error);
int gpueb_io_can_destroy(const struct gpueb_io_core *core);
#endif
