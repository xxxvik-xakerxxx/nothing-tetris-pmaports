# Native SENINF PM and capture lifecycle draft

New files only. Controller9 and all previous camera bundles remain unchanged.
No C/native/kernel build, phone operation, production linkage, or DT activation.
This is executable PM and probe/start/retire integration code, not a claim that
the root V4L2 capture driver or complete DT supplier graph is shipped.

## Pinned source

Modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`:
`mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-drv.c`:

- `seninf_core_pm_runtime_get_sync`: both native domain devices.
- `runtime_resume`/`runtime_suspend`: CAM gates before CSI, CAMTM source,
  reverse release. The unused CSI selectors/PLL options are NOT all enabled.
- `set_vcore_power`: VCORE lower-bound vote precedes selecting CSI parent.
- `set_csi_clk`: CSI enable then parent selection; port0 uses TOP_SENINF,
  port1 TOP_SENINF1, AP step0 source is the 312MHz provider.
- `data_rate2vcore_voltage`: threshold comparison, with CPHY data rate
  `mipi_pixel_rate * 10 * 7 / (3 * 16)` for these matching modes. The proven
  module rate is 700800000, NOT V4L2 PIXEL_RATE/PCLK 878400000.

Device `ee2be53cb75670b548948636a0db1d1ff112bf12`:
`arch/arm64/boot/dts/mediatek/mt6878.dts`, SENINF core node:
two domains, 12 named clock handles, step0 seven cells, VCORE supplier,
named resource banks/counts. Threshold and voltage are read from DT. No source
value is inferred from one handset. Higher VCORE from another consumer is valid
for vendor's minimum vote; step0's last two cells are two lane-configuration
voltages, not a voltage maximum. New overlay fixes that old controller check.

The native PM helper deliberately does not reproduce vendor MMDVFS/VCP calls,
AOV ownership, global TSREC timer writes or unrelated clocks. Linux genpd,
clock and regulator providers must perform the actual requested transitions.
No provider is replaced with a successful stub.

## Production path and ownership

`mt6878-seninf-pm.c`: domain usage refs, CAM gates/CAMTM, VCORE vote, selected
CSI clock and source. Every ledger bit follows a successful provider operation.
Failed unwind retains affected suppliers; failed PM put restores the consumed
usage ref with get_noresume, not a fabricated active state. Old CSI parent is
protected by Linux clock-rate exclusivity and restored only if still owned;
only this consumer's VCORE vote is removed, never
a sampled global voltage. No automatic retry after a first resume failure.

`native-pm.patch` is applied AFTER frozen controller `native-bind.patch` in an
isolated staging tree. It adds private native PM state/callbacks and actual
resource export/bind inside graph.c; links platform stop to the native capture
abort owner; corrects unused-clock and voltage checks; distinguishes no DMA
attempt from post-DMA reset quiescence. It is NOT a frozen-source modification.
Existing nvmem calibration remains mandatory and has no numeric fallback.

`mt6878_native_capture_probe` binds concrete existing direct/platform/native
SMI backends, allocates coherent CQ through the real IOMMU DMA owner and binds
the controller to the actual SENINF resources/sensor. No MMIO at probe.
Platform keeps an explicit pointer to its persistent native owner; stop does
not derive an enclosing allocation blindly from arbitrary subdev hostdata.
The caller is the persistent native media/video owner, NOT a temporary probe
stack. `mt6878_native_capture_frame` owns supplier PM gets, proven CAM_MAIN
reset, route preparation, coherent CQ/vb2 submit, CAMSV IRQ arm and receiver
native stream-on. It takes real ACTIVE raw/meta vb2 buffers and negotiated
recipe configuration; no CCD process, private ioctl or RPMSG endpoint.

Stop work serializes against actual stream-on with platform.lifecycle. It
never takes capture.lock, avoiding capture.lock -> lifecycle versus worker
lifecycle -> capture.lock deadlock. Receiver/core/queue lock order remains
the frozen controller's. Reset failures retain source-proven SMI clamp lease;
retirement refuses to discharge an incomplete reset.

## Failed stream-on cleanup

Linux core updates enabled_pads only on successful enable callback. Therefore
failed receiver/sensor ON makes ordinary disable return EALREADY without
invoking driver cleanup. Native stop inspects enabled state under active-state
mutex: successful ON uses native disable; failed/unstarted ON has exactly one
owned abort attempt (IRQ drain, sensor native disable if really enabled or
sensor core s_power(0) otherwise, actual route disconnect). It never interprets
EALREADY as stopped. Sensor-off error prevents source_stopped/disconnect proof.
Repeated abort returns the stored cleanup error/EALREADY without another write.
The original ON failure remains in capture/direct first_error.

An error result from direct_stop can be the preserved original ON failure even
AFTER successful reset. Retirement uses the actual hw_attempted/quiesced
observations, not error==0 as a readiness flag. Failed DMA reset cannot release
CQ/buffers. Successful cleanup can release resources while preserving the
original failure separately. Probe unwind errors are not discarded: parent
must retain storage/work/devres if an owned asynchronous cleanup has not drained.

## Exact remaining closure (not activation-ready)

- Persistent root video driver registration/notifier and raw/meta vb2_ops
  invocation of these probe/frame/retire functions are still absent. This
  draft does not advertise a registered /dev/video node or a capture command.
- CAM_MAIN mapping/reset serialization must be borrowed from its native owner,
  not re-ioremapped while camsys clock provider owns it. Native SMI common31
  clamp API must be linked with its provider patch and actual common31/larb
  supplier nodes. No fake regmap or shared consumer raw MMIO.
- Complete native TOP_SENINF/TOP_SENINF1 and AP-step0 parent clock provider
  mappings, CAM_MAIN/CSI_RX genpd, DVFSRC VCORE regulator and provisioned rg_csi
  nvmem must resolve. A valid zero calibration remains accepted with provenance.
- Existing resource getter expects a distinct already-bound IOMMU port owner.
  A future self-owned CAMSV platform probe must explicitly fix that API's
  device_is_bound/self-link requirement using real iommu_get_domain_for_dev;
  it must not self-defer forever or fake DMA ownership.
- Parent removal/unbind policy must retain storage/devres on failed retirement.
  Graph suppress_bind_attrs and platform module refs help but cannot make
  hot DT node removal safe. No production driver registration until this is
  closed. Do not turn a failed probe cleanup into success or free pending work.

`activation-disabled.dtsi` is an incomplete disabled topology research include
after0055, not a complete supplier declaration. It keeps sensor/SENINF disabled,
adds their matching CPHY link and pinned resource/DVFS metadata. It deliberately
omits unknown provider phandles and CAMSV outbound endpoint rather than invent
them. No DTC validation or activation is claimed.

## Integration and gates

Add PM C/H, capture C/H and native-smoke to the existing isolated closure;
compile PM/capture/smoke plus overlaid graph/controller/platform. Reuse the
existing coherent CQ, vb2, route/PHY, native SMI and calibration objects. Native
capture and graph functions need a common linked archive or explicit GPL symbol
exports when split; this draft makes neither production linkage change.
`generate-pm-overlay.py --check` and patch application are read-only/static.

`failed-start-test.c` is a kernel KUnit integration fixture requiring CONFIG_KUNIT,
MEDIA/V4L2_SUBDEV_API and the actual capture/controller/route objects. It uses
real V4L2 enabled-mask handling with failed sensor/receiver enable, verifies
EALREADY, calls the actual native abort and tests sensor cleanup success/error,
single invocation/no repeated writes, original failure retention and disconnect
gating. Its MMIO backend is an in-memory fixture, not hardware evidence.
It still requires CI compile/run; local native C builds are forbidden.

After supplier/root registration/removal closure: one matching RAW/PDAF frame,
failed stream-on fault injection with actual cleanup and error retention,
threaded IRQ drain/reset, vb2/CQ retirement and cold repeat with display,
touch, sensors and USB networking preserved. Until then camera remains Untested.
