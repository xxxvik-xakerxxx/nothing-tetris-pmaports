# One-Attempt Secure L1 Download Owner

`download.c/h` now connects the complete bootstrap constructor and ACK codec
to the exact secure MVCD/CW fragment sequence. `download_linux.c/h` performs
the actual fd-based metadata ioctl, bootstrap write, nonblocking reads and
integer fragment ioctls. It is not installed, activated or exposed by a CLI.
No physical DSP download, kernel WORKING state or navigation fix is claimed.

## Ownership And Protocol

Use one zero-initialized controller for one real exclusively held gps0 open.
The caller must acquire the legitimate profile/clock/configuration inputs,
retain the exact session and descriptor, and prevent duplicate readers/writers,
close/reopen, reset and concurrent callbacks. A struct address or descriptor
number is not a hardware ownership certificate. Missing acquisition is still
an integration blocker; no ADIE, platform frequency or synthetic calibration
is substituted here.

The Linux entry checks O_RDWR/O_NONBLOCK and validates field construction before
querying. One successful ioctl23/24 supplies the complete pinned five-u32 ABI.
Its key-bearing metadata is erased after assembly. Only the controller's private
116-byte buffer is submitted; it is erased when accepted or on first fault.
There is no metadata logger, frame recorder or persistent secret output.

After validated ACK31 sequence0, the next operation is **only** ioctl25/26
with integer index0. The matching ACK32 sequence1 admits index1, and so on.
The last index is N-1, ACK sequenceN; then sequence becomes N+1 and the controller
reports `ACKS_COMPLETE`. No per-fragment command08/0c packet or terminal execute
packet is invented. The opaque bootstrap auxiliary word is not a count/status.
[DOWNLOAD_SEQUENCE.md](DOWNLOAD_SEQUENCE.md) proves this exact producer path.

The controller accepts one complete checksum/trailer/command/sequence-matched
ACK per pending request. Arbitrarily split chunks are accumulated within the
1024-byte proven frame bound. Extra coalesced/stale/duplicate bytes fail the
attempt rather than being saved for an operation that has not been issued.
This conservative download-only policy is not a general navigation demux.
The Linux adapter reads whole entries into2048 bytes, not six-byte DMA reads:
the driver does not support splitting one queued entry by request size.

## Failure And Time

Every call uses one absolute CLOCK_MONOTONIC deadline for the whole attempt.
Backward time, expiration, malformed/unsolicited ACKs, zero writes/EOF, changed
session fd/selectors, unsuccessful metadata and fragment operations stop it.
First error and causal stage are retained; private TX/RX buffers are erased.
Subsequent calls cannot restart the attempt or replace that first error.
No sequence advances merely because write/ioctl returned success.

`EAGAIN` means no data/queue capacity yet, not a new firmware attempt. Accepted
TX bytes are never replayed. Interrupted or unsuccessful fragment ioctls are
terminal, not retried. The owner event loop must schedule steps within its
deadline; this module does not spin or silently retry a failed download.

The adapter requires packaged1008 nonblocking RX **and** the staged1009 TX
extension under `patches/gnss/write-boundary`. Stock write ignores O_NONBLOCK;
there is no stock `.poll` readiness API. The staged TX change queues once or
returnsEAGAIN before capacity/polling-completion waits while preserving existing
blocking behavior. It must pass actual-source and real module/package CI before
hardware integration. Current r182/r183 images do not contain1009.

Deadlines are checked before/after syscalls, not a claim of preemptible hardware
operations. Synchronous SMC has no timeout argument; user copy, existing locks,
event dispatch and kernel reset/close can still stall. The owner must retain
normal cleanup/recovery responsibility; no kill/unbind/module reload or
automatic device reboot is introduced here. ACK completion remains distinct
from the independently observed MCUB RAM_CODE_READY -> kernel FSM WORKING event.

## Verification And Next Integration

CI-only `run-ci.sh` now builds strict ASan/UBSan fixtures for the controller and
the actual Linux adapter with linker-wrapped syscalls (never real hardware).
Tests cover every count1..257 in both routes, exact integer/ACK numbering,
no extra fragment writes, partial TX, all maximum-frame split boundaries,
opaque auxiliary data, stale/early/invalid ACKs, deadlines/session changes,
first-error retention and private-buffer erasure. Linux fixtures cover real
syscall argument ABI and preserve an earlier syscall errno across a subsequent
clock failure. The new pinned static sequence check passes13 tests locally;
the TX source/application suite passes14 with one local GNU-patch check skipped.
GNU patch and both actual-source IRQ/polling native fixtures are mandatory in
the GNSS CI workflow. No C was compiled or executed locally.

Remaining integration: legitimate retained inputs and the sole live fd owner,
real1009 v051 compilation/packaging, protocol ACK traffic, independent kernel
ready evidence, clean teardown and lifecycle, then navigation INIT/fix and
GeoClue. The arithmetic/assembler/controller no longer need proprietary DSO
execution; that does not make the required input acquisition optional.
