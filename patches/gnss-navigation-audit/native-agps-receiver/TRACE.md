# Native AGPS Reverse Receiver

Status: Partial, seven hash-pinned static checks passed; shell syntax, Python
syntax and whitespace checks passed. This implements a bounded reverse
receiver and native delivery contract, not a complete assistance service.
MISSING_AGPS_RECEIVER remains set. Native C11 sanitizer fixtures and Bionic
compile checks are provided for parent CI; neither was run by this sidecar.
No emulation, native compilation, CI dispatch, phone access or push occurred.
All additions are within this directory. No private binary/payload is included.

## Exact Inputs

Outer workspace `/Users/vlysko/Documents/Nothing CMF Phone 1`, private inputs
under `worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/`:

| Input | SHA256 |
| --- | --- |
| mnld | `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83` |
| libmnl.so | `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90` |

Observed repository HEAD `5379657152363cc47e35f0df0ccf1a1d670bd3fe`.
The earlier d7b6f9e satellite/start producers and completed quiet-policy
inputs are consumed as existing work; neither is repeated or altered.
All addresses below are ELF virtual addresses. Capstone5.0.6 performs static
decoding, with both whole-file hashes validated first. No CPU executes the ELF.

## Two Directions

The forward TX producer `mnld39490/39540 -> 380a0` sends type150/152 to
`/data/agps_supl/mnl_to_agps` or abstract `mtk_mnl2agps`. Existing endpoint,
agps_host, slot6_service and the single frame_worker implement this TX route.
That socket needs the actual assistance-service consumer. Binding a listener
that merely accepts those messages cannot supply assistance or close its gate.

The reverse RX producer is a distinct endpoint. `create_agps2mnl_fd3b350`
tries the filesystem literal `16afc=/data/agps_supl/agps_to_mnl`, then the
abstract fallback at3b52c. The literal atc9e5 is `mtk_agps2mnl`.
3b550 writes abstract NUL,3b56c copies the first8 name bytes to sockaddr+3,
3b570/574 materialize the remaining `2mnl`,3b57c stores them at+11;
3b5e4 supplies length15 to bind3b5e8/PLT85370. No terminal NUL is in the name.
The new native profile explicitly supports this abstract reverse route only.
It never tries/unlinks the Android filesystem route or claims fallback occurred.

`mnld55d70..55d78` calls `agps2mnl_hdlr3a4a0` from its event reader with the
retained handler table. The first decoded word is version1; the second chooses
type200..303 through the104-halfword table at22bc0. That table, actual callback
relocations, and the deeper library calls are checked by `test_static.py`.

## Implemented Consumer Set

| RX Type | Table Branch / Callback Slot | Actual Handler | Native Parameter |
| --- | --- | --- | --- |
| 250 PMTK | 3aca8 / +58 | 59290 -> 64a00 | 35 |
| 256 LPPE common iono | 3b028 / +a0 | 599f0 | 62 |
| 257 LPPE common trop | 3a614 / +a8 | 59b80 | 63 |
| 258 LPPE common alt | 3a954 / +b0 | 59d10 | 64 |
| 259 LPPE common solar | 3a988 / +b8 | 59ea0 | 65 |
| 260 LPPE common CCP | 3a9bc / +c0 | 5a030 | 66 |
| 261 LPPE generic CCP | 3a9f0 / +c8 | 5a1c0 | 67 |
| 262 LPPE generic DM | 3b064 / +d0 | 5a350 | 68 |
| 264 ASN.1 assistance | 3aa24 / +100 | 51390 | 118 |

Table base88508 follows from actual RELATIVE relocations:88560 ->59290,
885a0..885d0 -> the seven LPPE handlers,88608 ->51390. Type263 and303 are
separate handlers, not inferred adjacent payload routes. Every unsupported
type, including GPS session/control/settings/version paths, fails EOPNOTSUPP.

Type250 wire layout is u32LE1,u32LE250,u8presence, optionally
u32LE(strlen+1),string,NUL. 3acb8 calls351c0, which consumes presence then
extent; absent yields NULL. This implementation refuses absent with ENODATA,
accepts present empty, requires the exact terminator and no embedded NUL.
64a24..34 calls mtk_agps_set_param(35,pointer,6,4); PLT859f0 relocation86e28
proves the export. lib6b18c4..6b192c selects message3 and length strlen+1;
its upper bound is256 including NUL. Larger strings are refused before entry.

Types256..261 carry u32LE1,u32LEtype,u32LElength,payload. The raw pointer is
the position after the extent word (3b058), not an optional-string parser.
262 uses352c0's u32 extent/copy with8192 maximum;264 uses the same copy routine
with65536 capacity. This implementation requires positive exact extents,
maximum complete datagram65536, and maximum264 payload65524. No clamped extent,
padding from a zero-filled receive buffer, fabricated NULL or guessed length.

