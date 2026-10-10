# Hardware operations draft, not activation-ready

Frozen direct/platform files unchanged. No probe, DT, shared manifest, C build
or phone operation. New kernel producer supplies RESOURCES/IOMMU/IRQ gates and
native CAMSV MMIO. ROUTE/STOPPED explicitly fail ENOLINK: no current native
receiver stream/VC/CAMMUX consumer proves these boundaries. This is not complete
capture support or a successful owner placeholder.
SENINF MMIO uses the existing provider's borrowed 0x18000 mapping, never a
second ioremap. Reads/writes require the bound receiver's active runtime PM.
Factory requires this mapping; backend does not advertise an unmapped region.

## Exact pinned operations

Modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835:
- `mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c`, sv_reset_by_camsys_top,
  lines 366-418: SMI common clamp, SCQ RESET 0/1, bit1 poll 1us/100000us,
  SCQ reset clear, CAM_MAIN_SW_RST_1 0/(3<<(sv_id*2))/0 and clamp clear.
  On timeout clamp is deliberately retained. Parent owns shared reset lock
  and CAM_MAIN provider mapping; no independent mapping of shared CAM_MAIN.
  Resume-reset refuses enabled IRQs or a MMIO-attempted capture transaction;
  it is not a live DMA recovery/reset shortcut. Parent serializes arm/submit.
- Same file lines 825-855 and toggle_tg_db lines 777-789: exact prefix of
  common_disable through CMOS_EN clear. tg_off does NOT perform the following
  DMA reset or claim DMA stopped. SEN_MODE TG_MODE_OFF bit11/CMOS_EN bit0,
  VF_CON VFDATA_EN bit0, PATH_CFG SYNC_VF_EN_DB_LOAD_DIS bit8 are from unions
  in the matching mtk_cam-sv-regs.h. No new ready poll is invented.
- `mtk_cam-seninf-drv.c`, dev_read_csi_efuse lines 1343-1376 and
  csi_efuse_value_verify lines 1417-1454: receiver nvmem cell rg_csi, five
  5-bit calibration fields at shifts7/12/17/22/27 plus physical port folded
  checksum. All-zero calibration fields bypass checksum exactly as vendor.
  Zero is not conflated with failed provenance. Require a four-byte cell,
  retain DEFER/errors, and sample the actually enabled CSI clock. Negotiated
  module trail/mode/trios remain separate, not filled with guessed defaults.

Device ee2be53cb75670b548948636a0db1d1ff112bf12:
- `drivers/memory/mtk-smi.c` lines 3196-3219: common clamp writes one port
  at a time to SET0x3c4/CLEAR0x3c8 and reads STATE0x3c0. Ports originate in
  mediatek,comm-port-id (lines4351-4354), common ID from mediatek,common-id.
  This draft validates the complete property before MMIO, skips u32(-1), and
  requires the provider's actual registered regmap, powered device and shared
  reset lock. No physical address, port mask or calibration from one phone.
  Empty/unused-only memberships fail before writes; state read bypasses cache.

## Real missing interfaces

Upstream 6.18 `drivers/memory/mtk-smi.c` does not expose a regmap/common clamp
API, common-id or comm-port-id table. Its private struct mtk_smi/base cannot
be reinterpreted as vendor ABI. Main integration must add an owned native SMI
provider operation or provider regmap with stable uncached SET/CLEAR/STATE
semantics, full reset serialization, power/lifetime, and correct DT membership.
Until then hardware_clamp returns EOPNOTSUPP before SCQ/CAM_MAIN reset writes.
The vendor void debug API and its empty CONFIG-disabled inline are NOT used.

The PHY calibration data ABI is known: rg_csi four-byte nvmem cell on the
matching SENINF receiver node. Missing cell/provider is an actual error, not
fallback. Native binding must select that node/physical port before calling;
this helper cannot infer port from arbitrary device names. The remaining PHY
IRQ/MAC/TSREC owners and CAMMUX VC/tag programming are not solved by the cell.

No standard legacy s_stream getter proves sensor-off. Frozen platform invokes
actual sensor/receiver s_stream(0), but graph-only receiver lacks its native
implementation. STOPPED cannot be enabled by setting platform.drained or a
calibration verified bit. Likewise native CQ cannot prove SENINF VC routing.
No receiver MMIO is performed from hardware.verify, matching frozen contract.

Integration: new hardware C/header/smoke alongside platform/direct and frozen
SENINF PHY headers/data. Object-only targets mt6878-camsv-hardware.o and
hardware-smoke.o; enable REGMAP and NVMEM in addition to existing dependencies.
Provider/runtime gates still pending. Never attach this partial backend to a
live streaming node. Parent must serialize TG/reset controls with capture and
retain all provider/clock/DMA lifetime on failure.
