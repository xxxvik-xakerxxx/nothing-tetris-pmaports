# Direct platform consumer draft

No probe/DT activation or phone operation. This is a concrete
IRQ registration/power-reference/stop-task consumer, NOT a completed hardware
backend. Frozen direct and shared files remain unchanged.

## Pinned evidence

Modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835:
`mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c`:
- lines 1497-1551 DONE, 1578-1687 SOF, 1691-1753 ERR, 1755-1807 CQ:
  FIRST_TAG, outer/inner FH_SPARE then corresponding status reads. ERR uses
  inner bank; SOF/channel outer; CQ SCQ. No handler writes ACK. We do not claim
  this establishes read-clear semantics or invent W1C writes.
- lines 2070-2103: four exclusive IRQs ordered DONE/ERR/SOF/CQ, initially
  disabled. This draft uses threaded-only IRQF_ONESHOT/NO_AUTOEN to serialize
  direct mutex access, not vendor hard-IRQ FIFO dispatch. Latency/level line
  behavior requires actual hardware validation before enabling.
- runtime_resume lines 2361-2397: clocks in DT order then CAMSYS_TOP reset
  then IRQ enable. This draft obtains clocks in that order; it cannot arm
  before the real backend proves reset/resource/route/IRQ ownership.
- sv_reset_by_camsys_top lines 366 onward: common SMI clamp, SCQ reset poll,
  CAM_MAIN reset register. Still requires the actual shared CAM_MAIN/SMI owner.
- central_common_disable lines 825 onward: TG_MODE_OFF/VFDATA_EN/CMOS_EN and
  tag clearing. Not substituted with receiver s_stream alone.

Register offsets copied from the same commit's `mtk_cam-sv-regs.h`:
ERR_STATUS 0x0350, SOF_STATUS 0x0360, CHANNEL_STATUS 0x0370,
CQTOP_INT_0_STATUS 0x001c. Existing frozen generated header supplies DONE
handler offsets. No guessed status masks or ACK writes.
SOF additionally reads inner LAST_TAG 0x01c8 before FH_SPARE, then four inner
GROUP_TAG registers (0x01b8, stride4) and outer VF_ST_TAG4 (0x0550+3*0x40),
exactly as lines 1590-1626. Observed groups must match the recipe job or first
ESTALE schedules stop; no update silently changes the submitted CQ contract.

Device ee2be53cb75670b548948636a0db1d1ff112bf12:
`arch/arm64/boot/dts/mediatek/mt6878.dts` lines 9600-9689 describes SV-A/B
six named banks, four IRQs and clocks; CAMISP IOMMU ports around line 4033.
No raw DT addresses copied. Existing resource acquisition remains authoritative.

## Actual operations and remaining boundary

Bind validates the enabled native sensor->receiver media link, pins module and
device identity, acquires an exclusive native media_pipeline under graph lock,
and requests all four disabled IRQs with unwind. Existing pipeline ownership
is rejected instead of silently sharing another controller's route. Parent's
async notifier must prevent subdevice/devres unbind until retire succeeds;
device/module references alone do not provide that guarantee.

Power_get holds actual CAM_MAIN and CAMSV runtime PM and eight acquired clocks.
CAMSV's own DT CAM_MAIN genpd is not inferred from its parent's power state.
The two PM references collapse to one if they refer to the same device. It does
not install fake PM/reset callbacks or enable a regulator without its driver.
Native CAM_MAIN provider, SMI clamp31, CAMISP/IOMMU supplier, calibrated CPHY
and CAMMUX route must implement the existing direct backend gates. This code
does not replace those gates with state booleans.

IRQ threads read pinned status order; ERR caches first EIO, CQ/SOF preserve
snapshots without claiming a complete frame. DONE uses frozen direct latching.
Full DONE/errors schedule task work. Work disables/drains IRQs outside queue
lock, calls actual sensor and receiver s_stream(0), then direct_stop under
lock. Receiver lacking s_stream is a real blocker, not successful route-off.
Direct STOPPED must independently prove CAMMUX/TG/VF off and reset completion.
Failed stop retains buffers/CQ, clocks, PM, IRQ registrations and controller.
Stop scheduling is one-shot; a lifecycle mutex excludes IRQ-enable progression
from the worker's disable/drain loop. IRQ callbacks never acquire that mutex.
No reset retries or implicit controller restart follow a failed stop.

Retire waits with a caller deadline; timeout does not cancel/free live work.
Linux disable_irq and subdevice callbacks themselves have no bounded-wait API:
a bounded parent/receiver implementation remains a required activation gate.
Success drains work before freeing registrations. Single controller-task
serialization is mandatory for bind/power/arm/retire; no simultaneous arm and
stop, and no retire from IRQ/queue lock. Native video nodes are not registered.

Compile plan: add only platform C/header/smoke to existing direct closure;
target mt6878-camsv-platform.o and platform-smoke.o in isolated CI. Needs
MEDIA_CONTROLLER, VIDEO_V4L2_SUBDEV_API, PM, common IRQ/workqueue infrastructure
and existing direct/vb2 dependencies. No CCD/RPMSG/daemon dependencies.

Both platform ARM64 objects passed combined CI 37991879173 with the existing
direct closure (20 total objects). Compilation does not execute the IRQ/stop
path. Next implement native CAM_MAIN/SMI and SENINF/CAMMUX TG/VF owners before
runtime activation. No captured-frame claim or local C builds.
