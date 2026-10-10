# Native producer arguments integration

Candidate, not a hardware or native-build success. Existing frozen sources are
unchanged. `b41_native_arguments_prepare` replaces generic ownership assumptions
with an actual setup transaction in a dedicated supervised Bionic ARM64 child.

The owner retains loader association, kernel device identity, adapter, control,
output, worker, stop owner and the constructed arguments together. Preparation
does not register or start libMNL. Execution uses these same objects through the
existing real session controller, not a separately supplied callback table.

## Concrete ownership closure

- Derive association from the existing legitimate loader view and exact staged
  ELF. Caller still must authenticate the immutable whole file before loading.
- Require unused relocated native thread records and real nonoffload global.
  The supported stop procedure is available; a successful stop is NOT asserted
  until the real runtime joins pass the frozen acknowledgement checker.
- Validate gpsdl descriptors against actual kernel sysfs identity. Match second
  config bytes AND receiver-specific provenance before moving them to the worker.
  Inactive secondary has source-retained zero, NOT fd0 or a guessed -1 field.
- Actually initialize and bind the existing adapter and native control, move and
  bind distinct output streams, start the existing worker, then expose it.
- Only after these producers succeed remove HOST_SERVICES, TRANSPORT_OWNER and
  STOP_CONTRACT from the retained arguments. Native HOST_SERVICES means the
  reviewed native report/control/output policy, not Android FM/RTC publication
  emulation. FIRST_CONFIG, SECOND_POLICY and AGPS remain independently gated;
  unknown requirement bits survive. Byte provenance is scanned even if a caller
  has zeroed first unresolved counters. A pure configuration-mask projection is
  NOT an argument builder or ownership authorization.

Kernel evidence: modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835,
connectivity/gps/data_link/linux/gps_each_device.c (exclusive open, dynamic
device identity, module owner) and the existing pinned navigation integration
trace. The host worker is NOT a receiver reader. Actual libMNL RX525528 reads
the transferred primary; no external RX worker is started here.

Stop evidence and supervision reuse the frozen native host: 17 source table
records, actual52e2c0 stop, nonoffload-only join acknowledgement and parent
waitpid acknowledgement. Timeout/failed join/forced-exit handle changes reject
graceful stop. Parent must run b41_native_child_wait; after preparation enters,
all returns require child exit, with no reset/retry/free/unload. Partial setup
may already have bound globals/moved fds, even when no engine call occurred.

## Remaining constructor and slot6 requirements

SECOND_POLICY and AGPS_RECEIVER remain forcibly missing. Moving an IPC socket
does not implement its receiving service or structured slot6 payload lifetime.
Existing selector0 only proves a nonzero parameter test, not a byte length;
neither this builder nor its tests invent one. Existing frame3/4/5 datagrams
still require a legitimate receiver and response semantics. NMEA-only output
does not establish an XML feature policy disabling these services. FIRST_CONFIG
retains every unresolved byte, XML policy and legitimate calibration/source
requirement. No frozen constructor is promoted or edited.

## CI integration

Ubuntu (no vendor engine calls):

```sh
CI=true sh "$AUDIT/run_native_arguments_ci.sh"
```

Bionic API28 compile/link and run the fixture with the existing sanitizer policy:

```text
b41_native_arguments.c
b41_native_receiver_host.c
b41_engine_arguments.c
b41_library_association.c
b41_gpsdl_identity.c
b41_startup_adapter.c
b41_agps_host.c
b41_frame_worker.c
b41_navigation_output.c
test_b41_native_arguments.c
```

Use pthread, C11, Wall/Wextra/Werror. No new libcrypto/libxml symbols. All
transitive headers must be present; particularly the previously frozen untracked
b41_library_association.h SHA256:
252f98e40bacbf9a0c4af10176f597fcdbc2b26cc96281991ef7653cace20fac.
Include that exact accepted header in the main snapshot; no git operation is
performed by this candidate.

Fixtures test provenance-mask reconstruction, XML/calibration refusal, unknown
bit preservation, platform refusal, no setup side effects on preflight failure,
and first-error propagation. Successful hardware takeover is intentionally NOT
simulated. Native compilation and fixtures remain CI-only and pending.
