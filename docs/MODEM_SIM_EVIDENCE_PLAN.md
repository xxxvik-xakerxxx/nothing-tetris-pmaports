# MT6878 modem and SIM evidence plan

This document defines the smallest safe next step toward modem support on the
Nothing CMF Phone 1 (`nothing-tetris`). It does not promote modem support and
does not authorize loading a modem module or enabling a DT node.

## Source identity

- Current port branch: `codex/next-hardware`, current candidate recorded in
  `docs/CURRENT_STATUS.md`.
- The original source audit was performed on historical branch
  `codex/scp-thermal` at `cd8fbdf`; its vendor-source conclusions remain the
  input to the current compile-only work.
- Mainline kernel package source: Linux 6.18 at the commit pinned by the
  package.
- Authoritative vendor device modules:
  `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878`, commit
  `ee2be53cb75670b548948636a0db1d1ff112bf12`.
- The vendor commit identifies the Nothing OS 4.1 Tetris B4.1 source drop.
- Exact vendor commit metadata: authored by `lio.chen <lio.chen@nothing.tech>`
  on `2026-05-30T09:30:11+08:00`, subject `Merge codes for CMF by Nothing
  Phone 1 Nothing OS 4.1 (Tetris-B4.1-260415-1709)`. It is contained by the
  official `mt6878/Tetris/16b` remote branch.
- Older branch heads and the `codex/radio-ci` pmaports branch are not modem
  inputs. The latter contains CPU-idle and Wi-Fi power work only.

## Boot-chain trace

The installed boot path does not reproduce the Nothing OS modem handoff. A
newer U-Boot candidate now validates its structure but deliberately does not
start the modem:

1. The MediaTek early boot stages and stock LK execute before the replacement
   U-Boot container. Trusted firmware remains resident and may implement the
   MediaTek SiP ABI, but support for each CCCI request has not been measured.
2. Installed U-Boot `8aa048f93bb7569e4107ef85aa994c630f85de48`
   preserves the prior LK/FDT and conninfra handoff work but does not publish a
   validated CCCI contract to Linux.
3. Candidate U-Boot `b76e47e774304ab550a6354f3286860b7caffb3a`
   validates the bounded B4.1 descriptor, required payload tags, modem/check
   headers, image and shared-memory layouts. It publishes sanitized status and
   sizes only: no physical addresses, SMC call, power/reset, firmware load or
   `runtime-ready` claim. CI run `33492618726` passed, but this revision is not
   flashed yet.
4. The postmarketOS FIT embeds its own `mt6878-nothing-tetris.dtb` and loads it
   at `0x47000000`. The FIT configuration selects that FDT explicitly. No code
   in the current boot path copies `ccci,modem_info_v2`,
   `ccci,modem_info`, or the referenced LK tag buffer into this DT.
5. Linux therefore still lacks an enabled modem consumer and a proven runtime
   memory/power/secure-world contract. Adding disabled inventory or parsing a
   valid descriptor does not make the modem usable.

The B4.1 kernel expects `ccci,modem_info_v2` on the `mediatek,mddriver` node.
That property points to a physical LK tag buffer containing at least the modem
header table, image location/size, memory layout, check header and shared-memory
layout. The parser consumes keys including `hdr_count`, `hdr_tbl_inf`,
`md_mem_layout`, `md1_chk`, `md1img`, `smem_layout`, `nc_smem_info_ext`, and
`md1_phy_cap`. A legacy `ccci,modem_info` property is the only alternate LK
format.

If neither LK property exists, `ccci_util` falls back to DT-calculated memory.
That path still requires a reserved-memory node compatible with
`mediatek,reserve-memory-ccci_md1` or a complete `mediatek,ccci_util_cfg`
contract. Draft `0031` supplies neither, so the correct result is modem
disabled.

The vendor FSM does not load the modem image from Linux. `md_cd_start()` says
`modem image ready, bypass load`; it validates a check header copied from the LK
tag buffer and uses the preloaded MD bank address. A `request_firmware()` based
loader is not present in this path. A maintainable pmOS port therefore needs
one of two explicitly designed owners:

- reproduce the complete authenticated LK loader/handoff in the boot chain; or
- implement a Linux firmware loader with a documented signed-container and
  secure-world protocol.

Silently depending on whatever stock LK left in RAM is not an acceptable cold
boot contract.

## Status of draft 0031

`0031-arm64-dts-mediatek-mt6878-modem-foundation-disabled.patch` is inventory,
not a modem implementation. It adds disabled DPMAIF, CCIF, MD1 and CCCI-SCP
nodes and disabled SIM hot-plug nodes. It omits clocks, power domains, syscons,
regulators, reserved memory and firmware ownership, so no node can probe.

