/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef _UAPI_GPSDL_V051_SESSION_H
#define _UAPI_GPSDL_V051_SESSION_H

#ifdef __KERNEL__
#include <linux/types.h>
typedef __u32 gpsdl_session_u32;
#else
#include <stdint.h>
typedef uint32_t gpsdl_session_u32;
#endif

/* Opt-in 1010 only. Existing ioctl12 is TRIGGER_ASSERT, not a state query. */
#define GPSDL_V051_IOC_SESSION_SNAPSHOT 31U
#define GPSDL_V051_SESSION_ABI 1U

/* Independently sampled live scalars, not an atomic FSM transition record.
 * No pointers, keys, firmware metadata, calibration or writable input fields.
 */
struct gpsdl_v051_session_snapshot {
	gpsdl_session_u32 abi_version;
	gpsdl_session_u32 size;
	gpsdl_session_u32 link_id;
	gpsdl_session_u32 session_id;
	gpsdl_session_u32 link_state;
	gpsdl_session_u32 dsp_state;
	gpsdl_session_u32 reserved[2];
};

#endif
