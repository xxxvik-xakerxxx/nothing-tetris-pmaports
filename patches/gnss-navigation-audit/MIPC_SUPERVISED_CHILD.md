# Sealed resources and sole-parent MIPC lifecycle

New code connects the retained resource lease to immutable copies and the
existing `b41_native_child_wait` parent controller. It does not launch INIT.
The frozen four resource-audit files are unchanged.

`SealedStage(resources)` requires actual versioned closure, copies each provider
into a Linux memfd, applies WRITE/GROW/SHRINK/SEAL seals, then hashes the sealed
copy against the previously independently pinned provider hash. Source stats
are not authentication. External changes to the original cannot change an
accepted copy. Missing liblog remains ENODATA; an NDK import stub is not an
implementation. No fake property provider is introduced.

`move()` transfers descriptors to the parent, which must close them on a failed
C prepare; successful `b41_mipc_supervision_prepare` consumes them. Prepare must
precede child creation. An absolute CLOCK_MONOTONIC deadline is copied once:
it includes loader work, unbounded OEM init0x305 retry and subsequent141 exchange.
There is no separate per-phase reset. Cleanup deadline bounds escalation/reap.
An exit observed after the deadline is conservatively rejected even if exit0:
it is not evidence of timely completion.
The existing isolate's load-only seccomp/device policy is NOT broadened here.
It is unsuitable for real CCCI until parent reviews the exact transport policy.

Parent must exclusively own creation and reaping of this child. Bind uses
waitid(WNOWAIT), not a child-written claim. Only actual waitpid acknowledgement
from the existing controller closes sealed resources. Nonzero exit preserves
failure; timeout sends SIGKILL and reports ETIMEDOUT after reap. Failed bind or
unreaped timeout retains resources in quarantine. There is no unload/reinit.
The supervisor uses the stateful `b41_native_child_wait_owned` API: stop/continue
notifications cannot set wait_status or release FDs. Persistent escalation and
first_error survive cleanup exhaustion: return EINPROGRESS with wait_error
ETIMEDOUT, then return the original ETIMEDOUT when a later call actually reaps.
The original single-call waiter remains a compatibility wrapper, not a retry API.
Pre-child rollback sets terminal but never reaped. Process exit is containment,
not proof of a graceful detached MIPC RX join or successful calibration.

## Review and CI integration

Run `sh run_mipc_supervised_child_ci.sh` in Ubuntu CI with CI=true. It links
the tracked `b41_native_receiver_host.c`; section GC keeps its existing child
wait implementation without duplicate mocks. Sanitizers are unchanged. Add
Bionic API28 object compilation of `b41_mipc_supervised_child.c` using the
existing NDK include paths. No local C compilation was performed.
Fixtures additionally use real Linux PTRACE_TRACEME stops and TRACEEXIT to hold
a killed child before terminal reap, verify retained FDs, then permit late exit
and check that timeout provenance survives. Ptrace denial must fail CI visibly.

Run Linux Python sealing fixtures with `PYTHONDONTWRITEBYTECODE=1 python3
test_b41_mipc_sealed_stage.py`. macOS skip is explicit, not a sealing pass.
Production sealing additionally depends on frozen init_resources/version_closure
and pyelftools. Fixture sealing itself uses only the standard library.

## Remaining executable handoff blockers

Actual platform liblog implementation and independent hash; legitimate runtime
property service; modem readiness report and reviewed CCCI bindings/handshake;
complete configuration/calibration remain mandatory. Sealed memfds alone do
not construct an Android filesystem or authorize linker execution. The parent
must consume these exact sealed descriptors (not reopen mutable source paths)
in its reviewed isolation/loader handoff. Until that path is complete, no real
INIT is exposed or called by this bundle. No hardware success is claimed.
