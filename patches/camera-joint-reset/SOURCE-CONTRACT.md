# Native cold frame + joint reset candidate (review only)

No shipped linkage/DT/frozen edits or hardware success. Four isolated ARM
objects KUNIT=y/n are pending: joint reset, cold cleanup, cold probe, smoke.
STAGING.json adds sources to the existing camera-owner directory. Apply
video-cold.patch ONLY there for review: it embeds persistent joint state,
uses the real resource-only cold probe, and routes the existing preflighted
vb2 worker through cold_frame. Old raw CAM_MAIN fields remain ABI-compatible
but are not required/used by this path. No duplicate ioremap or dummy base.

## Sources and OFF proof

Modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835:
mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c sv_reset_by_camsys_top and
mtk_cam-sv-regs.h supply SMI clamp, SCQ 0/1, bit1 ready poll 1us/100000us,
SCQ 0, CAM_MAIN 0x58 0/(3 << id*2)/0, barrier, unclamp.
mtk_csi_phy_3_1/mtk_cam-seninf-hw_phy_3_1.c set_cammux_src,
disable_cammux, switch_to_cammux_inner_page and the matching PCSR/GCSR
headers supply OFF-only current/next idle 0x7f, enable clear, four tag pages,
owned VSYNC bit clear, 0x103 status ACK and mux disable on both banks. These
are frozen route_disconnect operations, WITHOUT forging its route.attempted/
configured/PHY state to invoke an ON-gated API. mt_cam-seninf-tsrec.c
tsrec_n_settings_clear supplies frozen TSREC disable recipe/readbacks.
Existing event helpers supply known MAC/CPHY/mux IRQ mask/sample/ACK;
pending G1 fails EOPNOTSUPP because no ACK is proven.

Device ee2be53cb75670b548948636a0db1d1ff112bf12 supplies MT6878 DT ranges
SAT 0..2, muxvr 0..23, CAMMUX 0..15 and DVFS metadata. Read and validate
actual properties/voltage/clock before cleanup; no numeric fallback.
Shipping IMX882 0112 has NO core.s_power callback. The isolated
camera-seninf-controller/imx882-native-streams.patch MUST apply after 0112
and before the cold video overlay/entry. It registers core.s_power as
imx882_power: s_power(0), under the sensor lock, rejects an active native
stream with EBUSY and otherwise unconditionally calls imx882_stop. Stop
unconditionally calls imx882_power_off, which logically asserts active-low
reset BEFORE checking clock/supply references, even with zero owned refs.
It does not claim to discharge unowned inherited regulator references.
Without this overlay the cold call fails ENOIOCTLCMD; it is not OFF proof.
A zero software streaming mask alone is likewise not sensor OFF proof.

Cold cleanup requires a fresh bound exclusive media owner, no previous DMA
or controller PHY/route attempt, and six disabled requested IRQs. It drains
them outside core/queue/subdev-state locks, calls actual sensor power-off,
then reserves native controller bitmaps under core lock. It rejects foreign
enabled/dynamic CAMMUX state on BOTH pages before OFF programming and
restores page selection after preflight. It masks/samples/ACKs owned events,
disables TSREC and disconnects owned endpoints. Current/next/enable and mux
OFF values are read back; no guessed ready poll. Frozen allocated/
source_stopped/route.disconnected/irq_drained fields are NOT flipped.
Separate observations follow actual operations and are rechecked against
bitmap ownership and register readbacks.

## Executable path and locks

Cold probe uses real direct/platform/receiver bind and unwind APIs. No raw
CAM_MAIN mapping input or register/power activation at probe. Cold frame
takes a real CAM_MAIN PM/mapping lease BEFORE native lock, then obtains
ordinary SMI/platform/receiver PM refs. Native lock stays held through OFF
cleanup, reset, extra mapping-lease retirement, controller_prepare, coherent
CQ/vb2 submit, native arm and V4L2 stream-on. No retire/removal gap. Existing
video preflight checks RAW/PDAF/CQ layout and IOVAs before entry.

Native lock -> lifecycle -> receiver active state -> sensor active state ->
core -> queue (preflight only). Sensor power-off precedes active-state
locking because its callback locks the sensor mutex. IRQ drain precedes
state/core/queue locks. Queue unlock precedes SCQ polling and SMI callbacks.
Extra supplier lease retire runs after other locks unwind, BEFORE native
unlock. Static supplier ownership still must protect asynchronous DMA.

Only after reset AND mapping-lease cleanup succeed are completed flags
published. Cleanup failure latches transaction/native first errors, clears
completed/reset_completed, sets reset_attempted, and therefore preserves
the native PM/DMA retirement quarantine. Earlier reset error wins; cleanup
error remains separately recorded. No-attempt preflight/reentry rejection
with successful cleanup does not poison a successful owner.

Cold MMIO/sensor-cleanup/reset failure retains cold reservations and native
PM/storage. No OFF/reset retry. SMI owns its actual error/clamp lease. The
temporary CAM_MAIN lease retires synchronously after its last access, never
left locked over workqueue return. After successful OFF/reset/lease cleanup,
cold bitmap reservations retire; frozen controller_prepare performs the
ordinary calibrated PHY/route ON sequence with real nvmem inputs.

## Gates

This is a ONE-SHOT FIRST-FRAME experiment per bound owner lifetime.
transaction.attempted rejects a second capture; repeated streaming/capture
and suspend/resume are not implemented or claimed. Do not reset the sticky
transaction to retry on the same owner after failure.

Source checker compares pinned operations and reconstructs the packaged
sensor plus actual native-streams overlay with fuzz=0, checks registered
s_power(0) -> stop -> unconditional reset assertion even with no owned refs,
checks cleanup/lock ordering, and dry-runs video overlay on a fresh copy of
frozen source. --kernel-tree additionally checks the ACTUAL staged sensor:
parent must invoke this after all isolated overlays and before object build;
default source reconstruction alone does not prove parent staging applied it.
Kernel object CI without the vendor modules checkout must use the explicit
bounded mode after stage_camera_overlays and before ARM make:

```
python3 patches/camera-joint-reset/check.py --staged-only --kernel-tree STAGED_KERNEL_TREE
```

This requires the actual sensor file and validates the same callback chain,
then exits without Git reads or overlay replay. Missing file/overlay is a
failure, never a fallback to reconstructed source. Full source validation
still requires --modules-repo. test-sensor-off.py runs eleven source tests,
including staging-mode argument/dependency isolation and missing staged file.
The eight original fault fixtures cover missing overlay,
missing ops/callback, conditional stopped/zero-reference cleanup and wrong
reset polarity. These are not KUnit or hardware reset observations.
Five KUnit cases: sticky/reentry, unbound, completed+PM-error
quarantine, first-error preservation, invalid cold mode before provider
access. No fixture fabricates successful PM/IRQ/DMA providers. No local C
or KUnit execution. Parent must review shared page/TSREC exclusivity, PM
lock order and all four ARM objects, then run fixtures before activation.
Real genpd/clock/rail/nvmem suppliers must bind. Existing forced supplier
removal prohibition and failed-stop lifetime remain required. No capture
success, image activation or elimination of runtime gates is claimed.
