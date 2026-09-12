# CCCI FSM, port and DPMAIF Linux 6.18 compile-only evidence

## Boundary

This gate continues after the common CCCI boundary in commit `3156401`. It
uses `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878` commit
`ee2be53cb75670b548948636a0db1d1ff112bf12` (Nothing OS 4.1, Tetris B4.1)
and `MT6878-mainline/linux` commit
`d84b264a54a37611f2f46bc19363cb9b41606205` (Linux 6.18).

The package requests 39 individual translation units:

- the 14 remaining objects from the module-mode FSM list, excluding
  `ap_md_mem.o`, which patch `0089` already covers;
- all 13 port objects included by the module-mode `ccci_md_all` aggregate;
- the 12-object DPMAIF module list with `CONFIG_PAGE_POOL=n`.

This is the minimum complete vendor Makefile boundary for those three groups.
It excludes the separate CCCI-SCP FSM module, the optional DPMAIF page-pool
object, CCMNI, `conn_md` and `mddp`. It does not link `ccci_md_all.ko` or
`ccci_dpmaif.ko`.

## Linux 6.18 adaptation

Patch `0095-vendor-eccci-fsm-port-dpmaif-compile-only.patch.vendor`:

- exposes the pinned device-module `include/` directory to ECCCI;
- supplies the vendor CCCI command number when the mainline MediaTek SiP
  header does not define it, without adding an SMC call;
- uses `hrtimer_setup()`, `timer_delete()`, `skb_frag_fill_page_desc()`, the
  void-return `dma_set_max_seg_size()` contract and GPIO descriptor debounce;
- adds direct scheduler-clock and vmalloc declarations; and
- keeps the DEVAPC-only timeout state behind its matching configuration guard.

No DT, Kconfig, probe registration, module registration, IRQ request, DMA
allocation/mapping, power/reset sequence, firmware operation or new secure
call is added. The source objects retain existing dormant modem boot, power,
IRQ, DMA and SMC paths; object compilation does not execute them.

The patch SHA-512 is
`e4585a88cd8ade032d02dc6795fd720c886e3714291316078dcb0ea470494537ce0fec6662ffc3a3a98d4610f936b0d0db32b5af57e60a50d075f6bf87000627`.

## Validation

The package build runs after the complete kernel build and directly requests
only the listed `.o` targets with hard errors for implicit declarations,
incompatible pointer types and integer conversions. It checks representative
`ccci_fsm_init`, `ccci_port_init` and `ccci_dpmaif_drv3_init` definitions and
rejects any ECCCI `.ko` output. `package()` never copies these objects.

The clean local build used Alpine Clang/LLVM 21.1.8 against a prepared kernel
tree built with LLVM 21.1.2. All 39 objects compiled. Existing
missing-prototype and format warnings remained visible; none was promoted into
an ABI change. The resulting group evidence was:

| Group | New objects | Total bytes | SHA-256 of sorted object checksum manifest |
| --- | ---: | ---: | --- |
| FSM | 14 | 5432336 | `53ef2a3cd7ad5ed29cf9fd1bb28932811662809f08a4a7ef3a63772531a08b7d` |
| Port | 13 | 4940492 | `cc456575a26408ccf5ed0ba16cbb4af41886f300f9dda0df73b385526627385a` |
| DPMAIF | 12 | 5315312 | `eace94e856f1b1f738722edc347eff06021900b524706d8b88c66d9e36bc252e` |

These are local debug-object identities; embedded source paths make them
evidence for this run rather than path-independent reproducible hashes.

The 39 objects contained 467 unique undefined names before internal
resolution. Definitions within the selected set resolved 226 of them, leaving
241 external kernel and vendor dependencies. No module was linked or emitted.
This unresolved inventory is expected and blocks loading.

Static validation checks patch ordering, exact object targets, the disabled
page-pool option, representative symbols, patch-scope exclusions, package
absence, rootfs absence and autoload absence.

## Status and next gate

Modem, SIM, registration, calls, SMS and mobile data remain `Broken`. There is
still no validated bootloader memory handoff, trusted-firmware CCCI contract,
power/reset/clock ownership, IRQ/DMA isolation, firmware selection, DPMAIF
page-pool compatibility, CCMNI integration or userspace modem interface.

Before any link or runtime experiment, resolve and classify the remaining 241
external references against the earlier CCCI objects, kernel exports and
excluded vendor subsystems. Then stage the optional page-pool and CCMNI pieces
as separate compile-only boundaries. Runtime work remains blocked on the
bootloader, memory, secure-call, power, IRQ, DMA, firmware and recovery gates.
