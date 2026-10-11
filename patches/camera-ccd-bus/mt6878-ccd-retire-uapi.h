/* SPDX-License-Identifier: GPL-2.0-only WITH Linux-syscall-note */
#ifndef MT6878_CCD_RETIRE_UAPI_H
#define MT6878_CCD_RETIRE_UAPI_H

#include <linux/ioctl.h>
#include <linux/types.h>

/* New native-owner extension, NOT a claimed stock firmware/libccd ABI. */
#define MT6878_CCD_OWNER_ABI 1U
struct mt6878_ccd_registration {
	__u32 abi, endpoint_mask;
	__aligned_u64 generation;
};

struct mt6878_ccd_worker_retired {
	__aligned_u64 generation, token;
	__u32 src, reserved;
};

#define MT6878_CCD_REGISTER _IOWR('T', 0xc0, struct mt6878_ccd_registration)
#define MT6878_CCD_RETIRE_ACK _IOW('T', 0xc1, struct mt6878_ccd_worker_retired)
#define MT6878_CCD_RETIRE_QUERY _IOWR('T', 0xc2, struct mt6878_ccd_worker_retired)

#endif