The transport register windows and IRQs match the B4.1 vendor DT:

| Block | Vendor evidence |
| --- | --- |
| DPMAIF | `0x10014000`, `0x1022d000`, `0x1022c000`, `0x1022e000`; SPI 238 and 259; hardware v3 |
| CCIF | `0x10209000`, `0x1020a000`; SPI 228 and 229; SRAM size 512 |
| MD1 | `0x0d180000`; watchdog SPI 491; AP platform 6878; modem generation 6299 |
| CCCI-SCP | `0x1023c000`, `0x1023d000` |

The SIM interrupt conversion is not proven. The B4.1 board DT uses the vendor
EINT cells `<0 8>` and `<1 8>`. The MT6878 pinctrl table identifies GPIO46 and
GPIO47 alternate functions as UIM0/UIM1 hot-plug, which supports the draft
hypothesis, but it does not prove that the vendor EINT indices map directly to
mainline Linux IRQ specifiers 46 and 47. CCCI obtains the SIM data through its
RPC ABI (`port_rpc.c`), including `sockettype` and `src-pin`; these nodes must
remain disabled and must not be represented as `gpio-keys`.

Static checks performed on the current draft:

- `patch -p1 --dry-run`: both DT files apply without fuzz or offsets to the
  prepared post-stable-patch Linux tree.
- `scripts/checkpatch.pl --strict`: 0 errors and 7 warnings. One warning is the
  external vendor commit not existing in the mainline repository; six are the
  intentionally undocumented vendor compatible strings. The compatible
  warnings prevent treating this DT as upstream-ready.
- A fresh DTB rebuild could not be repeated in this audit: host GNU Make 3.81
  is too old, the project path contains spaces, and the Docker runtime stopped
  while its temporary Alpine filesystem was read-only. The patch was reversed
  after each attempt and no modem node remains in the prepared source tree.

Conclusion: keep `0031` untracked and out of `APKBUILD`. Before integration,
either remove the unproven SIM IRQ nodes or add a separately reviewed EINT
translation with binding and live evidence. Disabled vendor compatibles alone
do not provide a maintainable interface.

Enabling only `mddriver` is not a passive probe. The B4.1 probe path enables
runtime PM and immediately calls `pm_runtime_get_sync()` with the vendor comment
`match lk on`. First boot then performs CCCI SMC boot checks, power transitions,
PLL setup and `MD_KERNEL_BOOT_UP`. No node from `0031` may be changed to `okay`
until that inherited-LK behavior is removed or replaced with an explicit,
validated handoff.

## Exact dependency chain

The B4.1 ECCCI stack is not a single driver. Its minimum path is:

1. `ccci_util`: parses boot arguments, modem image metadata and reserved-memory
   contracts and enables modem image security checks.
2. ECCCI core/FSM plus CCIF and DPMAIF HIF modules.
3. CCMNI for packet data and the CCCI port/RPC ABI for control, SIM and userspace
   channels.
4. MT6878 infracfg/topckgen clocks, MD power domain, MT6363 modem regulators and
   DPMAIF reserved DMA memory.
5. SCP IPI/shared-memory synchronization for the CCCI-SCP path.
6. Trusted firmware support for `MTK_SIP_KERNEL_CCCI_CONTROL`. Vendor code uses
   this SMC for power configuration, boot release, flight mode, clock requests,
   boot status, SCP synchronization and debug operations.

7. A legitimate, version-matched modem firmware image and modem memory layout.
8. A Linux userspace integration that exposes standard WWAN/ModemManager
   behavior without depending silently on Android daemons or userdata.

The current port has only partial prerequisites. It has generic MT6878 scpsys
groundwork and PMIC register definitions, but does not have a validated MD power
domain sequence, the required infracfg modem clocks, the bootloader/ATF modem
handoff, modem reserved memory, firmware provenance, or a standard userspace
control path.

## Current CCIF compile boundary

An isolated LLVM 21/aarch64 build against pinned Linux `d84b264a` and Nothing
OS 4.1 device modules `ee2be53c` now reaches the first CCIF-specific ABI
boundary without creating a module:

- `ccci_ringbuf.o`: compiles;
- an isolated compatibility patch replaces `from_timer()` with
  `timer_container_of()` and the old non-sync `del_timer()` with
  `timer_delete()`;
- `ccci_hif_ccif.o`: both timer errors are gone and the first failure is now
  the unowned `MTK_SIP_KERNEL_CCCI_CONTROL` dependency;
