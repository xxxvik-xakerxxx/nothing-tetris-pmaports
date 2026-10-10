# Native video registration draft

Not activated, compiled or exercised on hardware. No DT, package, frozen source
or workflow edits. The new owner registers actual media/V4L2 devices and RAW/meta
vb2 queues; it is not an automatic platform driver with fabricated suppliers.

## Executable closure

Call `mt6878_native_video_register()` only from the already-bound static platform
resource owner, outside probe and outside its device lock. It retains the four
devices and their driver modules. Registration holds this module until a
successful `mt6878_native_video_unregister()`. The root async notifier matches
the actual receiver fwnode. Its complete callback runs only after the receiver's
sensor notifier completes, resolves the real media sensor link and verifies the
active RAW10 sensor dimensions. No name-based subdevice search/private cast.
`mt6878_native_video_wait_ready()` waits for the real complete/failure callback,
returning its causal registration error or a bounded timeout. Timeout retains
the notifier and lease. The platform caller serializes public wait/unregister
calls while owning the handle; this is not a freeable asynchronous request.
Registration errors are separate from later frame/retirement errors.
An error return from register may carry a non-NULL result when partially
published devices cannot retire/drain. That handle still owns its complete
supplier lease; callers must retry unregister, never discard it on errno alone.

Native capture bind acquires the sensor/receiver pipeline. While still strictly
resource-only, this owner stops that pipeline, registers both sink entities and
immutable enabled receiver-to-video links, then starts the expanded pipeline.
The physical sensor mode must be selected BEFORE registration. Formats are
fixed for this one-shot lifetime. G_FMT/TRY_FMT/S_FMT return the selected DMA
layout; S_FMT rejects allocated buffers/retirement and never changes ACTIVE
sensor state. Its registration -> queue lock order follows native ioctl dispatch.
Both video sinks have actual link_validate callbacks. Reacquiring the expanded
pipeline checks the receiver ACTIVE format against the selected layout, rather
than relying on the format snapshot taken before the pipeline was extended.

The two queues each allocate one MMAP buffer on the existing bound camisp-larb
IOMMU supplier. They retain direct.lock as required by the frozen buffer mapper.
Neither DMABUF import/export nor USERPTR/read/create-buffers is exposed. Both
STREAMONs plus both buffers schedule a process-context worker calling the real
native capture frame API. This worker does not hold the queue mutex. Completion
remains the frozen real IRQ -> stop worker -> checked reset -> vb2 DONE/ERROR
path. One-second absent completion requests actual stop; no synthetic DONE.
Before invoking native capture, the worker resolves both real ACTIVE vb2
allocation cookies/IOVAs, checks the existing IOMMU domain, CQ overlap and the
frozen recipe's entire config/layout contract. Unsupported packing/scenarios,
wrong capacities or stale mappings fail before any power/reset/PHY operation.
Such preflight failure returns ERROR buffers without a hardware cleanup claim:
no frame call or DMA attempt occurred; the resource-only bind still retires.

STREAMOFF, REQBUFS(0) after use and close cannot reclaim in-flight DMA through
an unguarded vb2 cancellation. STREAMOFF drops the INFO_FL_QUEUE lock before
retire, then reacquires it for vb2. Close retires outside that lock. A failed
retire retains the independent fh, queue owner, buffers, capture work/context,
module and supplier references. Unregister refuses outstanding opens or this
quarantine. The opens count is NOT a final-video lifetime gate: V4L2 core takes
video_get BEFORE open callback and performs video_put AFTER close callback.
Both embedded video devices now have a genuine final-release callback signaling
their own sticky completion. Unregister detaches published nodes under the
registration mutex, unlocks it, and waits for both actual releases with one
bounded deadline. Only then may queue/entity, notifier, media, module/supplier
and owner storage teardown run. A timeout retains the entire root and can be
retried; successful prior retirement is not repeated. Never-published nodes
have no callback to await. A failed video registration before device_register
has no device references and is explicitly completed; a device_register failure
uses its real release callback. This follows the exact pinned v4l2-dev.c paths.
The root deliberately has no v4l2_device.release callback: pinned core caches
NULL in that case before calling vdev.release and never touches v4l2_dev after
our final video callback. Successful reset is NOT inferred from first-error errno.
There is no retry/rearm; a new registration requires full safe retirement.

## Registration policy and remaining integration

The caller must not free its borrowed mappings/devres after unregister fails.
This error-returning registration API deliberately cannot be put into a void
remove callback or a devm cleanup action. Static supplier nodes, suppressed
manual unbind, module pins and explicit unregister ordering are required.
Kernel-initiated platform-device deletion still needs the real platform owner's
cooperation: device/module references do not pin devres against forced unbind.
The async unbind callback is defensive stop handling, NOT a guarantee against
a supplier that ignores that policy. Runtime activation remains prohibited.

True remaining supplier/API corrections, for main review rather than frozen edits:

