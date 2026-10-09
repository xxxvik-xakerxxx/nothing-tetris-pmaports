# MT6878 SENINF Resource And Graph Candidate

Status: **Untested**, not camera capture. This is a separate patch from the
frozen IMX882 0112 sensor change. No board DT, package or global CI is edited.

## Concrete Implementation

`0114-media-platform-mediatek-mt6878-seninf-graph.patch` adds a platform
receiver subdevice with sink/source pads, active/try format state and an
async sensor notifier. A parent capture/media device must register this
subdevice before its sensor notifier can form a usable media graph.

The sensor link validates C-PHY, explicit identity trios [0,1,2], matching
line order and polarity, normal RAW10 Bayer format, and both exact packets:
VC0/DT0x2b image, VC0/DT0x30 PDAF blob. Mode dimensions are restricted to
4000x3000 and 4096x2304; PDAF height is image height/4. This matches frozen
0112's source-derived frame descriptors, not arbitrary packet-routing success.

The custom media-entity link validator calls the sensor before taking the
receiver state lock. The generic V4L2 link validator holds both active-state
locks, which would deadlock the IMX882 non-state frame-descriptor callback.

Probe strictly obtains and reserves/maps `base` (0x18000 bytes) and `ana-rx`
(0x30000 bytes), resolves both named IRQs, acquires all 12 named clocks,
VCORE supplier and CSI efuse cell. It does **not** dereference MMIO, enable
clocks/supplies, change voltage, read efuse, request IRQ handlers, allocate
DMA or call sensor stream-on. Missing dependencies fail visibly.

Both CAM_MAIN and CSI_RX genpd devices are attached by explicit names,
without runtime device links or resume requests. Cleanup uses power_off=false.
OPP-bearing graph nodes are rejected because even genpd attachment may apply
a required performance state; DVFS is not implemented in this candidate.
Runtime-resume and stream-on explicitly return -EOPNOTSUPP.

## Pinned Source Chain

- Device modules `ee2be53cb75670b548948636a0db1d1ff112bf12`,
  `arch/arm64/boot/dts/mediatek/mt6878.dts`, `seninf_top`.
- Modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`,
  `mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-drv.c`,
  `mtk_cam-seninf-def.h`, `mtk_csi_phy_3_1/` and MT6878 platform source.
- The matching core has PHY3.1, 12 SENINF instances, 13 muxes, 43 camera
  muxes and 6 TSREC blocks. ISP7S/PHY3.0 is not the MT6878 implementation.
- Vendor runtime-resume gets both domains before the cam/seninf/camtg gates,
  enables CAMTM/TSREC, then selects CSI clock parents and applies VCORE DVFS.
  None of that is copied as an unconditional graph-probe operation.
- Vendor SENINF has **no iommus property**. RAW/YUV/CAMSV/MRAW nodes own the
  actual memory ports. This receiver rejects misplaced IOMMU ownership.

The pinned DT has 13 clock phandles but only 12 clock names: an extra CAM
MMDVFS reference is unnamed/commented out. This discrepancy is not silently
accepted: the graph-only description requires exactly the 12 named clocks.
The full DVFS/OPP/MMDVFS owner still needs an explicit future contract.

## Future Disabled Node Contract

Use a **new, disabled** compatible `mediatek,mt6878-seninf-graph`, not the
vendor core compatible. It describes one full physical CSI port (string
`csi-port = "0"` or `"1"`) on the shared top resource. Do not instantiate
multiple copies claiming the same two MMIO regions. No split-port support.

Required resources are the pinned named MMIO/IRQ/clock resources, explicit
`dvfsrc-vcore-supply`, `rg_csi` nvmem cell, exactly two domains named
`cam-main`, `csi-rx`, and two graph endpoints: port0 C-PHY sensor input,
port1 downstream capture output. Input must explicitly declare bus-type1
and data-lanes [0,1,2]. No iommus, required-opps or operating-points-v2 in
the resource-only node. This is an isolated bring-up description, not a
drop-in conversion of the full vendor node or authorization to power it.

## Main Integration And Next Gate

Add 0114 and checksums to the package; CI-select
`CONFIG_VIDEO_MT6878_SENINF_GRAPH=m`. Compile
`drivers/media/platform/mediatek/seninf/mt6878-seninf-graph.ko` and run
`sh patches/camera-seninf/run-contract-tests.sh` with ASan/UBSan in CI only.
Use `check.py` with `--device-repo`, `--modules-repo`, `--kernel-tree` to
validate exact source inputs and apply the patch offline.

Before any runtime DT activation, validate clock and domain providers,
VCORE/DVFS ownership, CSI efuse ownership and the concrete downstream media
entity. Then audit PHY3.1 port-specific C-PHY calibration/settle/deskew,
CSI MAC interrupt acknowledge, mux allocation, TSREC lifecycle and RAW/CAMSV
packet routing. The downstream capture owner must supply IOMMU-backed DMA
queues, buffer limits, CCU/firmware ownership where required and ordered
stream teardown. Only after those exist can the explicit stream/resume
rejection be replaced by a controlled hardware transaction.

Resource registration or graph linkage does not demonstrate received frames.
No native/kernel build or phone operation was performed by this task.
