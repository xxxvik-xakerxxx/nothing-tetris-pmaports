# MT6878 GPU bring-up

## Current status

Installed r179 and loader `d385921` still have no GPU acceleration. The cold
authenticated GPUEB transform passed with 156064 signed bytes and unknown flat
format; its temporary plaintext was erased. Display/touch and automatic sensors
remain working, confirmed by the user after cold boot.

Actual U-Boot now includes a separate default-off private flat-retention path:
one authenticated transform, an exclusive erased-tail no-map reservation and
publication into an owned final DT. Full ARM64 objects and the opt-in image link
passed [CI 38027149560](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38027149560)
at `94ead1146c`. This image is not installed. The earlier CI caught incorrect
FDT pointer/lifetime handling; the final mapping now remains owned through
handoff. The paired read-only Linux analysis consumer passed native sanitizer
checks, isolated ARM64 compilation and modpost against actual kernel exports in
[CI 38028106842](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38028106842).
This is a minimal isolated kernel, not the phone's module ABI. A matching phone
ABI build is still required before one controlled private capture. The kernel
package now carries this optional module, with its source checked byte-for-byte
against the verified consumer. Ordinary DTs do not instantiate it; the next
package/image and lifecycle gates remain pending. Public CI
uploads metadata only, never plaintext.

This implements a missing firmware-inspection transport, not GPUEB startup.
Entry/data/BSS and the unauthenticated larger LK copy span, complete reset/power
ownership and accelerated Panthor rendering remain unresolved. See
[retention integration](../patches/gpu/flat-handoff-draft/HOOK-INTEGRATION.md).

## Earlier Supply Evidence

r177 candidate describes disabled USID-6 VBUCK2/VGPU and MT6363 VSRAM_CPUM
without attaching a GPU consumer. The existing MT6363 registration loop now
honours disabled children. A partial MT6315 provider cannot register VBUCK1
with a phase mask that also writes unowned GPU/VCORE outputs. Source/patch
tests are in `patches/gpu/`; live rail ownership is not established and no
render node or acceleration is claimed.

The separate VGPU observer diagnostic obtains one uncached, write-blocked
snapshot without regulator registration or voltage changes. CI builds a
separate boot artifact and checks its compiled DT delta, unchanged kernel
and initramfs, and all non-FIT boot-file contents. This is prepared for a
controlled test on the identified handset, not proof of GPU ownership,
electrical voltage, variant identity or acceleration.

2026-10-09, installed r175, Linux `6.18.0 #176`, boot
`aa136f81-1539-4455-a2f9-7eed5ffacc91`: fresh read-only inspection still finds display
`card0` only, no render node, no Mali platform device and no VGPU/VSRAM_CPUM
provider. SPMI currently instantiates USIDs 4, 5 and 9, not 6. No GPU MMIO,
clock-debugfs read or PMIC mode/voltage write was attempted.

r174 candidate adds `0109`: stop MT6315/MT6319 mode changes after either
current-mode read fails; requesting an already-normal mode is a successful
no-op. This protects the shared camera VMM/GPU VGPU provider before runtime
enablement. The CI harness executes the actual getter/setter over all four
rails, phase/LP bit patterns, requested modes and read/write faults, asserting
that errors cannot produce PMIC writes or disturb other rails. Patch application
and overlay checks pass. Validation-only CI
[37885933479](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37885933479)
passed the 16,384 actual-function mode/fault cases and rejected the
read-error-swallowing mutant. Full r174 kernel/image CI
[37886195992](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37886195992)
also passed; it has not been installed. Live PMIC behavior remains untested.
No supply or GPU consumer is enabled by this correction.

r175 candidate adds `0110` to select only available BUCK children from an
explicit `regulators` container before regmap setup. Missing/disabled rail
children are not registered without constraints; an empty/disabled container
fails with `-ENODEV`. The historical all-rail fallback is retained only when
the container is absent. No new DT node or PMIC transaction is introduced.
The actual helper has 512 presence/availability tests, reference-balance
checks and negative mutants; native validation CI
[37887268734](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37887268734)
passed, including the earlier 16,384 mode/fault cases. This validation-only run built no image.
Registering the actual
USID-6 provider still requires proving probe/shutdown and inherited rail
ownership, including regulator-core cleanup behavior.