- `ccci_ccif.ko`: neither requested nor emitted.

The include-graph and timer patches pass dry-run, strict checkpatch and their
targeted object gates, but remain outside the active package. The timer lifetime
review preserves the old rearm-permitted non-sync semantics and does not approve
the vendor driver's broader missing teardown path for runtime. The secure
command must come from an authoritative firmware/LK contract rather than a
copied numeric constant.

### Memory and isolation trace

There are three separate memory contracts:

| Memory | B4.1 owner | Required behavior |
| --- | --- | --- |
| MD ROM/RW plus AP-MD shared memory | LK tag buffer or `mediatek,reserve-memory-ccci_md1` fallback | Address and size must be reserved before normal memory allocation; layout must match the signed image header and MD view. |
| DPMAIF cacheable pool | Dynamic reserved-memory node, size `0x190000`, 4 KiB alignment | Vendor driver obtains the region by compatible, converts it with `phys_to_virt()`, maps it for DMA and clears it. |
| DPMAIF non-cacheable pool | Dynamic `no-map` reserved-memory node, size `0x50000`, 4 KiB alignment | Vendor driver maps it with `ioremap_wc()` and clears it before use. |

The B4.1 DPMAIF node has no `iommus` property. The transport uses the Linux DMA
API, but the source does not prove that a mainline IOMMU domain isolates its
transactions. Modem memory protection is instead coupled to MediaTek EMI
MPU/SMPU callbacks, MD/AP memory-view negotiation and secure firmware. Until
those protections are represented and validated, DPMAIF must not perform DMA.

The dynamic DPMAIF reserved-memory nodes are also not passive inventory: they
reserve about 1.9 MiB during early boot even if transport probing is deferred.
They should be added only with the DPMAIF driver patch and exact binding, not to
`0031`.

### SMC trace

The exact B4.1 call is `MTK_SIP_KERNEL_CCCI_CONTROL`, MediaTek SiP command
`0x505`. Its request IDs include:

| Request | Use in vendor stack | Risk if called without contract |
| --- | --- | --- |
| `MD_CLOCK_REQUEST` | AP/MD source-clock ownership and wake/sleep state | Clock leak, stalled transition or invalid secure state |
| `MD_POWER_CONFIG` | BROM checks, LK/kernel boot stage, boot release and PLL stages | MD power transition, reset or boot from invalid memory |
| `MD_FLIGHT_MODE_SET` | Secure flight-mode state | Radio/power state divergence |
| `CCIF_CLK_REQUEST/RELEASE` | Secure CCIF clock arbitration | CCIF hang or leaked clock |
| `SCP_INFO_TO_SAVE`, `SCP_CLK_SET_DONE` | SCP shared-memory and clock synchronization | SCP/CCCI ABI corruption |
| debug/remap requests | MD register remap and dumps | Unauthorized or invalid MMIO mapping |

The source defines request numbers but does not prove that the currently
resident trusted firmware implements the same ABI or return semantics. A raw
SMC probe is not observation-only and is forbidden before an authoritative ATF
source or non-mutating capability interface is identified.

## Minimal next patch

The next code patch should be a **compile-only Linux 6.18 compatibility patch
for `ccci_util`**, generated from the exact B4.1 commit. It must not contain DT,
Kconfig defaults, package autoload policy, firmware, reserved-memory addresses,
or changes to CCCI power/reset behavior.

Required procedure:

1. Archive only `drivers/misc/mediatek/ccci_util` and its exact required headers
   from commit `ee2be53...`; never build the moving vendor branch head.
2. Build only `M=drivers/misc/mediatek/ccci_util` against the exact prepared
   Linux 6.18 kernel/config used by CI. Record the first compiler failure.
3. Adapt only real Linux API changes. Do not suppress implicit declarations,
   incompatible pointer types, integer conversions, or modpost failures.
4. Require `checkpatch`, clean patch application, successful object/module
   build, `modinfo`, and a reviewed unresolved-symbol list.
5. Keep the result outside `APKBUILD`, the rootfs and module autoload lists.
   Building the module is the whole experiment; loading it is explicitly out of
   scope because its init path parses modem boot arguments and memory contracts.

Only after `ccci_util` is clean should separate compile-only patches address
CCMNI, ECCCI core/FSM, CCIF and DPMAIF. `conn_md` and `mddp` remain excluded.
This ordering keeps the first failure attributable and avoids a monolithic
vendor-stack port.

The later runtime patch must add an explicit fail-closed handoff gate before any
platform driver registration or runtime-PM call. At minimum it must reject:

