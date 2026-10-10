# Native SENINF first-frame controller (review draft)

No DT activation, production linkage, local C compilation, or device testing.
This is a one-frame IMX882 RAW/PDAF consumer, not an ISP/libcamera pipeline or
continuous capture implementation. No CCD process, new ioctl, or RPMSG service.

## Source provenance

Modules pin: `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`.
Under `mtkcam/camsys/isp7sp/cam/`:

- `mtk_csi_phy_3_1/mtk_cam-seninf-hw_phy_3_1.c`:
  `get_csi_irq_status` / `debug_current_status` MAC and CSI status ACKs;
  CPHY debug status/clear; `record_vsync_info` mux overrun ACK `0x103`.
- `mtk_csi_phy_3_1/mtk_cam-seninf-csirx_mac_csi0.h`: MAC A/B enable bits,
  G1 enable/status, IRQ_CLR_MODE bit31; bit15 is not an enable.
- `mtk_csi_phy_3_1/mtk_cam-seninf-seninf1-mux.h`: IRQ enable bits0..3.
  The ACK value `0x103` is NOT an IRQ enable mask.
- `mtk_csi_phy_3_1/mtk_cam-seninf-seninf1-csi2.h`: asynchronous FIFO IRQ
  enable bit28. Its status has the vendor full-word clear above.
- `mtk_csi_phy_3_1/mtk_cam-seninf-cammux-gcsr.h`: global enable mask
  `0x333`, VSYNC enable low32/high11. Inherited services are rejected, not
  silently disabled or acknowledged by this consumer.
- `mtk_cam-seninf-tsrec.c`, `mtk_cam-seninf-tsrec-regs-def.h`:
  `tsrec_n_settings_clear`, `tsrec_intr_reset`, `tsrec_regs_iomem_init`.
  Engine off, read-clear mode, VSYNC/HSYNC interrupt disable, VC/DT clear.
  Readback verifies actual engine/enables are zero; no timer/ready poll.
- `mtk_cam-seninf-route.c`, `get_vcinfo_by_sensor`: RAW group RAW1=1;
  PDAF default group ALL=0, both VC0. Frozen route maps SAT mux*8 to CAMMUX.

Device pin: `ee2be53cb75670b548948636a0db1d1ff112bf12`,
`arch/arm64/boot/dts/mediatek/mt6878.dts`, SENINF core:
base size0x18000, ana-rx size0x30000, named SENINF/TSREC interrupts,
12 clocks, two domains, six TSREC engines, `cdphy-dvfs-step0` seven cells.
Actual CSI clock and VCORE voltage must match this provider tuple. No rate,
voltage or calibration value is invented or taken from a test handset.

## Executable integration

Stage the existing combined camera closure plus these four kernel files:
`mt6878-seninf-controller.c`, `.h`, `mt6878-seninf-events.h`,
`controller-smoke.c`. Add isolated object targets for controller and smoke.
Keep all existing objects; this introduces real external controller calls in
graph/hardware, not shipping archive linkage. Required config remains media,
V4L2 subdev active-state, PM, regulators, clocks, IOMMU and vb2 DMA-contig.

Apply `imx882-native-streams.patch` to the sensor after frozen0112. Apply
`native-bind.patch` to staged basename graph/route/platform/hardware sources.
These are review overlays, not replacement frozen source files. The generator
reads current main (including corrected PHY setup argument order) and changes
only the displayed hunks. Patch email metadata/sign-off is integration-owned.

1. Native media controller acquires the validated sensor/receiver/CAMSV
   pipeline, provider/device/module refs, domain and clock/rail refs.
2. Embed exactly one controller in the actual SENINF owner, borrow its existing
   mappings/suppliers, call bind. Native pad stream ops are required before
   requesting IRQs. Both IRQ lines are exclusive, initially NO_AUTOEN.
3. Prepare with negotiated layout before direct submit. Preparation allocates
   actual interface/two SAT mux/two CAMMUX destinations and disables TSREC,
   then runs frozen calibrated PHY and VC/CAMMUX recipes. Unsupported inherited
   GCSR/dynamic routes fail before the first programming write.
4. Submit coherent CQ/vb2 buffers through existing direct API under its lock;
   hardware ROUTE gate reads actual successful controller transaction state.
   Arm CAMSV and use `v4l2_subdev_enable_streams(receiver, 1, 1)`.
5. Receiver threaded IRQ samples both MAC halves, masks owned enables,
   performs only source-proven ACKs and schedules existing CAMSV stop work.
   G1 status clear is unproven: mask, retain snapshot, report error. No G1 ACK
   write; no controller reset or buffer completion in receiver IRQ.
6. Stop worker drains CAMSV IRQs outside queue lock, native receiver disable
   drains SENINF IRQ outside core/queue lock, stops sensor with real error
   propagation, then disconnects outer/inner CAMMUX. STOPPED gate verifies
   these observations before CAMSV reset; it does not require post-reset
   `quiesced` (which would form a cycle).
7. Only after existing direct stop proves reset/quiescence, controller release
   retires PHY/IRQ/allocation. Then platform retirement may release pipeline
   and provider refs. Failed cleanup retains refs/storage; no retry/reuse claim.

Lock order: receiver active-state -> controller core -> direct queue -> sensor
active-state. IRQ never acquires core or receiver state; IRQ drain never holds
core/queue. CAMSV gates acquire neither core nor active-state while queue is
held. Controller state mutations used by those gates hold core + queue.
Parent lifecycle serializes bind/prepare/start/stop/release and cannot destroy
the embedded storage or devres on a failed retirement.

Sensor native callbacks use its existing active-state/control mutex, not a
second nested lock. ACTIVE format changes reject an owned media pipeline.
Initial power-off cleanup uses the standard core s_power(0) callback and
rejects an active native stream; stream enable owns power-on. We deliberately
do not call post_streamoff without a preceding pre_streamon. Legacy s_stream
stop can swallow errors in the pinned Linux core and is not shutdown proof.

## Remaining real blockers and next gate

Graph runtime_resume still returns EOPNOTSUPP and rejects required OPPs.
This draft does NOT replace that with success: the real SENINF PM/DVFS provider
must acquire/program/retain its two domains, 12 clocks and VCORE, and expose
borrowed resources to the embedded controller. The actual capture probe must
call bind/prepare/start, connect the provider-owned SMI reset backend, and
serialize removal against failed teardown. No such calls are currently shipped.
Calibration consumer remains frozen route's nvmem rg_csi lookup with explicit
provenance (verified zero is valid), not a numeric fallback.

Immediate CI gate: native `controller-test.c` with frozen mux/PHY/route headers;
controller + smoke ARM64 objects; rebuilt overlaid graph/hardware/platform,
route and sensor objects in the same isolated closure. Fixtures cover both
ports/MAC halves, preserving IRQ_CLR_MODE, inherited IRQ rejection before
writes, TSREC failed-write first-error retention and successful-write/no-effect
readback failure. The in-memory fixture does not simulate hardware W1C or prove
threaded callback lifetime. Runtime gate remains default-off until real PM and
probe binding exist; then a single-frame RAW/PDAF capture, injected failure,
IRQ drain/reset and DMA retirement must pass without display/sensor/USB loss.
