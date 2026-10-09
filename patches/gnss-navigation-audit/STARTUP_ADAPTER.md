# B4.1 native startup adapter

Status: executable host boundary, not a running navigation engine. No vendor
registration or `mtk_gps_mnl_run` is called. No package or device is changed.

## Implemented

`b41_startup_adapter.c/.h` adds typed 0x70/0x444 configuration storage with a
separate resolved-byte map. Zero-filled bytes are explicitly not resolved
policy. The adapter constructs the independently traced B4.1 identity/magic,
the `UseCallback` output marker, and bounded caller-selected absolute paths at
the recovered string offsets. It rejects truncation without altering storage.
It does not invent first-block fields, scalar defaults, fd ownership or assets.

The offset0xc8 producer is now fully emulated from pinned mnld
`628e0..62a0c`, including both property calls. `user` produces0;
`eng` with debuggable1 produces1; `userdebug` with debuggable1 produces2.
Other combinations return-1 in mnld and are refused by the adapter without
writing a fake value. This field is build/log policy, not navigation mode.

Typed slots1/2/3/4/5/6 preserve borrowed output bytes (including embedded NUL),
encode exact PMTK738/736 frame requests and capture selector0 AGPS data.
They enqueue bounded typed events
for a host worker, without allocating, blocking, retaining borrowed pointers,
accessing devices or reentering libmnl. A frame event contains the internal
dispatcher payload, **not a complete AGPS datagram envelope or gpsdl packet**.
The host worker must route it to a real, audited AGPS receiver; dequeue alone
is not a frame measurement. Output is not automatically a valid NMEA fix.

The queue holds16 events of at most1024 bytes (host policy, not vendor limits).
Full/contention/invalid-length errors are recorded once and returned to the
callback. Later queue callbacks return that first error. Pure codec/pass-through
callbacks retain their separate return contracts. The opaque library may
ignore a callback return: a worker must also inspect the sticky error and use
an audited stop path. Binding is one-shot and lifetime is process-wide; there
is no unsafe unbind/reset of a retained callback target.

## Tests And Integration

The existing pinned ELF SHA256 checks still apply. `test_b41_startup.py` now
executes the complete build-policy helper with nine property vectors in
addition to the earlier262 frame vectors and bounded startup-copy tests.
These Python/Unicorn tests pass; they do not establish native Bionic behavior.

`test_b41_startup_adapter.c` exercises config extents, supported paths,
immutable rejection, marker/identity, unresolved gates, one-shot binding,
borrowed-buffer lifetime, ring wraparound, full/contention/sticky-error cases
and exact frame encoding. **Native tests have not been run locally.** Main CI
must invoke `sh patches/gnss-navigation-audit/run_startup_adapter_ci.sh` on
Linux to build/run the six isolated scenarios with ASan/UBSan. Before runtime
integration, also cross-compile the adapter with the same AArch64 Bionic
toolchain/runtime used by `mnl-load-probe`; do not substitute musl shims.
No global CI file or APKBUILD is modified here.

## Exact Next Runtime Gate

Mandatory0..9 machine shapes are now recovered; see `MANDATORY_CALLBACK_ABI.md`.
Before a native engine call, implement the active notification and AGPS host
services, recover the complete first block and remaining second-block
scalar/policy producers, the AGPS
receiver envelope/result path, a single owner of receiver fds/initialization,
and bounded stop/close behavior. `b41_startup_missing_contracts()` exposes the
remaining audit mask0x7b: mandatory shapes no longer block, actual host services
still do. Callers cannot clear gates by asserting flags.
Keep the library unregistered until those are implemented and the exact
Bionic closure is validated. The current load-only isolation denies threads,
ioctl and networking, so it must not be reused as an engine runtime blindly.
After those gates, the first supervised test must establish timestamped,
checksum-valid navigation output plus clean stop, not merely library loading.