- absent or malformed `ccci,modem_info_v2`/legacy handoff;
- an image header whose platform, generation or memory size does not match;
- overlapping, non-reserved or unit-specific physical regions;
- missing DMA isolation/MPU ownership;
- unsupported CCCI SMC ABI;
- missing MD power domain, regulator or clock suppliers.

Failure must leave MD, CCIF and DPMAIF unpowered, with no IRQ requested and no
DMA mapping. It must not retry, reset SCP, reboot the phone or degrade USB/Wi-Fi.

## Evidence required before any live modem probe

All of the following are stop/go gates:

- Prove the bootloader and trusted firmware implement the exact CCCI SMC ABI
  used by B4.1, including return-value semantics. Do not test this by issuing a
  modem power or boot SMC first.
- Derive every modem and shared-memory region from authoritative partition/FDT
  metadata. Do not copy a physical address observed on one handset.
- Identify the signed modem firmware container, version/SKU selector, loading
  path and legal packaging boundary. Preserve per-device radio identity and
  calibration; never commit IMEI or calibration data.
- Add bindings and clock IDs for the MT6878 DPMAIF/CCIF/MD resources before a DT
  consumer is enabled.
- Implement and validate the MD power domain and regulator sequence without
  relying on state inherited from stock LK.
- Prove the SCP transport and shared-memory ABI independently; do not reset SCP
  or load/unload its owners during modem experiments.
- Trace the userspace control path from CCCI ports to a standard WWAN or
  ModemManager-visible interface. A `/dev/ccci*` node alone is not success.
- Establish a clean-boot rollback artifact and verify USB NCM/SSH, Wi-Fi and
  Bluetooth immediately before the test.

## First permitted live experiment

The first live experiment is observation-only: boot a CI image with all modem
DT nodes disabled and no modem modules installed, then record the current FDT,
reserved-memory map, boot arguments, firmware/partition metadata visible through
documented read-only interfaces, and ATF capability evidence. It must not call a
CCCI SMC, request modem IRQs, enable a regulator or power domain, map modem
memory, or load `ccci_util`.

### Read-only live gate

Run this only on the current clean CI image with the modem draft absent from the
active patch series:

1. Record kernel release, boot ID, bootloader artifact hash, slot, rootfs image
   commit and DTB hash.
2. Pass the existing USB NCM/SSH regression gate, including the 32 MiB transfer.
3. Keep one SSH control session. Record Wi-Fi association, routed traffic and
   Bluetooth controller state before and after collection.
4. Copy the live FDT from `/sys/firmware/fdt` through SSH and decompile it on the
   host. Record only property names, region boundaries and hashes; do not commit
   unique identifiers or payloads.
5. Capture `/proc/cmdline`, `/proc/iomem`, `/proc/interrupts`, loaded modules,
   `/sys/kernel/iommu_groups`, power-domain state where exposed, and the absence
   or presence of `/dev/ccci*`, `/dev/wwan*` and `/dev/cdc-wdm*`.
6. Verify that the live FDT has no enabled `mediatek,mddriver`,
   `mediatek,ccci_ccif`, `mediatek,dpmaif` or `mediatek,ccci_md_scp` consumer.
7. Search the FDT for `ccci,modem_info_v2`, `ccci,modem_info`,
   `mediatek,reserve-memory-ccci_md1` and the two DPMAIF reserved-memory
   compatibles. Presence is evidence to inspect, not authorization to map it.
8. Repeat the USB transfer and routed Wi-Fi check. Stop if either regresses.

Prohibited during this gate: `/dev/mem`, debugfs register writes, raw SMC calls,
`modprobe`/`insmod`, regulator or clock writes, runtime-PM forcing, SCP reset,
suspend, and any modem partition write.

The gate passes when the evidence bundle is complete, hashes are recorded,
USB/Wi-Fi remain unchanged and no modem owner was activated. It does not change
the subsystem status from `Broken`/`Untested`.

The first later module-load experiment is allowed only after the compile-only
series and every prerequisite above pass. It must start with one persistent USB
SSH control session, a clean boot, complete baseline logs and a defined fastboot
rollback. Stop at the first error or any USB/Wi-Fi regression and recover by a
clean reboot; do not unload/reload modem, SCP or connectivity modules.

## Definition of modem progress

Compile success is `Untested`, a bound driver is `Partial`, and a modem boot is
still only `Partial`. `Works` requires clean-install automatic initialization,
SIM detect/PIN, network registration, calls, SMS, mobile data, call audio,
airplane mode, recovery, warm reboot, suspend/resume and coexistence stress with
USB, Wi-Fi and Bluetooth intact.
