# Native restricted SENINF route (review freeze)

Status: source implementation, not hardware capture support. No DT activation,
probe registration, shared manifest changes or local C builds. Native fixtures
and ARM64 objects must run in CI before integrating a live consumer.

## Authoritative source

Modules commit `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`:

- `mtkcam/camsys/isp7sp/cam/mtk_csi_phy_3_1/mtk_cam-seninf-hw_phy_3_1.c`:
  `mtk_cam_seninf_set_reg` MAC0=analog+0x5000, MAC1=analog+0xd000;
  SENINF CSI2=base+0xa00+intf*0x1000, mux=base+0xd00+mux*0x1000,
  CAMMUX PCSR=base+0x17000+id*0x40, GCSR=base+0x17f00.
  `SET_DI_CTRL`, `SET_DI_CH_CTRL`, `reset_dt_remap`, `remap_dt`, `set_vc`,
  `set_cammux_src`, `set_cammux_vc`, `SET_TAG`, `set_cammux_tag`,
  `set_cammux_chk_pixel_mode`, `cammux`, `disable_cammux`,
  `switch_to_cammux_inner_page`, `enable_cam_mux_vsync_irq`.
- Same directory `mtk_cam-seninf-{seninf1-csi2,csirx_mac_csi0,cammux-pcsr,
  cammux-gcsr}.h`: exact offsets/field masks. CAMMUX status clear is 0x103;
  this does not establish a CAMSV DONE acknowledgment.
- `mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-hw.h`: IDLE_SRC_SEL=0x7f.
- `mtkcam/imgsensor/inc/imgsensor-user.h`: REMAP_TO_RAW10=1.
- `mtkcam/camsys/isp7sp/cam/mtk_cam-seninf-route.c`: SAT_MUX_FACTOR=8,
  `mux2mux_vr_` and `get_vcinfo_by_sensor` (both VC0 packets offset=0),
  `mtk_cam_seninf_s_stream_mux` outer setup and explicit inner-page finalize.
  Physical mux index is NOT the CAMMUX source code. The restricted plan uses
  distinct allocated SAT muxes 0..2 and encodes each as mux*8+VC0 offset.
- Matching IMX882 mode/descriptor source already frozen in 0112: normal
  VC0/DT0x2b RAW10 and VC0/DT0x30 PDAF, width x (height/4), RAW10 remap.
  Geometry describes CSI packets, not emitted DMA bytes, stride or sizeimage.

Device commit `ee2be53cb75670b548948636a0db1d1ff112bf12` remains the
authority for MT6878 resource suppliers/clock choices, inherited through the
frozen PHY and hardware calibration helpers. No numeric calibration fallback.
`arch/arm64/boot/dts/mediatek/mt6878.dts:5991` defines SAT mux 0..2,
muxvr 0..23 and CAMMUX 0..15. Native prepare reads all three two-cell range
properties from the actual receiver and rejects missing/mismatched metadata.
Main must carry that sourced metadata when integrating; this draft changes no DT.

## Executable path

`route_prepare` requires the existing native receiver's retained core/page
mutex, active PM/CSI clock, bound stopped IMX882 and an exclusive, enabled,
non-dynamic media pipeline link. It reads actual sensor format, C-PHY bus and
both frame descriptors. Module timing is restricted to the two audited modes.
The frozen calibration helper reads the receiver's per-port `rg_csi` nvmem
cell and actual held clock. Zero data remains independent of verified provenance.

Before the first PHY write: validate both allocated routes, verify existing
POWER/IRQ/ROUTE/TSREC owners, reject inherited CAMMUX enable/dynamic switching
and shared global-drop IRQ state. Then run frozen calibrated PHY recipe,
MAC DT-remap, DI/CH groups, both frozen mux recipes and actual CAMMUX routing.
Each CAMMUX is programmed on outer and live inner pages, with next source,
matching the source's explicit FINALIZE operation. Preflight reads the currently
selected page; the native allocation/IRQ provider must exclude inherited
activity on both pages, not treat this limited read as a global reset proof.
All addresses are resource-relative. Allocated mux/group/pixel-mode values
come from the native owner, never an inferred width or one handset address.

`route_matches` supplies a cached successful-programming proof for the exact
CAMSV job/tag assignment without receiver MMIO. Call while core_lock is held.
It must replace only the ROUTE branch of main's hardware verifier; existing
RESOURCES/IRQ/STOPPED checks remain mandatory. It is not an unconditional
replacement verifier.

After real coherent CQ/vb2 submit, `route_source_on` checks actual submitted
transaction, its tags/geometry, unchanged CSI clock and sensor descriptor,
then invokes native sensor `s_stream(1)`. No CCD service is needed. Failed
stream-on is conservatively considered attempted and requires actual stop.

