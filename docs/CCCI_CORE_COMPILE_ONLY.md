# CCCI core Linux 6.18 compile-only evidence

## Scope

- Vendor source: `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878`
  at `ee2be53cb75670b548948636a0db1d1ff112bf12` (Nothing OS 4.1,
  Tetris B4.1).
- Kernel source: `MT6878-mainline/linux` at
  `d84b264a54a37611f2f46bc19363cb9b41606205` (Linux 6.18).
- The proposed gate compiles only `eccci/ccci_core.o` and `eccci/ccci_bm.o`
  after the pinned kernel and its `Module.symvers` have been built.
- The gate must not link a module. It must reject any `ccci*.ko` emitted in the
  ECCCI directory, and image CI must reject `ccci_md_all.ko` or `ccci_all.ko`
  in the rootfs.

No DT, Kconfig default, package, autoload, firmware, reserved-memory access,
DMA, IRQ, SMC, modem power/reset, CCIF, DPMAIF, CCMNI, FSM or port object is in
this boundary. The resulting objects must never be loaded on a device.

## Linux 6.18 adaptation

`ccci_core.c` uses the pre-6.4 `class_create(owner, name)` API in both built-in
and module code paths. `0048-vendor-eccci-core-linux-6.18-api.patch.vendor`
removes only the obsolete owner argument. The compile gate treats implicit
function declarations, incompatible pointer types and integer conversions as
errors.

## Why this subset is not runtime-safe

`ccci_core.o` can create the CCCI device class and call buffer-manager init.
`ccci_bm.o` allocates and maintains shared packet pools. Compiling these files
proves kernel API compatibility only; it does not prove the modem handoff,
memory map, DMA isolation, secure-monitor ABI or power sequence.

The objects intentionally retain unresolved references that belong to later
CCCI layers. They are not linked, installed or advertised as modem support.
CI evidence must record the first compiler failure, final object list and the
absence of any ECCCI loadable module.

## Local compile result

The exact vendor commit was exported with `git archive` and compiled in an
isolated Alpine container with LLVM 21 against the prepared pinned Linux 6.18
tree. Patch application used zero fuzz. Both requested translation units
completed successfully:

```text
CC [M]  ccci_core.o
CC [M]  ccci_bm.o
```

Both outputs are LLVM IR bitcode and no `ccci*.ko` was emitted. The first
causal Linux 6.18 failure before `0048` is the removed two-argument
`class_create()` API; no additional compiler failure remains in this subset.

The undefined-symbol audit is consistent with an intentionally unlinked
subset. `ccci_core.o` references the kernel device/OF APIs plus
`ccci_dump_write` and `ccci_subsys_bm_init`. `ccci_bm.o` references normal
SKB/workqueue APIs, CCCI logging, and its intra-subset buffer-pool entry points.
This is compile evidence only, not a link or runtime result.

## Blockers before the first safe runtime probe

1. Prove LK/U-Boot provides a valid, bounded `ccci,modem_info_v2` or documented
   legacy handoff for every supported Tetris SKU.
2. Describe modem ROM/RW and AP-MD shared memory as reserved memory, validate
   all ranges and reject overlap before any mapping or write.
3. Prove the exact trusted-firmware `MTK_SIP_KERNEL_CCCI_CONTROL` commands and
   return semantics used by the installed firmware.
4. Add fail-closed ownership for modem regulators, clocks, resets and power
   domains without relying on warm-boot state.
5. Establish IOMMU/MPU ownership and DMA masks before enabling DPMAIF.
6. Compile and audit ECCCI FSM, CCIF, DPMAIF, port/RPC and CCMNI as separate
   boundaries, with no packaging or autoload.
7. Verify CCCI-SCP shared-memory/IPI ABI without disturbing the working sensor
   SCP path.

8. Prove SIM1/SIM2 EINT pin ownership and debounce from authoritative board
   data; do not request the IRQs before the modem handoff gate passes.
9. Define a standard WWAN/ModemManager userspace interface and firmware
   provisioning path; `/dev/ccci*` alone is not functional modem support.

The first follow-up CCIF build now proves `ccci_ringbuf.o` but fails closed in
`ccci_hif_ccif.o` at removed `from_timer()`/`del_timer()` APIs. It also exposes
the unresolved `MTK_SIP_KERNEL_CCCI_CONTROL` dependency. No CCIF patch or
module is integrated until timer lifetime and secure ABI ownership are reviewed
as separate boundaries.

The first runtime experiment is allowed only after a probe-only driver can
validate every handoff and dependency above, then exit with the modem, DMA,
IRQs and shared memory untouched. USB NCM and Wi-Fi remain hard invariants.