The same r175 candidate includes `0111`: stop protected shutdown writes after
the first failed unlock, always attempt to clear both protection keys, and
return the first error instead of combining errno values with bitwise OR.
Successful register values/order are unchanged. The CI gate executes the
actual helper over all 32 fault combinations and rejects unguarded-write and
overwritten-error mutants. Native CI
[37894001985](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/37894001985)
passed these tests and the earlier mode/rail gates at `a5d72a1`. It does not
instantiate USID 6 or enable GPU rails. Full r175 CI `37894315052` passed at
`ba605b03d8bf`; verified artifacts were clean-installed and first-boot USB/SSH,
FIT identity and 32 MiB USB transfer passed. No USID-6 provider was instantiated.
Runtime VGPU/VSRAM ownership and acceleration are still not established.

**Do not read `clk_summary`, `clk_dump` or per-clock hardware-state debugfs
files on the current image.** The 2026-10-08 observation below caused an
external abort and reboot. Clock enumeration is not a passive hardware read.
The existing `check-live-idle-delta.sh` already avoids this operation.

2026-10-08: r171 adds board-described VBUCK1 forced-PWM phase selection
(`0108`), after the active-voltage-selector correction. Nothing B4.1
`ee2be53cb75670b548948636a0db1d1ff112bf12`, `mt6878.dts`'s
`mt6319_6_regulator`, sets `buck1-modeset-mask = <0x1>`. Mainline derives
`0xb` from USID 6 alone. The vendor board uses VBUCK1 for camera VMM,
VBUCK2 for GPU and VBUCK4 for VCORE; using `0xb` for a VBUCK1 mode change
would update all three force-PWM bits. The new optional binding property
`mediatek,buck1-mode-mask` describes existing board phase topology, never
configures coupling, preserves old defaults when absent and rejects invalid
masks before publishing them. No global descriptor is mutated. This is needed
before a provider/consumer DT can be enabled, not proof of rail ownership.

`scripts/check-mt6315-mode-mask.py` applies `0105` then `0108` and extracts
the actual selection helper for CI tests of all 16 USIDs, valid/invalid masks
and property-read failures. No DT node or PMIC write is introduced. Static
patch application passed. CI `37746161064` at `eb05019` passed 2464 native
helper cases and three mutation checks. The full kernel ABI build and actual
PMIC phase/rail behavior remain untested; this validation-only run produced
no install image.

### 2026-10-08 clock observation failure

Installed r168, kernel `6.18.0 #169`, boot
`2fd66df3-f3ac-47e5-8fcf-fe368b22f3f4`, retained loader `fef0154b`:
reading SPMI device links and GPIO ownership completed. SPMI exposed USIDs
4, 5 and 9, not 6. GPIO ownership listed no requested main-camera GPIO1,
23, 25 or 93; absence of a Linux owner does not prove electrical safety.
The following filtered read of `/sys/kernel/debug/clk/clk_summary` aborted
before its USB post-check. No module, regulator, GPIO or DT write was issued.

`systemd-pstore` archived the evidence in
`/var/lib/systemd/pstore/console-ramoops-0` (the live pstore directory was
empty). At monotonic 57890.530823 it records a synchronous external abort
`0x96000010`, task `grep`, with this stack:

```
regmap_mmio_read32le -> _regmap_bus_reg_read -> _regmap_read
-> regmap_read -> mtk_cg_bit_is_cleared -> clk_core_is_enabled
-> clk_summary_show_subtree -> clk_summary_show -> seq_read
```

The register argument is `0xe00`. The pinned MT6878 IMP IIC wrapper gate
tables use that status offset. The trace does not identify which wrapper or
its physical mapping, and does not implicate MFG PLL rate readback. Resolve
the actual provider/mapping and its power/access ownership before changing
clock callbacks; do not return fabricated enabled states or turn on unrelated
power domains to suppress the abort. No second read was attempted.

The phone rebooted to `890665d4-245f-4e72-88d2-14a3bf438dc6`; USB NCM/SSH
recovered and systemd reported no failed units. The user confirmed that the
display, touch and autorotation work after recovery. No new image was flashed. Device wall time lagged
the host date, so boot IDs and monotonic timestamps identify this incident.

GPU acceleration is `Broken`. The stable image intentionally has no Mali
platform device, so Panthor cannot probe and no render node is expected.
`CONFIG_DRM_PANTHOR=m`, `CONFIG_MTK_IOMMU=y`, and the MFG clock foundation
from patch `0009` are present. This is build support, not proof that the GPU
power, clock, firmware, or memory paths are usable.

