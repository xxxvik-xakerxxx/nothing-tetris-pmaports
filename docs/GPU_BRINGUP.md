# MT6878 GPU bring-up

## Current status

GPU acceleration is `Broken`. The stable image intentionally has no Mali
platform device, so Panthor cannot probe and no render node is expected.
`CONFIG_DRM_PANTHOR=m`, `CONFIG_MTK_IOMMU=y`, and the MFG clock foundation
from patch `0009` are present. This is build support, not proof that the GPU
power, clock, firmware, or memory paths are usable.

Candidate `c8f02ca` additionally stages a compile-only MT6363 VSRAM_CPUM
descriptor and enables the existing MT6319-compatible regulator provider
config. There is still no VSRAM/VGPU DT child or GPU consumer, so the candidate
does not register or switch a GPU rail at runtime.

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
match the Nothing OS 4.1 source. Keep `0035` out of the stable package queue
until the reboot-mode change has passed CI and live validation; it has no
functional benefit on its own.

## Blocking dependencies

1. **Safe genpd policy.** A later patch must add
   `MTK_SCPD_KEEP_DEFAULT_OFF` for MFG0 and prove that registering the domain
   leaves SPM `MFG0_PWR_CON` unchanged before any GPU consumer is added.
2. **GPU regulator.** Mainline DT still has no MT6319 USID 6 VBUCK2 GPU supply.
   The candidate enables the compatible provider module and inventories
   VSRAM_CPUM without a DT consumer. VGPU voltage/mode handling, enable state,
   provider USID and cold-boot ownership must be validated before adding a
   disabled DT child, and the first probe must not change either rail.
3. **MFG RPC and clocks.** Patch `0009` provides PLLs and top muxes only. It
   does not model the MFG RPC subdomains, gate/reset ordering, stack clock, or
   vendor SCMI/GPUEB frequency ownership.
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
3. Add MFG0 keep-default-off policy and a disabled DT domain node. On a clean
   image, prove provider registration does not alter the MFG0 register or
   USB/Wi-Fi behavior.
4. Model MFG RPC clocks/domains and validate register ownership against B4.1.
5. Identify and package the exact Panthor CSF firmware by GPU architecture.
6. Add a disabled standards-compliant MT6878/`arm,mali-valhall-csf` node. Validate
   binding and DT first; enable it only in a recovery image with a persistent
   USB control connection and an immediate fastboot rollback path.
7. Require three cold probes, render-node creation, short offscreen rendering,
   thermal observation, power-off, warm reboot, suspend/resume, and concurrent
   USB transfer before promoting GPU support beyond `Partial`.
