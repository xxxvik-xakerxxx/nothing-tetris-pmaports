/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_GPUEB_SRAM_CORE_H
#define MT6878_GPUEB_SRAM_CORE_H
#ifdef GPUEB_SRAM_HOST_TEST
#include <stdint.h>
typedef uint64_t u64;
#else
#include <linux/types.h>
#endif

/* ee2be53 MT6878 DT + authenticated B4.1 LK full-SRAM clear. */
#define GPUEB_SRAM_BASE 0x13c00000ULL
#define GPUEB_SRAM_SIZE 0x40000ULL
#define GPUEB_GPR_OFFSET 0x3fd1cULL
#define GPUEB_GPR_SIZE 0x64ULL
#define GPUEB_MBOX_OFFSET 0x3fd80ULL
#define GPUEB_MBOX_SIZE 0x280ULL

enum gpueb_sram_window { GPUEB_WINDOW_GPR, GPUEB_WINDOW_MBOX, GPUEB_WINDOW_COUNT };
enum gpueb_sram_phase { GPUEB_SRAM_NEW, GPUEB_SRAM_OWNED,
	GPUEB_SRAM_QUARANTINED, GPUEB_SRAM_CLOSED };
struct gpueb_sram_range { u64 start, size; };
struct gpueb_sram_core {
	enum gpueb_sram_phase phase;
	unsigned int clients;
	struct gpueb_sram_range whole;
};
/* All core operations require the controller mutex. No physical OFF inference. */
int gpueb_sram_validate(u64 start, u64 size);
int gpueb_sram_open(struct gpueb_sram_core *core, u64 start, u64 size);
int gpueb_sram_claim_window(struct gpueb_sram_core *core, enum gpueb_sram_window type);
int gpueb_sram_put_window(struct gpueb_sram_core *core, enum gpueb_sram_window type);
int gpueb_sram_window_range(const struct gpueb_sram_core *core,
		enum gpueb_sram_window type, u64 offset, u64 size,
		struct gpueb_sram_range *range);
int gpueb_sram_quarantine(struct gpueb_sram_core *core);
int gpueb_sram_close(struct gpueb_sram_core *core);
#endif
