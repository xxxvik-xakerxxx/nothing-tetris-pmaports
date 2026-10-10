# Persistent reusable capture-cycle candidate

Review only. No published source edits, DT activation, hardware success or local
C/KUnit build/run. Stage overlays and compile both new objects plus changed
platform/native/video objects KUNIT=n/y. No reprobe or full supplier teardown
between frames. PM refs remain held until streamoff/close; this bounded snapshot
cycle is not continuous preview or idle-power optimization.

## Executable producer

epoch-video.patch applies AFTER published video-cold.patch. Worker claims a
separately allocated epoch, submits actual RAW/PDAF vb2 buffers and performs
epoch retirement/rearm. First epoch uses reviewed cold_frame. Later epochs
reuse native controller_prepare/direct_submit/platform_arm and enable_streams
with unchanged mode/config, actual IOVAs and incremented sequence. No unknown
register setup or invented IRQ ACK is introduced.

Per-frame retire waits bounded completion from the actual IRQ DONE/error-driven
stop worker, then flushes work. It MUST NOT request stop before this wait: doing
so truncates the submitted frame. Only timeout first latches persistent native,
direct and epoch failure (preserving an earlier causal IRQ error), then schedules
abort stop and exits without per-frame retirement/rearm. All refs/storage stay
held until native full cleanup. Late DONE cannot authorize a healthy successor.
Actual worker disabled capture IRQs, receiver disable drained SENINF and
stopped sensor/routes, direct_stop verified STOPPED and DMA/SCQ reset. Successful
stop clears tx.submitted: receipt requires !submitted, quiesced, off_attempted,
observed DONE, exact full tag mask and both returned buffers. Earlier draft
incorrectly required submitted after stop; corrected here.

A fresh retirement_reset calls existing joint reset against actual prepared,
disconnected STOPPED owner. Source-backed CAM_MAIN pulse is not a guessed ACK.
Six disabled registered IRQs are synchronized outside core/queue locks. Existing
seninf_route_retire performs actual PHY OFF and independently verifies IRQ/TSREC/
quiescence. Only after success are own mux/core/CAMMUX reservations released and
coherent CQ freed. DMA/route/TSREC/event receipts are saved in old epoch; errors
or missing proof retain owners/storage and block rearm.

next() requires that receipt, disabled IRQ actions, unchanged IOMMU domain, live
media/PM/binding, no allocation/PHY/bus/persistent errors and completed old stop.
It allocates NEW coherent CQ and fresh per-frame transaction objects, retaining
original MMIO/clocks/device refs/IRQ registrations/mutexes/vb2 queues. Only then
per-frame completion/stop request is initialized and successor installed. Old
attempts/errors are archived, not reset for retry. Persistent native/controller/
direct first_error fields are never cleared.

Worker detaches old pending pointers and clears used admission under unchanged
queue mutex only after next succeeds. QBUF returns EAGAIN during stop/rearm, not
permanent ESHUTDOWN; retry after bounded cycle finishes. One RAW + one PDAF buffer,
fixed initial mode/config/layout, no sequence wrap. Not an arbitrary multibuffer
streaming engine.

## Full streamoff lifetime

Parent lifetime exclusion is mandatory for WHOLE call. Root blocks queues and
cancel_work_sync drains frame_work before native full retire. Only streamoff/
close releases supplier/module/device refs, IRQ registration and media ownership.
epoch-final-retire.patch lets existing resource-only receiver release recognize
actual historical PHY-off/disconnected/quiesced receipt, not treat all old
attempts as live. Failed OFF remains EBUSY. Worker never frees supplier storage.
epoch_free refuses active owners. Detached successful history may be freed once
callers drain; current epoch is freed only after full native teardown. Failed
cleanup retains existing video quarantine policy.

## Stop reset-lock overlay

native_smi_clamp asserts reset_lock ownership. epoch-stop-lock.patch takes it
AFTER direct.lock in task-context stop work, after receiver/IRQ drain, and releases
it before direct.lock. Queue -> reset avoids introducing reset -> queue opposite
to joint's queue -> sensor -> reset hierarchy. No state/core lock is acquired
under reset lock. Parent must review supplier exclusion/lifecycle serialization.
Direct_stop remains existing locked bounded reset API. No IRQ self-drain,
IRQ-thread poll, ignored EALREADY or fabricated OFF flags are added.

## Sources and gates

Pinned modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835
mtkcam/camsys/isp7sp/cam/mtk_cam-sv.c supplies existing DONE/reset flow;
reset_msgfifo is SOFTWARE kfifo initialization, not hardware ACK. Device
ee2be53cb75670b548948636a0db1d1ff112bf12 suppliers unchanged. Native
camera-direct/platform, camera-seninf-controller/route and reviewed joint/cold
are actual cleanup/setup producers; this draft reuses their recipes.

Five KUnit fixtures: sticky first error, retained unretired storage, unbound owner,
stale old-sequence DONE through actual camsv_done, missing/failed DMA OFF through
production epoch_done. Prepared, NOT executed; no successful mock supplier.
check.py verifies ordering/no supplier teardown/no scalar error clearing and
overlays; generate-overlays.py --check verifies deterministic worker/final-retire
overlays. Next gates: parent lock/lifetime review, ARM objects, KUnit execution,
then separately authorized repeated capture and regression tests.
test-completion-order.py runs five source-only mutation fixtures preventing
premature stop, abort before error publication, timeout fallthrough and late-DONE
success after timeout. These inspect actual production call order; no C execution.
