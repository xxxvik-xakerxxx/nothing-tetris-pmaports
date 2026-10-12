# Native CAMISP DMA supplier candidate

Default-off research integration. No shipping Kbuild/Kconfig, package, DT node,
clock, regulator or hardware activation is changed. Existing drafts and vendor
checkouts are preserved. No camera frame or working hardware claim.

## Exact B4.1 topology

Nothing device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`,
`Tetris-B4.1-260415-1709`, `arch/arm64/boot/dts/mediatek/mt6878.dts`:

* CAMSV-B: logical camisp-l13-1, larb13 CQI port0/WDMA port1;
  physical larb13, one CAM_MAIN_LARB13 APB clock, CAM_MAIN power domain;
  parent common16, then common31, then display common0.
* CAMSV-A: logical camisp-l14-1, larb14 CQI port0/WDMA port1;
  physical larb14, one CAM_MAIN_LARB14 APB clock, CAM_MAIN power domain;
  parent common19, then common31, then display common0.
* Commons16/19 each have seven clocks, in DT order: CAM2MM0/1_GALS,
  LARB13, LARB14, LARB29, CAM_MRAW, MRAW_GALS, MRAW_LARBX.
* Common31 has one CAM_VCORE_MM0_DCM_DIS APB clock and CAM_VCORE genpd.
  Genpd hierarchy is MM_INFRA -> CAM_VCORE -> CAM_MAIN.
  CAM_VCORE/VMM supply belongs to scpsys (`cam-vcore-supply`, MT6319 VBUCK1),
  not the logical DMA device. No new independent regulator/reset writes.

Modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`, same B4.1 tag,
`mtkcam/camsys/isp7sp/cam/mtk_cam-larb.c`, establishes the logical port identity,
34-bit DMA mask and maximum segment size. `trace-b41.py` reads the exact Git
objects without changing either checkout.

## Native ownership and ordering

`provider.patch` extends the existing Linux SMI/IOMMU providers after packaged
0070 and the existing camera-smi-owner overlay. It uses their owned DT mappings,
actual clock handles, genpd and public IOMMU component state. Camera larbs get
one clock, camera subcommons get all seven; generic display larb0/common0 retain
their existing clock behavior. Missing/malformed camera IDs fail closed;
only the explicit two-clock root-common0 shape permits the missing common-id
used by the packaged display fixture. Dynamic camera nodes/ancestors are refused.

Linux driver-core DMA configuration attaches the logical port before its probe.
The IOMMU master first binds real physical SMI components, then the default DMA
domain supplies port mask/bank metadata. The logical driver requires that actual
domain, exact two port IDs and unique bound physical supplier. It never creates
or attaches a domain itself, interprets private IOMMU structs, or remaps MMIO.
It reuses platform-owned DMA parameters and restores original metadata on unwind.

IOMMU root discovery walks the MT6878 multi-common chain with cycle/depth checks
and balanced node references; other SoCs keep the existing two-level path.
`consumer-pm.patch` adds runtime-PM ordering to the actual CAMSV -> CAMISP link.
Managed PM links then order CAMISP -> physical larb -> common16/19 -> common31
-> common0. Probe itself does no clock enable, PM resume or MMIO access.

Runtime resume enables the real clock set before SMI register restoration.
Larb13/14 restore only CQI/WDMA NORMAL_DOM bank0 translation, explicit vendor
bandwidth values, command throttle and SW flag; foreign bank/SYSRAM routes fail.
Zero-filled misc-array padding is never treated as an offset-zero register write.
Commons16/19/31 restore eight explicit bandwidth entries and three explicit misc
entries. No guessed sleep/reset sequence, secure call or firmware layout is added.
Logical and physical suspend check both external/internal larb busy registers;
busy refusal retains PM state/clocks. The exported synchronous idle operation
uses device_trylock and releases that lock before returning.

## Teardown and activation limits

Managed device links own ordering, and module/device references preserve object
identity. They do **not** veto forced supplier withdrawal or preserve devres
after an unsafe consumer remove. There is no persistent kthread/device-lock
lease. Only the synchronous idle read excludes provider removal for that call.
Long-lived DMA needs parent-controlled cooperative teardown exclusion: stop and
drain native capture, prove DMA/PHY OFF, release queues and PM references, then
permit supplier unbind. Failed stop must retain that exclusion and all owners.
Forced physical unbind, module withdrawal, live DT-property/overlay changes and
DMA across suspend are unproven and forbidden activation paths for this candidate.

Required activation producers are still the real CAM_MAIN/CAM_VCORE genpd/VMM
and clock providers (including CAM_VCORE and MRAW gates), complete disabled-first
DT supplier description, and proven native consumer retirement. These sources
describe those dependencies; this change neither fabricates them nor enables DT.
CAMSV/CAM_MAIN joint reset remains owned by the existing capture/reset path.

## Validation scope

Source-only checks cover input topology, PM/attach order, unknown ports/banks,
padding, cycles, signed OF-count comparisons and deterministic overlay generation.
The established research runner stages exact new source bytes and overlays,
compiles the real CAMISP DMA, SMI and IOMMU ARM64 objects, and records source/object
hashes. All three are also rebuilt with KUnit disabled. The SMI TU includes five
private KUnit cases when enabled.
[CI 38225925800](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38225925800)
passed at `b41ea66b5a94de59f93bf1dd0d02e76ebd7baac1`: actual CAMISP, SMI and
IOMMU translation units compiled as AArch64 LLVM bitcode with KUnit enabled and
disabled. Both configurations retain real MTK_SMI/MTK_IOMMU/PM providers.
Artifact archive SHA256:
`ab48bbb8cecc890a6b10010d7598c7b36c855b982d808a5bf2732830f402e262`.
No KUnit fixture has been executed and no hardware was exercised. This is
object compilation, not linked drivers, clean installation or a camera frame.
No local native compilation or handset command is part of validation.