Read-only device check on 2026-10-07, r168 cold boot
`2fd66df3-f3ac-47e5-8fcf-fe368b22f3f4`: DRM exposes display `card0` only,
with no render node. Registered regulator names include the existing MT6369
and connectivity supplies, but no MT6319 VBUCK2/VGPU or VSRAM_CPUM provider.
This confirms that enabling Panthor alone would not close the supply chain.
No regulator voltage/state read, MMIO access or GPU probe was performed.

The compile-only prerequisite is now enforced by
`scripts/check-panthor-compile-only.sh` and documented in
`docs/PANTHOR_COMPILE_ONLY.md`. It links `panthor.o`, traces the pinned
NothingOSS hardware inventory, and rejects any shipped GPU DT node or autoload
rule. Full package CI builds and inspects `panthor.ko`. This adds no runtime
integration.

The VGPU readback prerequisite is enforced by
`scripts/check-panthor-vgpu-readback.py`. It compiles the pinned Nothing OS 4.1
MT6315 callback and the pinned mainline regulator helper into a host-only fake
regmap test, then proves that an enabled VBUCK2 rail is read from DBG0 by the
vendor path and ELR2 by unpatched mainline. Patch `0105` now implements the
vendor active/off readback contract in the mainline MT6315 driver: DBG4 bit 0
selects DBG0 versus ELR; either read error is propagated. Voltage writes,
enable/mode operations and DT availability are unchanged. The source harness
also exercises the actual patched callback and rejects stale-selector/error
mutants. r168 CI/runtime verification remains pending. This is a driver
implementation change, not a runtime rail measurement or a working GPU.

Candidate `c8f02ca` additionally stages a compile-only MT6363 VSRAM_CPUM
descriptor and enables the existing MT6319-compatible regulator provider
config. There is still no VSRAM/VGPU DT child or GPU consumer, so the candidate
does not register or switch a GPU rail at runtime.

Patch `0052` inventories the separate MFG RPC register block and nested domain
IDs 1, 2, 3, 5, 9 and 10. Both the outer `mfg_rpc` syscon and inner provider
remain disabled, and every domain carries `KEEP_DEFAULT_OFF`; the shipped DT
therefore creates no platform device and reads or writes no MFG RPC register.
This is static topology evidence only, not a usable GPU power provider.

Live logs only prove that the inherited device tree reserves the following
memory and that the generic IOMMU core starts in translated, strict mode:

- `mblock-46-me_GPUEB_SHARED`, 1536 KiB
- `mblock-40-me_GPUmputab_PMA`, 6144 KiB
- `mblock-14-me_gpu_reserved`, 2048 KiB

They do not prove MFG power sequencing, GPUEB startup, GPU MMU operation, or
successful access to GPU registers.

The phone also exposes slot-specific `gpueb_a` and `gpueb_b` partitions, 2 MiB
each. The vendor Linux GPUEB driver attaches to MMIO, mailbox and reserved
memory but does not implement a complete firmware loader, so preloader/LK or
secure firmware likely owns this image and startup. This is an inference from
the partition and driver contract, not a validated handoff. These partitions
must not be copied into rootfs or confused with Panthor CSF firmware, which is
requested separately as `arm/mali/arch<major>.<minor>/mali_csffw.bin`.

## Authoritative source trace

The reference device-module source is Nothing OS 4.1 for Tetris at commit
`ee2be53cb75670b548948636a0db1d1ff112bf12`. The matching external-module
source is commit `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`.

The vendor stack describes:

- Mali CSF hardware at `0x13000000`, using interrupts 271/270/269 plus
  vendor-only event and power interrupts;
- MFG0 shutdown control at SPM offset `0xeb4`;
- MFG RPC domains 1, 2, 3, 5, 9, and 10 below `0x13f90000`;
- MFG PLL and stack PLL controls at `0x13fa0000` and `0x13fa0c00`;
- the GPU rail as MT6319 USID 6 VBUCK2, with a 300000-1193750 uV range;
- GPUEB mailbox/firmware ownership and GPUMPU/protected-memory helpers;
- a 265-1300 MHz vendor OPP table controlled through gpufreq/SCMI.

The vendor MFG0 scpsys domain has a bypass-initial-power-on policy. Mainline
MediaTek scpsys normally powers an instantiated domain during provider
registration unless it carries `MTK_SCPD_KEEP_DEFAULT_OFF`. This difference
is a hard requirement before a DT MFG0 child can be exposed.

## Patch 0035 assessment