Each LPPE handler calls mtk_agps_set_param_with_payload_len(parameter,p,6,4,n)
at handler+b4..c8; ASN.1 does so at51414..28. PLT85760/relocation86ce0 names
the export. Its lib entry6b14c4 handles parameters62..68 or118.

## Native Queue And Pointer Lifetime

Native association reuses the existing loader-view validation and the exact
immutable ELF. Trusted staging must authenticate the complete Bionic closure;
association itself is not authentication. No caller dispatch callback, guessed
function address from another DSO, Android flag or property is installed.

The receiver dispatches through this SAME associated image at6b17b0 or6b14c4.
The mnld producer's actual6/4 arguments are retained. lib6b1944/48 and
6b15d8/dc put those values into the first two message halfwords. PMTK message
subtype is3; payload path uses61 or17 (118). These are native agent-message
headers, not a new host IPC envelope or an invented channel number.

Both entries allocate owned message storage and copy payload synchronously:
6b1968 and6b15fc call the real memcpy veneer6e48e0 before native ring enqueue
651500 at6b19b0 or6b1660. The host receive-buffer view may be reused only after
the call returns. Native ring enqueue stores the allocated pointer at65153c;
on failure the entry frees it, while success transfers it to its native owner.
The internal queue therefore never retains the host's borrowed RX pointer.
This does not substitute for the existing native worker/agent consumers.

Native enqueue signalling contains a delay/retry path (6515d0 and following).
Calling these exports is not hard-bounded. The dedicated engine child's parent
must retain its process deadline and waitpid/reap quarantine. Receiver shutdown
cannot cancel a thread inside this native call.

## Controller Stages And Gates

| Stage | Actual Transition | Dispatch Allowed | INIT Gate Effect |
| --- | --- | --- | --- |
| open, pre-INIT | exact bind, SO_PASSCRED, four owned fds | no | none |
| prepare, pre-INIT | real mapped-image association, detached parked worker | no | partial return1, none |
| activate, post-INIT | sample source native records, write owned activation eventfd | yes, admitted types only | none |
| quiesce, pre-stop | stop wake, completion acknowledgement by deadline | ends | none |
| close | bound-unused or acknowledged receiver only | no | none |

`prepare` does not require INIT or primary RX to be live. Its worker polls only
stop/activation fds and cannot read the socket; queued messages stay queued.
`activate` must be called by the sole controller after an actual successful
run return18. It accepts no run-status/ready boolean; native admission samples
the associated source-owned primary record at6edef0 and the relocated nonoffload
pointer6e6d00 ->6fa3d8. Index0, stop529f18, wake529418, live marker and retained
handle are checked. Dispatch repeats that observation. It is a sampled native
lifetime precondition, not proof that an assistance peer exists or a fix works.
No reset/retry makes an activation failure succeed.

The PREPARED/RUNNING states describe this host worker's own lifecycle only.
They are never supplied as readiness to the vendor engine. Activation eventfd
is a controller scheduling command, not a replacement for a source INIT gate.
Parking is new host synchronization to exclude premature native calls; it is
not claimed to reproduce an OEM service-readiness or worker-state global.

There is no way to make the existing argument builder's AGPS gate zero using
this partial implementation. The old executor consequently cannot INIT today.
This is an explicit remaining integration boundary, not a circular claim that
post-INIT activation fulfills its own pre-INIT prerequisite. Full pre-INIT
closure requires the legitimate forward service and all enabled consumer
semantics to be implemented, owned and admitted before native run. An eventual
complete producer may compose this reverse owner; this sidecar does not publish
that producer or a service-ready receipt.

No assistance daemon binary/source/owner PID is established by these two ELF
inputs. `open` requires the supervisor to supply an actual owned peer PID/UID;
there is no default/current/self/root PID, service spawning or fake listener.
Every received datagram must carry matching kernel SCM_CREDENTIALS. Credentials
authorize the peer identity only, not service semantics or runtime readiness.
Supervisor must retain and reap that child, avoid PID reuse/replacement while
the receiver lives, and keep the namespace trusted. Socket bind/send acceptance
does not authenticate or attest the other side of the forward channel.

Selecting ordinary satellites while disabling assisted mask options does not
prove that mandatory slot6 or frame3/4/5 service requests disappear. The current
mask consumers only establish constellation-pair configuration. No explicit
unassisted service-exemption profile is justified by this trace, so none is
added and neither existing AGPS nor other configuration gates are lifted.

## Parent Integration

Add b41_agps_decode.c,b41_agps_receiver.c,b41_agps_native.c and the header to the
native source closure. Production links existing b41_library_association.c;
the native-record header contributes types only, not another engine controller.

Before INIT, after the real supervisor service identity and loader association
are available, keep fresh process-lifetime receiver storage and call open then
prepare. Treat return1 as partial ownership, not complete service readiness.
The existing slot6 TX and frame_worker queue remain the only callback queue
consumer. This new worker reads only the independent reverse AGPS socket;
it never reads gpsdl, duplicates output, or replaces native RX.