* IMX882 and all root/DMA/CAM_MAIN/SMI driver owners must suppress bind attrs for
  this restricted experiment. Graph's native PM overlay already does so. This
  draft refuses missing policy instead of silently making forced removal safe.
  `sensor-unbind-policy.patch` is the proposed IMX882-only correction, unapplied
  to frozen sources; apply after 0112 and native-streams review overlay. This
  hides manual unbind only, not kernel-initiated forced removal.
* A legitimate CAM_MAIN native provider must call this API with its owned
  mapping and retain its lease until unregister succeeds. No provider currently
  exports that mapping/retirement lease. This draft does not invent an address,
  remap the clock provider or claim that get_device pins the mapping.
* The existing camisp-larb DMA supplier must actually be bound with the exact
  CQI/WDMA IOMMU ports/domain. `dma == pdev` is rejected; no self-link workaround
  or manual domain attachment. CAM_MAIN/SMI/root/receiver runtime PM must be real.
* Partial capture bind is discharged by the new owner's narrowly gated
  retire_partial: no PM/reset/PHY/route/DMA attempts and no controller IRQ
  ownership are permitted. It uses actual platform retirement/work drain and
  direct coherent-CQ release APIs. Failed cleanup retains the registration;
  nothing converts a first-error return into an unproven stop success. Native
  capture remains the only retirement entry for a bound/attempted stream.
* Supplier-selected PDAF BAYER8 emitted DMA is exposed as GENERIC_8, NOT as
  packed RAW10 or as a quarter of RAW bytes. Pixel content/truncation still needs
  a first-frame comparison; no libcamera tuning/ISP/preview claim is made.

## Provenance

Vendor modules pin `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`:
`mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c`,
frame_desc_prev (4542+) and frame_desc_vid (4585+): RAW VC0 DT2b 4000x3000 or
4096x2304; PDAF VC0 DT30 4000x750 or 4096x576, RAW10 receiver remap. Those are
wire/receiver geometry, not proof of emitted BAYER8 payload size. Explicit DMA
layouts/config come from the caller and are checked by the frozen CQ recipe.

Device pin `ee2be53cb75670b548948636a0db1d1ff112bf12` and matching B4.1 libccd
provenance remain in frozen CAMSV recipe/resources/PHY contracts. No new HW
registers, voltage, clocks, polls or calibration values are introduced here.

Linux base `d84b264a54a37611f2f46bc19363cb9b41606205`:
`drivers/media/common/videobuf2/videobuf2-core.c` queue cancellation forcibly
returns ACTIVE buffers when stop_streaming fails its contract. Consequently
hardware retirement is BEFORE entry to vb2 cancellation, not in its void
callback. `videobuf2-v4l2.c` _vb2_fop_release releases queue memory and fh;
quarantine must not call it. `v4l2-ioctl.c` v4l2_ioctl_get_lock chooses queue.lock
for INFO_FL_QUEUE calls. Generic metadata formats describe emitted byte layout,
not interpretation/calibration of PDAF samples.

## CI plan / next runtime gate

Stage this directory's C/header/inc alongside main's frozen native capture,
controller, platform/direct, route/PHY/mux, SMI and recipe closure, with both
native graph overlays applied in order. Add objects mt6878-native-video.o and
video-smoke.o. CONFIG_MEDIA_CONTROLLER, VIDEO_DEV, V4L2_ASYNC,
VIDEOBUF2_V4L2, VIDEOBUF2_DMA_CONTIG and DMA/IOMMU dependencies must be enabled.
Build the owner with CONFIG_KUNIT=n and =y; the latter includes real private
callback fault tests in video-lifetime-test.inc, requiring a runnable KUnit CI
kernel to execute them. No local C builds or test execution claimed.
Current local checks cover source ordering/guards and style only. Added KUnit
cases exercise bounded notifier timeout/causal error isolation and rejection
of QUEUED/wrong-allocator buffers without fake DMA allocations or providers.
Partial cleanup fixtures reject receiver IRQ, reset and DMA attempt states
before any cleanup API is called; no mock supplier is asserted ready.
Three additional lifetime fixtures register actual V4L2 devices, use real Linux
get_device/put_device references and drain the final-release callbacks. They
cover an open blocked on registration with opens==0, native close returning
before core's final put (both nodes independently), and one-node partial
publication. Pending-open uses a kthread and actual native open locking;
last-close executes native video_release with a real V4L2 fh/empty native queue.
It also verifies that unregister with an outstanding open returns EBUSY and
leaves BOTH actual devices registered before exercising the final-close tail.
No camera provider, power, hardware-ready state, DMA buffer or register is mocked.
These fixtures require execution in KUnit CI; source checks are not race proof.
The supplied CI run 38029177349 reports the frozen 33-object closure successful;
it does not establish execution or runtime success for this revised draft.

First runtime gate, only after provider/abort-policy closure and object/test CI:
register two nodes without rails/MMIO; verify media graph and exact G_FMT
strides/capacities; queue one RAW and one metadata MMAP buffer; STREAMON both;
require actual DONE timestamps and valid RAW/PDAF bytes, then bounded STREAMOFF
and successful unregister with no IRQ/work/mapping left. Inject failed source
start and failed stop and verify no vb2 reclaim until actual quiescence. Maintain
display/touch/sensors/USB regressions and recovery under main's live gates.
