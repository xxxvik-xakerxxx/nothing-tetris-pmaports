/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MT6878_MD_STARTUP_SCOPE_H
#define MT6878_MD_STARTUP_SCOPE_H
#include <linux/arm-smccc.h>
#include <linux/types.h>
struct device;
struct module;

/* ROM and shared-memory identities, not a new bootloader wire format. */
struct mt6878_md_handoff_state {
	u64 rom_base, rom_size, smem_base, smem_size;
	u8 rom_digest[32];
};
struct mt6878_md_handoff_owner {
	struct module *module;
	/* Read the retained source-owned handoff, not caller-supplied proof bits. */
	int (*snapshot)(void *, struct mt6878_md_handoff_state *);
	/* Must bind signature/authentication and reserved memory to these fields.
	 * No production implementation exists in this candidate. Missing => ENOKEY.
	 */
	int (*authenticate)(void *, const struct mt6878_md_handoff_state *);
};
/* Replace every selected DVFSRC command0 call, preserving the raw SMC result.
 * Called in driver probe while supplier device_lock is already held.
 */
int mt6878_md_scoped_dvfsrc_init(struct device *, u32 flags, u32 vmode,
			       struct arm_smccc_res *);
/* Same task must call begin -> validate_execution -> end. No domain transition
 * or CCCI operation is performed here. End never signifies safe power-down.
 */
int mt6878_md_scope_begin(const struct mt6878_md_handoff_owner *, void *);
int mt6878_md_scope_validate_execution(void);
int mt6878_md_scope_end(int first_start_result);
#endif