`0035-pmdomain-mediatek-mt6878-mfg0-data.patch` is the smallest safe GPU
foundation currently available. It adds only dormant domain data and does not
add a DT power-domain child or a GPU node. The generic provider instantiates
only available DT children, so this patch cannot switch MFG0 by itself.

Static validation on the exact Linux 6.18 source and the pmdomain portion of
patch `0018`:

- strict checkpatch: 0 errors, 0 warnings;
- patch apply check: passed without fuzz;
- `drivers/pmdomain/mediatek/mtk-pm-domains.o`: compiled successfully with
  `ARCH=arm64 LLVM=1` in an amd64 Alpine container.

The register offsets, SRAM bits, status bits, and both bus-protection masks
match the Nothing OS 4.1 source. `0035` is already in the active package but
adds no DT child, so it has no runtime effect or functional benefit on its own.

## Patch 0052 assessment

`0052-pmdomain-mediatek-mt6878-mfg-rpc-inventory.patch` applies with zero fuzz
after all 39 active mainline-kernel patches on exact source `d84b264a`. Direct
preprocessing and DT compilation pass; the remaining unit-address and
reserved-memory warnings predate this patch. The new binding also passes local
YAML lint. Full `dt_binding_check` remains a CI gate because local `dtschema`
is unavailable.

Sparse domain IDs are deliberate. The generic scpsys driver rejects an
undefined ID because its `sta_mask` is zero, and onecell lookup returns
`-ENOENT` for an unregistered hole. Nested domain traversal does not honor a
child domain's `status`, so the safety boundary depends on both provider levels
remaining disabled. Enabling the provider would immediately read each control
offset and would permit later consumers to write it; that is forbidden until
clock, reset, SRAM and firmware ownership are complete.

## Blocking dependencies

1. **Safe genpd policy.** Patch `0035` already supplies
   `MTK_SCPD_KEEP_DEFAULT_OFF` for MFG0; still prove that registering the domain
   leaves SPM `MFG0_PWR_CON` unchanged before any GPU consumer is added.
2. **GPU regulator.** Mainline DT still has no MT6319 USID 6 VBUCK2 GPU supply.
   The candidate enables the compatible provider module and inventories
   VSRAM_CPUM without a DT consumer. VGPU voltage/mode handling, enable state,
   provider USID and cold-boot ownership must be validated before adding a
   disabled DT child, and the first probe must not change either rail.
3. **MFG RPC and clocks.** Patch `0052` inventories the disabled RPC subdomains,
   while patch `0009` provides PLLs and top muxes. Neither proves gate/reset/SRAM
   ordering, stack clock, or vendor SCMI/GPUEB frequency ownership.
4. **Firmware.** Panthor derives
   `arm/mali/arch<major>.<minor>/mali_csffw.bin` from the live GPU ID. No CSF
   firmware is packaged in this port. The exact GPU ID, redistributable
   firmware source, header compatibility, and hash remain unknown.
5. **Memory protection.** The vendor Mali node has no external `iommus`
   property and the Panthor binding does not require one; Panthor manages the
   Mali MMU directly. However, MT6878 GPUMPU, protected-memory, reserved-memory
   ownership, and secure-monitor interactions are not ported. A generic IOMMU
   startup line is not evidence for these paths.
6. **Thermal and lifecycle.** Read-only LVTS zones must be live-validated
   before load. GPU power-off, warm reboot, suspend/resume, fault recovery,
   and USB NCM/SSH invariants have no evidence yet.

## Next safe sequence

1. Keep the proven reboot-to-fastboot rollback while GPU remains absent.
2. Complete the MT6319 USID 6 VGPU provider description with no enabled
   consumer; verify binding, voltage/mode tables and cold-state ownership.
3. Validate the disabled MFG RPC inventory in CI and confirm no platform device
   or register access appears on a clean image.
4. Complete MFG0/MFG RPC clock, reset, SRAM and firmware ownership, then use a
   separate diagnostic DT to prove provider registration does not alter power
   state or USB/Wi-Fi behavior.
5. Identify and package the exact Panthor CSF firmware by GPU architecture.
6. Add a disabled standards-compliant MT6878/`arm,mali-valhall-csf` node. Validate
   binding and DT first; enable it only in a recovery image with a persistent
   USB control connection and an immediate fastboot rollback path.
7. Require three cold probes, render-node creation, short offscreen rendering,
   thermal observation, power-off, warm reboot, suspend/resume, and concurrent
   USB transfer before promoting GPU support beyond `Partial`.