The parent's eventual controller hook belongs immediately after verified real
run_status18, before its observation loop: activate the already-prepared owner.
Observe receiver first_error/completion alongside existing host/control errors.
On activation failure or receiver error, retain all resources and stop the
session through the existing supervised lifecycle. On every stop path quiesce
the reverse receiver BEFORE native_stop_capture/call destroys agent queues.
Only after completion acknowledgement can native stop proceed. On receiver
timeout/unknown completion, exit/quarantine the engine child rather than enter
native stop concurrently with a still-dispatching receiver. Parent waitpid/reap
remains the final resource boundary. Exposed frame_worker semantics stay intact.

Those hooks are not applied to the shared files in this sidecar. Current
b41_native_arguments_config_missing unconditionally retains AGPS_RECEIVER;
b41_native_session_execute rejects nonzero missing_contracts. Neither is patched.

## Ownership And Failure

Only the setup/controller opens/closes this receiver's four private fds.
The single detached RX worker owns receive-buffer/native-call access. It checks
socket identity before recvmsg, refuses data/control truncation, closes all
received SCM_RIGHTS fds once and then rejects the message. Excess rights are
closed by Linux on control truncation. No datagram drop returns fake success.
First decoding/peer/native error stops dispatch and remains sticky.

Stop requests use an owned eventfd, absolute CLOCK_MONOTONIC deadline, and a
separate completion eventfd. Completion is published after the worker's final
owner/DSO access. Successful quiescence with an earlier failure still records
QUIESCED while returning that failure; timeout records QUARANTINED and retains
every fd/image/storage. close refuses RUNNING/PREPARED/QUARANTINED owners, checks
all identities before closing any, and never retries close(EINTR). Native and
host records cannot be freed or reused before their required process lifetime.
Exclusive fd ownership is required: inode checks cannot establish absence of
external dup/close/reuse, especially for eventfd's shared anonymous inode.

Remaining blocked consumers are executable refusals: forward150/152 service
effects; frame sleep/network/measurement responses; source GPS open/reset/close,
NI, location, settings/version and additional payload types; structured slot6
controls3/5/7 and LPP/RTCM services12..15. GPS session controls never call a
guessed native stop. The supported nine receive types do not implement those
producers or assistance algorithms. INIT/fix/clean-install/lifecycle remain
unvalidated.

## Verification

From the repository root, static-only validation:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 \
python3 patches/gnss-navigation-audit/native-agps-receiver/test_static.py \
  '/Users/vlysko/Documents/Nothing CMF Phone 1/worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/mnld' \
  '/Users/vlysko/Documents/Nothing CMF Phone 1/worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/libmnl.so'
sh -n patches/gnss-navigation-audit/native-agps-receiver/run_ci.sh
```

private_evidence.py with the same two paths prints a small JSON evidence report,
never writes/disassembles raw bytes into the repository or executes either ELF.

For parent-owned CI only:

```sh
CI=true sh patches/gnss-navigation-audit/native-agps-receiver/run_ci.sh
CI=true BIONIC_CC=/path/to/aarch64-linux-android28-clang \
  sh patches/gnss-navigation-audit/native-agps-receiver/run_ci.sh \
  --bionic-compile /path/to/test-receiver
```

The Linux fixture uses actual Unix datagrams/eventfds/pthreads and a synthetic
native sink through linker wrappers. It tests nine supported routes, every
unsupported type0..399, truncation/extent/null/max-length rejection, copied
payload, parked pre-INIT dispatch exclusion, failed activation, bounded stop,
blocked native dispatch quarantine, credentials, unexpected fd cleanup, bind
collision and replaced socket refusal. No fixture can claim real native INIT,
library dispatch success, assistance peer or hardware behavior. The Bionic
route compiles the native branch and fixture without executing it.

Native candidate hashes at handoff (SHA256; no compilation result implied):

| File | SHA256 |
| --- | --- |
| b41_agps_receiver.h | `38b79767a840c745901f357664ca0ba37315b1261535f4cb1e2398db509b1677` |
| b41_agps_receiver.c | `46c5ee65532cf924d3fb7826d2220cb28513d703edfa79c6959839b1dd42ab3f` |
| b41_agps_decode.c | `bbe4c6477f5b9b2c24cb055d9d700587789955ff3a407ad321aa131bfa9d3979` |
| b41_agps_native.c | `a3e43242c7badd0cfab3e0dffa27c0cc6c60d1239fbaef7a769f26cf2a5d73f1` |
| test_receiver.c | `ce189fccf59f7947c020cbceaba1d10ef878d8376569260bfd8c44e2d206a474` |
| run_ci.sh | `1835a40d2b59715d43baaad2a763d87b1c8afc564b68a3e173c8654ce56a0039` |
