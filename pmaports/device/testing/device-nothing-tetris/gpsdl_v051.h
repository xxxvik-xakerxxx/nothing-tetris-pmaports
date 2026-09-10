/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
/*
 * Read-only userspace ABI for the MediaTek GPS data-link v051 driver.
 *
 * The driver intentionally uses plain integer ioctl command values rather
 * than _IO*()-encoded commands. Keep these values and layouts stable.
 */

#ifndef _UAPI_GPSDL_V051_H
#define _UAPI_GPSDL_V051_H

#include <linux/types.h>

#define GPSDL_V051_IOC_QUERY_STATUS		13U
#define GPSDL_V051_IOC_GET_DSP_BOOTUP_INFO	23U
#define GPSDL_V051_IOC_GET_BOOT_TIME		28U

struct gpsdl_v051_boot_time {
	__s64 now_time;
	__s64 arch_counter;
};

struct gpsdl_v051_bootup_info {
	__u32 code_size;
	__u32 start_addr;
	__u32 exec_addr;
	__u32 cipher_key;
	__u32 frag_num;
};

#endif /* _UAPI_GPSDL_V051_H */
