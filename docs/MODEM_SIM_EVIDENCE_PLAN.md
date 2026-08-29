# MT6878 modem and SIM evidence plan

This document defines the smallest safe next step toward modem support on the
Nothing CMF Phone 1 (`nothing-tetris`). It does not promote modem support and
does not authorize loading a modem module or enabling a DT node.

## Source identity

- Port branch at review time: `codex/scp-thermal`, commit `cd8fbdf`.
- Mainline kernel package source: Linux 6.18 at the commit pinned by the
  package.
- Authoritative vendor device modules:
  `NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878`, commit
  `ee2be53cb75670b548948636a0db1d1ff112bf12`.
- The vendor commit identifies the Nothing OS 4.1 Tetris B4.1 source drop.
- Older branch heads and the `codex/radio-ci` pmaports branch are not modem
  inputs. The latter contains CPU-idle and Wi-Fi power work only.

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
