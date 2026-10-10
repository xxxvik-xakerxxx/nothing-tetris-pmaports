# Native receiver control and real RX stop candidate

New scoped files only. Integrated worker/output/identity, ADC draft, adapter,
constructors, APKBUILD and shared CI are untouched. No local C compilation,
phone operation, native engine execution or hardware-success claim.

## Consumer boundary: Linux NMEA is not Android mnld

Pinned mnld285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83;
libMNL3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90.

Event0 is not a mandatory call to get/publish a GPS position to Android before
the solver can emit NMEA. Its first getter85890 is mtk_gps_get_rtc_info, writing
two doubles for the FM coexistence branch. `/proc/fm` and relative `dev/fm`,
ioctl0xc008f520 and mnld88c0c thresholds belong to that FM consumer, not gpsd.
The native host does not own/provide an FM consumer; it must not fabricate RTC
values, copy Android FM ioctl to an unrelated Linux node or alter GPIO policy.

After5e370, mnldde518/de9e8 conditionally enables RAW_MEAS through set_param51.
After5e42c, real56c70/56c50 gates measurement/clock/AGC publication. Later
56c80/56c50 gates navigation events. Calls858a0..858e0 are named GNSS getters
for those Android paths. They are not the callback2 NMEA output path at524a88.
Existing raw output goes to the real output owner; gpsd must validate fixes.
Native event0 records an actual report notification and wakes the controller,
never creates a location/RTC answer or claims fix validity. It does not enable
RAW_MEAS51 or Android measurement/navigation publication. No stock XML switch
for FM/ADC/AGPS disable was established; absence of such a key is not proof of
an engine default. This host policy is a different consumer, not claimed OEM
feature-disable emulation.

Event3's source reads ADC fd88790, with a real -1 no-action branch. Its source
producer is not resolved completely. Accordingly this backend NEVER responds
with fake diagnostic success: an unexpected event3 records EOPNOTSUPP and wakes
the controller to stop. Frozen ADC draft remains independent/unbound.
No per-device NV/calibration bytes are initialized, substituted or overwritten.
Existing source-derived state paths/legitimate calibration still belong to their
owners; this control backend does not manufacture the initializer inputs.

Event7 means fix prohibited: a real control notice, not sending a packet to a
nonexistent Android listener. Event13 means restart requested: a real control
notice, not restart completion. Both must make the controller stop the session.
Only a fresh supervised process may later start a replacement; no reset/retry
loop or inline stop/join from the engine's callback thread. Other selectors
have actual no-action entries in the pinned5de00 table. The eventfd owner binds
once and remains until process exit; only an unbound setup owner can close it.

## Actual native RX acknowledgement

Source52c524 calls52c9b0 before destroying events/queues. The17 records at6edef0
have32-byte stride: first signed marker, index, pthread handle, stop function,
wake function. Exact function pointers are529f18 and529418.

Stop529f18 index0 sets6fa3dc, signals the recorded thread with10, and invokes
529e04's pthread_join path. Both direct join and timer-assisted join branches
write the first marker=-1 ONLY after join returned0 (52a2c0..52a2c8).
Join failure returns-1 with the original live marker (52a29c..52a2cc).
The pthread handle at+8 is not cleared, so checking handle==-1 AFTER stop is
wrong. Initial marker==-1 with a live/stale handle cannot establish this session.

Important counterexample: nonzero6fa3d8 (GOT6e6d00) lets offload records14/16
write marker=-1 WITHOUT JOINING. The verifier refuses that actual mode, rather
than guessing an offload flag or treating a marker/timeout as universal proof.
It requires initially live primary RX, unchanged loaded base/index/functions/
handles, and success markers for EVERY initially live record. Any changed/late
thread, failed join, stale record or unexpected mode prevents acknowledgement.

b41_native_stop_capture reads the associated legitimate mapped image after
actual init/thread start on the sole controller. b41_native_stop_call calls the
REAL Bionic ARM64 export52e2c0 once; it never uses uninit52f86c/RET as teardown,
never interprets the residual return register as join success, and never closes
GPS/IPC fds, unbinds callbacks or unloads the library. No thread-table/global
write is performed by this host code. ACK refers to these native table threads,
not every timer/auxiliary thread in the process; process exit remains the final
ownership boundary. Capture cannot authorize native init, and its source checks
are NOT new caller-selected readiness flags.