Receiver `s_stream(0)` should call `route_source_off`: actual sensor stop,
owned CAMMUX VSYNC disable, idle next/current source, enable clear, four tag
pages cleared, proven status ACK and mux disable on both outer/inner banks.
It does NOT switch off PHY,
drop supplier refs or claim DMA idle. Shared global drop IRQ is not touched.
First start error survives cleanup; failed disconnect is not retried and
does not produce a disconnected proof. Retain all resources on failure.

Controller task must drain CAMSV IRQs outside the queue mutex, stop TG/VF and
reset CAMSV through the native SMI lease helper. Only after actual transaction
quiescence may `route_retire` invoke frozen PHY shutdown, which independently
requires sensor/CAMMUX/DMA and MAC/PHY IRQ/TSREC quiescence. No synchronize_irq
or reset runs in this route's IRQ context. No implicit reinitialization after
failure: restricted one-frame owner lifetime remains explicit.

Lock ordering: parent lifecycle serialization -> core/page mutex -> direct
queue mutex. Source-off acquires only core/page mutex, before controller
queue stop. IRQ drain is outside both core/page and queue locks. Parent holds
media/module/device refs and prevents forced subdev/provider unbind across
the operation; device refs alone do not protect devres teardown. The media
pipeline blocks non-dynamic link changes, not arbitrary sensor format changes.
Frozen IMX882 set_fmt currently rejects changes only once camera->streaming.
Main must serialize/reject ACTIVE format changes for the prepared pipeline
before enabling this path: the descriptor recheck and legacy s_stream(1)
take the sensor mutex separately. Do not hold its state_lock across legacy
s_stream (it internally locks the same mutex). This is a real activation gate,
not a successful-ready assumption or solved by the core/page mutex alone.

## Source closure and CI targets

New isolated targets: `mt6878-seninf-route.o`, `route-smoke.o`. Place the six
files beside main's existing camera-owner isolated sources, not in a second
destination for one source key. No production archive linkage.

Uses existing staged `mt6878-seninf-{contract,mux,phy,phy-data}.h`,
`mt6878-camsv-{direct,hardware,platform,vb2,capture}.h` and their existing
transitive recipe/CQ/CCD UAPI headers. Actual symbol dependency is
`mt6878_seninf_calibration_read` in `mt6878-camsv-hardware.o`; that object and
`smi-backend.o` must be compiled against the native provider API before link.
Provider source additionally stages `mt6878-smi-camera-reset.inc` inside
`drivers/memory` and `smi-camera-reset.h` into `include/soc/mediatek`, applies
owned provider.patch after existing 0070, and targets `drivers/memory/mtk-smi.o`.
Require reachable MTK_SMI, OF, PM, COMMON_CLK, NVMEM, MEDIA_CONTROLLER,
VIDEO_V4L2_SUBDEV_API and the already-tested frozen DMA-contig dependencies.

Native CI target: `route-test.c` with include path to frozen camera-seninf.
Fixture covers both modes/full ports, RAW/PDAF CH/DT remap, packet checker
geometry, exact ACK, invalid/duplicate allocation, shared-drop/dynamic
selected-page preflight rejection without writes, distinct physical/virtual
SAT source mapping and outer/inner bank finalization, every setup write failure with retained
first error, every disconnect write failure without replay, and successful
disconnect without claiming DMA/PHY retirement. Fixture is an in-memory fake,
never a production provider. It is prepared, not locally executed.

## Remaining real activation owners

The current frozen graph has resource-only probe and a rejecting stream op.
Main must embed this route state and bind ops before registration, under its
native controller lifetime. It must implement the actual allocated mux/group
reservations and core/page exclusion; this code does not invent an allocator.
The frozen PHY backend's mandatory MAC A/B + PHY interrupt pending/ack/drain
consumer and TSREC route setup/disable are still required; this route does not
pretend CAMSV's four IRQs cover them. They cannot be replaced with booleans.
`mt6878_phy_off` now retains `configured` if receiver shutdown fails. Its
fault fixture checks retained state and refusal to replay every failed off
operation. This route still retains the first error independently and never
turns a local flag into proof of complete DMA/IRQ/TSREC retirement.

Next gate: combined CI native fault fixture + ARM64 route/smoke, hardware,
SMI consumer and actual upstream SMI provider objects. Runtime remains disabled
until complete PM/reset/IRQ/TSREC/mux owners and failed-stop removal lifetime
are reviewed; then a bounded first-frame RAW/PDAF capture and verified stop
on a cold boot, preserving display/touch/sensors/USB. No capture success is
claimed by this source-only change.
