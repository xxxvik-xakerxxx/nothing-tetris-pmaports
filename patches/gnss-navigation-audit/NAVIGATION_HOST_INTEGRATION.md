# Navigation Host Integration

The existing worker directly routes application and navigation output alongside
AGPS frame requests. Native sanitizer tests and AArch64 Bionic compilation are
part of the shared CI; no vendor engine is executed by either fixture. This
source integration is not yet packaged or validated on a receiver.

## Executable output path, one worker

Pinned B4.1 libmnl SHA3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90:
output524a30..524ab8 uses second+1cc UseCallback for slot2, then calls mandatory
slot1/app separately. Callback returns do NOT suppress subsequent calls. Our
existing adapter already copies both borrowed pointer/length pairs correctly.

b41_navigation_output connects those copies to actual nonblocking native stream
consumers. Slot2 writes the exact raw/NMEA-format byte stream to an owned FIFO or
PTY feeding gpsd/native parser. Slot1 publishes to a DIFFERENT app stream; it is
not duplicated into gpsd, dropped, or treated as an engine position object. It
preserves embedded NUL, proprietary output, sentence fragmentation and invalid
fixes; the consumer's existing parser establishes checksum/position validity.
No new hand-written NMEA/solver implementation or generated positions.

Both sinks must be exclusively owned, writable NONBLOCK FIFO/PTY fds; takeover
validates real fstat/type/flags and refuses aliases, regular files and raw GPS
device fds. Character sinks must pass read-only TIOCGPTN, identifying an actual
PTY master rather than any UART/tty/GPS device. Kernel PTY numbers distinguish
different masters even when ptmx fstat inodes match and are rechecked before
delivery. No proprietary GPS power/firmware ioctl is issued. No
open/dup/endpoint guessing/flag mutation occurs. Bind before the sole host worker,
retaining the owner until process exit. Fd identities and NONBLOCK are checked
before each write; disappearance/replacement/backpressure/short write latches the
first failure and stops the existing worker. Already-delivered byte count is
retained; no retry/replay, duplicate sentence or successful-drop semantics.
SIGPIPE is contained per private host-worker thread, not process-wide SIG_IGN.
Its original mask and preexisting pending SIGPIPE are preserved normally; if a
new EPIPE signal cannot be drained, the failed worker retains its blocked mask
until exit rather than restoring into a fatal signal. Vendor threads' signal
dispositions are never changed.

`b41_frame_worker.c` uses one navigation dispatcher,
not its queue, thread,25ms scheduling or lifecycle. Frames3/4/5 still call the
existing b41_agps_owner_send_event. One worker drains ONE existing queue, so no
competing output worker consumes and loses frame work. Existing unsupported
selector0 AGPS_DATA remains refused: the producer only tests parameter nonzero,
not a byte-count contract. This is real output and frame delivery, NOT full host
service completeness or gpsd/GeoClue support before integration/runtime validation.

Runtime sequence (not executed here): create legitimate app and raw
output streams; b41_navigation_output_take; bind output; reuse existing adapter
init/bind and callback table/argument builders; start the existing worker
with the existing AGPS owner. No callback reentry or additional queue.
No missing-contract flag is cleared.

## Actual Linux transport ownership

Exact kernel module pin e96f60dc081ae3525ef43d4bcf0ee5ee97e53835, read with git show:

- connectivity/gps/data_link/gps_dl_context.c declares gpsdl0/index0 and
  gpsdl1/index1. v051 uses these shared sources, not MCUDL's NMEA device.
- linux/gps_data_link_devices.c allocates the major dynamically via
  alloc_chrdev_region; class_create/dev_name and device_create use gpsdlN in
  linux/gps_each_device.c. Hence /sys/class/gpsdlN/gpsdlN/dev is the authoritative
  kernel dev_t, not a fixed handset major or caller-selected pin/proof flag.
- gps_each_device_open invokes gps_each_link_open and marks the session open
  only on success. Reopen returns EBUSY. gps_each_link_open rejects OPENED/OPENING
  and atomically transitions CLOSED ->OPENING before power/event handling.
  Opening starts a hardware session; existence of a node is NOT readiness.
- .owner=THIS_MODULE retains the driver while the open exists. Release clears
  is_open and runs normal gps_each_link_close, which can wait for hardware close.
  No duplicate open or unload is an acceptable handoff/cleanup technique.