Native stop may block in join. Run the engine/controller in a dedicated child;
b41_native_child_wait is the PARENT's bounded waitpid supervisor. After the
absolute deadline it sends SIGKILL once to its exclusively owned unreaped child,
then bounds actual reap by a second absolute deadline. Reaped forced exit is
ETIMEDOUT, never graceful native ACK; an unreaped child is EINPROGRESS and must
stay quarantined with no replacement engine. Parent never signals a nonchild.
No cancellation of vendor threads or forced release of retained pointers.

## Integration sequence and current closure

1. Fresh dedicated Bionic engine process, source-derived constructors and
   legitimate calibration, exact existing loader association; no missing gate
   cleared merely because these functions exist.
2. Bind existing adapter/output worker, then replace callbacks.notify through
   b41_native_control_bind BEFORE table construction/registration. Do not add
   a second raw-output queue/worker. Poll the control eventfd alongside existing
   host-worker completion/error notification.
3. After genuine initialization, observe report/control/worker events until
   stop admission, then capture actual live native thread ownership. Capturing
   immediately after return18 could mistake a still-starting thread for absent.
   REPORT is liveness only; PROHIBITED/RESTART/UNSUPPORTED or any host error
   requests controller stop. The callback thread never invokes stop/getters.
4. Controller invokes native_stop_call, retaining all fds/callbacks. Verify
   source ACK, then quiesce the existing host worker and terminate the child.
   Frozen worker exposure/quarantine semantics are NOT overridden; do not clear
   exposed flags or call release_unused on exposed resources.
5. Parent requires real waitpid exit/reap. Forced/unreaped outcomes remain
   failures, with no false restart/cleanup success.

The actual b41_native_session_execute controller is included: source callback
registration52f9d0, mnl_run52e2bc, required result18, existing worker/control
monitoring, actual stop and host quiescence. It requires a fresh native table,
UseCallback output, matching actual primary receiver fd and nonoffload first+68
policy. Both actual registration and initialization are refused while existing
arguments.missing_contracts is nonzero; partial builders are not reclassified.
It does not guess partial-init cleanup: after entered/failed initialization the
child MUST exit, and the parent bounds actual reap/quarantine. A failing callback
or worker terminates observation. Restart is surfaced as ECONNRESET, not reset
success. Exposed worker quiescence/quarantine remains visible as EBUSY; caller
must terminate the child, not drop the flag to get a zero cleanup status.

This is real register/run/control/stop/reap CODE, but NOT yet a permitted
runnable initializer with current constructors. Remaining startup closure includes legitimate
live constructor-source snapshots and slot6/assistance receiver/response
contracts. Existing callback6 parameter is not proven universal payload length;
neither this backend nor NMEA-only consumer policy resolves that contract.
No initializer/registration/engine-run was EXECUTED or readiness bit cleared.
Main must not label the port GNSS Works from source/native fixture results.

## CI commands and evidence

Bounded pinned stop producer oracle (pyelftools+Unicorn, intercepted external
calls, no engine/thread/signal/phone execution):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT/test_b41_native_join_producer.py" "$ASSETS/vendor/lib64/mt6878/libmnl.so"
CI=true sh "$AUDIT/run_native_receiver_host_ci.sh"
```

Oracle passed primary join success/failure and offload14/16 counterexamples
locally. Native fixture is CI-only: actual eventfd delivery/first-error latching,
finite unbound cleanup, table failure matrix, actual child exit/forced reap.
Ubuntu native compile closure: b41_native_receiver_host.c + its C fixture,
pthread and existing GNSS type headers. The previously frozen
b41_library_association.h is STILL UNTRACKED in this checkout; main must include
that accepted header in the CI snapshot, not assume git already contains it.
No other new/untracked implementation dependency. Real engine branch is
restricted to Bionic ARM64.
Bionic API28 links those2 C files PLUS integrated b41_startup_adapter.c,
b41_agps_host.c, b41_frame_worker.c and b41_navigation_output.c with existing
sanitizer policy. No extra XML/crypto source function calls were added. Test
fixtures never call a synthetic native stop function or claim fake engine init.
