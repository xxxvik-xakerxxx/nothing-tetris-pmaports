# B4.1 CSF And Panthor Activation Gates

## Actual Asset And Format Result

Private CI stock asset: `vendor/firmware/mali_csffw.bin`, 290816 bytes,
SHA256 `81bef7649fc3c056fae347c4511dd9d2f80f081dc07ac6c4ad9c8fbb7c302f56`.
No binary or binary payload is committed or copied by this checker.

Offline `csf_preflight.py` passes against the exact cached kernel Panthor
sources under `linux-d84b264a54a37611f2f46bc19363cb9b41606205`. The script pins
the firmware loader, devfreq and device-init source hashes and rejects changed
sources until re-audited. This is conservative structural validation, not
native parser execution, runtime ABI validation or hardware authentication.

- Header magic 0xc3f13a6e, binary header version **0.3**. Panthor supports
  major 0; minor 3 is not rejected. This is NOT the host/firmware interface version.
- Metadata table ends at 960; 26 aligned bounded entries. No unknown mandatory
  entry. Types 5, 7, 9 are optional and Panthor ignores them. Known config/trace/
  timeline types are also ignored, rather than implemented by our checker.
- Eight section entries, seven active; the protected section at 0x03000000
  is ignored by Panthor. Protected-content support is not established.
- Active VA ranges/data bounds/flags pass. 4096-byte VM pages are required
  by the small sections; current config uses CONFIG_ARM64_4K_PAGES=y.
- Shared section 0x04000000..0x0400c000, 49152 bytes, initialized from 8192
  bytes at file offset 282624 and ZERO-fill for the rest. Its initial control
  version word is zero: the running MCU must initialize it. Do not forge that
  word or claim runtime ABI compatibility from the file header.
- Build metadata SHA `9f6c2edbe24cc5a5ffcf23c56c04bc01c21b7009`.

Commands for main's existing assets (no downloads/builds):

```sh
python3 patches/gpu/test_csf_preflight.py
python3 patches/gpu/csf_preflight.py "$CSF_ASSET" --kernel-tree "$KERNEL_TREE"
```

The CLI defaults to the exact B4.1 asset digest. `--gpu-id` accepts a separately
observed GPU_ID and reports the request_firmware path; it never reads registers.
Panthor constructs `arm/mali/arch<GPU_ARCH_MAJOR>.<GPU_ARCH_MINOR>/mali_csffw.bin`
using bits31:28 and27:24 of actual powered GPU_ID. Do not derive architecture
from header v0.3, install a guessed arch path, or add a firmware-path fallback.
Packaging this legitimate asset at that verified path is a main integration
edit; no APKBUILD/shared workflow change is made here. Existing config has
CONFIG_DRM_PANTHOR=m and CONFIG_PM_DEVFREQ=y; module presence is not activation.

## Probe Is Not A Read-Only Diagnostic

`panthor_device_init()` initializes clocks and devfreq BEFORE
`pm_runtime_resume_and_get()`, GPU identification, MMU and firmware loading.
`panthor_devfreq_init()` sets OPP regulator name **mali**, gets/enables optional
**sram**, then calls `dev_pm_opp_set_opp()`, which enables/configures the mali
rail when supplied. Its target uses `dev_pm_opp_set_rate()`. Generic Panthor
assumes regulator coupling and holds supplies for device lifetime.

Our read-only MT6315 observer is not a writable regulator/coupler or power
owner. Do not attach it as mali-supply, supply dummy success, omit required
rails to hide the missing owner, or let OPP and GPUEB DVFS independently
control the same voltage/clock resources. Before DT activation, choose and
implement one audited owner for domain transitions, OPP voltage/frequency,
coupling, rollback and suspend/resume. Avoid writing stock PLL/rail controls
behind running GPUEB's back.

## Concrete Hardware Dependencies

Pinned device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`,
`arch/arm64/boot/dts/mediatek/mt6878.dts:6390` describe:

- GPU registers 0x13000000/0x480000; vendor compatible is mediatek,mali plus
  arm,mali-valhall, neither matches Panthor. Any future Panthor node must use
  its audited binding, not activate the vendor Android node verbatim.
- JOB GIC_SPI271, MMU270, GPU269, EVENT272, PWR273. Panthor requests lowercase
  job/mmu/gpu for the first three. Do not assign PWR273 to Panthor: GPUEB
  mailbox ownership already depends on that IRQ. Route and ownership need
  compiled-DT validation; no IRQ request is performed by this audit.
- Vendor GPUFREQ supply links are VGPU USID6/VBUCK2 and VSRAM CPUM. They are
  NOT proof that direct Panthor regulator ownership is safe. GPUEB owns the
  vendor transition/DVFS ABI; current provider inventory remains disabled.

Panthor requires a real core clock (first clock; optional coregroup/stacks),
MMIO/IRQ ownership, working genpd hierarchy, valid OPP/coupling contract,
DMA addressability and its GPU-internal MMU. Do not add an unrelated SoC
IOMMU phandle or dummy clock as a shortcut. The current MFG-RPC inventory in
0052 and MFG0 data in0035 are not a functioning GPU power provider; 0118's
source-grounded command6 backend still needs the real GPUEB owner/session.

## Relationship To B4.1 RV33 And Next Gates

CSF firmware runs on the Mali MCU, not GPUEB RV33. Its availability removes
the missing-CSF-asset blocker but does not replace GPUEB firmware or power
ownership. The declared B4.1 LK/ATF audit in `GPUEB_B41_TRACE.md` proves RV33
selector1 transform ABI, NOT plaintext expansion or a physical OFF procedure.
Stock fixed copy258744 vs authenticated ciphertext156064 remains unresolved.

1. Main's authenticated RV33 transform-only CI/fault gate, then one controlled
   transform-only boot and private plaintext layout inspection. No GPU start.
2. Implement real GPUEB whole-SRAM/GPR/mailbox controller ownership, boot IRQ
   ordering, reservations/EMI and physical OFF/error contract before load/start.
3. Validate live GPUEB session INIT_SHARED_MEM and audited command6 power
   transitions with USB/sensor invariants. No Panthor during this owner gate.
4. Establish GPU_ID and actual clock/regulator/OPP ownership; package CSF at
   the corresponding arch path. Validate compiled diagnostic DT and object CI.
5. Only then one controlled Panthor activation: firmware boot, nonzero runtime
   CSF interface version, valid group/stream bounds/IRQ acknowledgement, render
   node and accelerated render. Finish lifecycle/thermal/suspend and compositor
   gates before marking GPU Works. No rail/DT/phone operation occurred here.
