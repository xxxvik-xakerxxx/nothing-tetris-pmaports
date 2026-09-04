# CCCI CCIF Linux 6.18 compile-only evidence

## Boundary

This gate uses `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878`
at exact commit `ee2be53cb75670b548948636a0db1d1ff112bf12` (Nothing OS
4.1, Tetris B4.1) and `MT6878-mainline/linux` at
`d84b264a54a37611f2f46bc19363cb9b41606205` (Linux 6.18).
The downloaded kernel archive used for the clean rerun has SHA-256
`72ad59af6a4e55995f357a3d4f5d18ae3a021bf56a1d334663a1488dceb17ca6`.

At exact `ee2be53`,
`include/linux/soc/mediatek/mtk_sip_svc.h` defines
`MTK_SIP_KERNEL_CCCI_CONTROL` as `MTK_SIP_SMC_CMD(0x505)`. Under
`CONFIG_ARM64`, the shared `MTK_SIP_SMC_CMD()` definition encodes the fast
64-bit SiP call value `0xc2000505`. The same source commit passes that macro to
`arm_smccc_smc()` for `MD_CLOCK_REQUEST` in `ccci_hif_ccif.c`; therefore this
fallback is not runtime-safe merely because it is compile-safe.

`0053-vendor-eccci-ccif-linux-6.18-compile-only.patch.vendor` is an
object-build compatibility patch. It updates the removed timer helpers and
supplies the exact B4.1 CCCI SiP service identifier behind `#ifndef` when the
Linux 6.18 header does not provide it. The identifier is source evidence only:
it does not prove that the trusted firmware installed on a phone implements
the service, its operation numbers, or its return semantics.

The gate may compile only `ccci_ringbuf.o` and `ccci_hif_ccif.o`. It must not
link `ccci_ccif.ko`, install an object, enable Kconfig, add DT, create a service,
autoload CCCI, map modem memory, request IRQ/DMA resources, or execute an SMC.

## Linux 6.18 adaptation

- `from_timer()` becomes `timer_container_of()`.
- The non-synchronizing `del_timer()` becomes `timer_delete()`, preserving the
  original teardown semantics. Linux 6.18 documents `timer_delete()` as
  deactivating a pending timer without waiting for a callback running on
  another CPU and without preventing rearm, matching the old `del_timer()`
  contract. A future runtime patch must separately audit whether
  `timer_delete_sync()` or `timer_shutdown_sync()` is required by the owning
  stop/teardown path.
- Missing `MTK_SIP_KERNEL_CCCI_CONTROL` is defined as
  `MTK_SIP_SMC_CMD(0x505)`, exactly matching the B4.1 MediaTek SiP header.
  The definition is guarded so a kernel-owned definition takes precedence.

## Safe object-only command

Run this function only in fresh, disposable source trees after the pinned
Linux 6.18 configuration and `modules_prepare` have completed. A full kernel
and `Module.symvers` become mandatory at the later link/modpost boundary. This
function requests translation units directly and rejects any loadable CCCI
module:

```sh
ccci_ccif_compile_only() {
	kernel_tree=$1
	devmods_tree=$2
	moddir="$devmods_tree/drivers/misc/mediatek/eccci"
	hifdir="$moddir/hif"

	test "$(git -C "$kernel_tree" rev-parse HEAD)" = \
		d84b264a54a37611f2f46bc19363cb9b41606205 || return 1
	test "$(git -C "$devmods_tree" rev-parse HEAD)" = \
		ee2be53cb75670b548948636a0db1d1ff112bf12 || return 1
	test -s "$kernel_tree/include/generated/autoconf.h" || return 1

	make -C "$kernel_tree" M="$moddir" \
		ARCH=arm64 LLVM=1 \
		KERNEL_SRC="$kernel_tree" KERNEL_OUT="$kernel_tree" \
		DEVICE_MODULES_PATH="$devmods_tree" \
		CONFIG_ARM64=y CONFIG_MTK_ECCCI_DRIVER=m \
		CONFIG_MTK_SECURITY_SW_SUPPORT=n \
		CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n \
		CONFIG_MTK_AEE_IPANIC=n \
		KCFLAGS='-Werror=implicit-function-declaration -Werror=incompatible-pointer-types -Werror=int-conversion -Wno-error=format -Wno-error=format-extra-args -Wno-error=missing-prototypes' \
		hif/ccci_ringbuf.o hif/ccci_hif_ccif.o || return 1

	test -s "$hifdir/ccci_ringbuf.o" || return 1
	test -s "$hifdir/ccci_hif_ccif.o" || return 1
	test -z "$(find "$moddir" -name 'ccci*.ko' -print -quit)"
}
```

Do not replace the two object targets with `modules`, `ccci_ccif.o`, or
`ccci_ccif.ko`. Do not copy the resulting objects to a root filesystem and do
not run any CCCI object on a phone.

## Local result and next compile boundary

The patch applied to exact `ee2be53` with zero fuzz. A fresh Linux 6.18 tree
at exact `d84b264` was configured with the port's aarch64 config and prepared
with Clang/LLVM 21.1.8. The reviewed patch has SHA-512
`4589759c9818a361edff0392b23ee96fb77b2a728f0ce763a4ed2f8a423cf979263f085d05e2e19384f222894a27f8f05fe5d3d91321015b89ed57f14e7654a0`.
Both requested objects then compiled successfully:

```text
CC [M]  hif/ccci_ringbuf.o
CC [M]  hif/ccci_hif_ccif.o
```

No `ccci*.ko` was produced. There is no remaining compiler blocker inside this
two-object CCIF boundary. The first diagnostics are three non-fatal
missing-prototype warnings for `ccci_reset_ccif_hw`, `ccci_ccif_hif_init`, and
`ccci_hif_ccif_probe`; they are existing cross-file API declarations to audit
before link integration, not justification to make the functions `static`.

The next compile boundary is the separate CCIF integration/link audit. It must
inventory unresolved CCCI core, modem, platform, clock, IRQ and secure-call
dependencies before any `ccci_ccif.o` link or modpost gate is added. This patch
intentionally stops before that boundary.

The undefined-symbol audit confirms that boundary. In addition to normal
kernel timer, workqueue, clock and IRQ APIs, `ccci_hif_ccif.o` still requires
CCCI core/FSM/port/ring-buffer symbols and `__arm_smccc_smc`. These references
must remain unresolved here. Adding stubs merely to pass a link would hide the
unproven memory, interrupt and secure-firmware contracts.

## Runtime gate

No modem runtime probe is permitted from this patch. Before the first
observation-only driver can bind, the port must validate the LK/U-Boot
`ccci,modem_info_v2` handoff, all reserved-memory bounds and overlap checks,
installed trusted-firmware CCCI command/return semantics, IRQ and reset
ownership, IOMMU/MPU and DMA isolation, modem firmware identity, and SCP/CCCI
shared-memory ABI. That probe must exit without powering or resetting the
modem, mapping writable shared memory, requesting DMA/IRQs, or issuing an SMC.
USB NCM/SSH and Wi-Fi remain hard invariants for every later live gate.