New b41_gpsdl_identity_snapshot validates actual O_RDWR character fds against
SYSFS_MAGIC-backed kernel dev_t for the exact source-declared classes. It opens
ONLY sysfs metadata, never GPS devices, and supplies the real descriptor/device
inventory. Primary is gpsdl0; optional secondary is gpsdl1, not a duplicate of
primary. Absence does not invent the56ce0 secondary policy. No owner/stop flag
is asserted or cleared. Identity cannot detect all external dup/fork aliases:
the supervisor must retain exclusive descriptor lifecycle and forbidden aliases.
The native fixture tests real invalid fd/types/read modes and atomic failure;
it does NOT emulate a successful GPS sysfs or claim a hardware pass.

Pinned libmnl init52b9e0..52b9f4 copies second+10/+14 into primary6ee124 and
secondary6edeec. It does NOT open the primary/secondary device paths again on
that branch. A primary -1 with first+68 zero fails setup. Supply the already-open
legitimate owner snapshot through our existing second constructor, not a new
open in the library or a duplicated native firmware initialization.
Internal RX525528..525538 reads primary6ee124 through508d14 ->__read_chk,
capacity512;525718..52571c feeds mtk_gps_data_input. No external b41_rx_owner
reader may run concurrently once the engine owns this RX. The existing raw
capture worker is pre-engine only; second's fd fields are NOT the AGPS IPC fd.

## Internal RX shutdown: resolved steps, remaining hazard

Read directly from the same exact libmnl, not names guessed from nearby symbols:

- Primary RX5253b8..5253e4 installs signal10 with flags4/SA_SIGINFO, NOT SA_RESTART;
  relocated GOT6e77e8 points to5214e0 (RET). Primary reads already handle errno4
  as EINTR;525488 rechecks stop6fa3dc and exits to timer cleanup/pthread_exit.
- Stop tail52c524 calls52c9b0 BEFORE destroying queues/events. The17-entry thread
  table6edef0 has32-byte records, handle+8, stop function+10=529f18.
- Primary index0 branch529f74 sets6fa3dc=1 BEFORE pthread_kill(handle,10) at
 52a1c4..52a1cc; thus the owner is the real retained internal pthread, not an
 external reader. The follow-up529e04 arms the owned timer for parameter1 second
 (1000ms conversion), then pthread_join. Some alternate branch uses direct join.
- Successful stop invalidates the per-entry first word; timeout/error is NOT an
 ownership acknowledgement. The timer-based helper is NOT equivalent to
 pthread_timedjoin_np or a proven hard deadline across all17 retained threads.
- 52c650..52c654 writes primary6ee124=-1 but does NOT close that primary GPS fd;
  serial/output fd branches close other descriptors. The sole supervisor still
  owns actual GPS close after verified internal-thread cessation. Do not close
  while RX could still be blocked, or mistake integer invalidation for fd release.

This materially resolves the shutdown mechanism/owner, but does not authorize
calling native stop/init on an unowned receiver. Native timer/fallback signal
behavior, join acknowledgement for every active thread, callbacks and complete
engine stop still require supervised source-backed validation. No register/init/
run/stop API is called by this draft and no unconditional-success wrapper exists.

## Exact CI and remaining init blockers

```sh
sh "$AUDIT/run_navigation_output_ci.sh"
```

CI=true/Linux required. Runner compiles the tracked production worker with
ASAN/UBSAN and runs both the new real callback->worker->pipe/frame
service tests and existing frame-worker regression tests unchanged. New tests
cover NUL/copied lifetime, distinct slot1/2 delivery, retained fds, EPIPE without
process death, preexisting SIGPIPE, backpressure, actual partial byte delivery,
fd replacement refusal and unresolved AGPS-data rejection. Kernel identity has
negative-only native tests, no fabricated success. No local native builds.

Shared Bionic ARM64 CI compiles the worker + adapter/agps_host + output
source + test_b41_navigation_output.c using NDK API28,
pthread and -Wl,--wrap=write; standalone gpsdl identity uses its two C files.
No libcrypto/libxml dependency is added by these two services.

Actual init/run blockers now remain slot0 position/control/ADC/NV/restart
effects, complete structured AGPS services and responses, remaining second/XML
policy plus legitimate live producer snapshots, and native retained-thread stop
acknowledgement. A real output service removes neither these mandatory services
nor the firmware-ready gate. Display/sensors/SCP/USB/shared DT/services are not
touched. The next runtime step must complete these services before invoking
the engine; another association-only test is not a navigation implementation.
