# B4.1 GNSS post-init navigation audit

Status: **Partial, offline only**. One post-init configuration packet and the
receive-to-output control path are bounded-test verified. A sufficient navigation
start sequence, measurement decoder, position ABI, and position fix are NOT proven.
No device access, transport writes, firmware execution, or package changes occurred.

## Provenance and boundaries

- libmnl input: `worktrees/gnss-userspace-bridge/local/ota-b41/vendor-lib64/libmnl.so`.
  SHA-256 `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`.
  Tests reject any other hash. Addresses below are ELF virtual addresses, not
  process addresses or a stable API.
- Matching `mnld` SHA-256:
  `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`.
  Its disassembly was inspected, not executed.
- GNSS worktree HEAD observed: `f4db1b5cac9cd95d3981d68b96f6d2e863cfe01f`.
  Its `research/gnss-b41-inputs/CALLBACK_ABI.md` SHA-256 at inspection:
  `17cfd7771bcd2ac030a26a01b2597c3bc4a6c3fe938162ae049bbbd2cbf221d3`.
  Existing ARM64 tests informed the harness; they were not modified.
- Own worktree HEAD: `5944ffd1300e6ce1ebc2be54a377be29b3bec2a9`.
  Initial status was `?? patches/`; existing camera files were left intact.
- The user's supervised native r153 PASS is contextual evidence only, not a
  test repeated here. Prior-session RAMWORK is not current-session readiness.
- This is matching binary/disassembly evidence, not recovered original C source.
  Whole disassemblies stayed under `/tmp/camera-agent-*`; no vendor binary is
  included in this folder. Integration and GNSS research were read-only.

## Precisely established configuration step

`mtk_gps_run` (`52fc48`) calls system init, then
`mtk_gps_init(startup != NULL, 0, startup)` at `52fcb4`. Its accepted init status
is **18**, not zero. In the init helper `52f264`, DSP status is classified at
`52f2c0`; both success and failure rejoin `52f2e8`. Consequently observing a later
configuration packet does not establish successful full MVCD or DSP readiness.

The constructor at `52f334..52f390` skips the following operation when startup
word at offset `0x28` is `0x40`. Otherwise it constructs exactly 232 bytes:
little-endian u32 `[3, 1]` followed by 224 zero bytes, then calls
`mtk_gps_set_param(42, block)`. This is the ordinary, non-offload dispatch path.

| Stage | Exact evidence |
| --- | --- |
| Parameter dispatch | `510028`: param42 -> internal message1016, length232 |
| Run-loop dispatch | table `4c4cf2` -> `530228`; subtype table `4c5244` |
| Subtype3 | `5323d4`: block word1 -> `5c6644(1)` |
| Configuration helper | stores low byte1; calls `699c50(NULL,"COMD",2,[50,1],3)` |
| Binary sender calls | `50bd60(5,1,5,payload)`, then `50bd60(5,2,5,payload)` |
| Payload | `32 00 00 01 00` (five bytes, not a single u16 argument) |
| Serialized frame | `aa f0 09 00 05 fe 32 00 00 01 00 3f 01 aa 0f` |

Here `50` is decimal (`0x32`), a payload subtype of command **FE05**. It is
**not command FE32**, and it is not FE05/u16 arg0. The wrapper rearranges the
second u32's bytes; do not replace it with a generic little-endian u32 serializer.
The real framing/checksum/escape routines were executed for this fixed payload;
this does not test all possible escaping inputs.

The second sender emits only when `508d0c()` has low byte1. Missing primary
context at the lower sender logs and emits no frame. The wrapper itself
dereferences contexts0/1/2 before these guards: do not call it with invented
contexts. The frame also emits with sender internal state1, so this sender is
not a RAMWORK/readiness gate.

An earlier `mtk_agps_set_param(38,NULL,1,4)` at `52f320..52f330` remains unaudited.
Matching mnld calls `mtk_gps_mnl_run(0xde520,0xde590)` at `63c30..63c40` and has
further parameter configuration afterward. This audit is not the complete list
of startup settings and does not establish that this packet starts navigation.

## Why the apparent stop counterpart is not start

- Param0 -> message1001 -> `5328b0` -> known variadic sender
  `50bbe4(5,3,1,4)` stop path.
- Param1 -> message1002 -> `530c80` -> `4fa5f8(1)`. That helper starts a reset
  sequence, including three calls `50bbe4(5,mask,1,4)` at `4fa640/654/668`, with
  mask1 or3 according to secondary availability. The test verifies the first
  call; the additional calls are static evidence. Param1 is not a simple start.
- At `542bfc..542c24`, a parsed double is converted to integer and mapped
  0->0, 1->1, other tested values2/7->2, then passed to
  `50bbe4(5,3,1,mapped)`. The following acknowledgement string is
  `$PMTK001,161,3*36\r\n` (`12ba1`). This is a PMTK161 control branch, not
  proof that cold initialization should send FE05/0. Whole parser validation
  and other numeric edge cases were not executed.

## Which feed reaches position processing

Static primary RX path (consistent with CALLBACK_ABI): read up to512 bytes
from fd global `6ee124`, caller `52571c`, then `mtk_gps_data_input` (`53cb28`)
in the non-alternate mode. Input is the binary AA F0 stream, **not NMEA text**.
Byte handling/extraction uses `554f80/554da4` and queued-copy helper `53ccf4`.
That helper has its own state/bypass guards; it calls `651fa4(context,byte)`
at `53cec8`. On return low byte1, primary states0 or6 select notification:
allocate6 bytes, store message header `{u16 type=101,u16 length=0}`, enqueue.
State1 and allocation failure do not enqueue on the tested branch.

Message101 -> table `4c4b44` -> `52fe6c` ->
`mtk_gps_main_flow(callback,0)` (`532fc8`). Static continuation checks queues
via `682dd0`, consumes primary via `682ef8(NULL)` at `533418`, and enters
host processing. Frame validation/dispatch includes `554d3c -> 509830`.
The measurement/epoch command semantics and complete solver path were not
established. Do not fabricate message101 without the actual queued input.

At `533674`, an output-ready byte must equal1. The tested branch clears it,
calls `53457c`, calls output routine `534b8c`, then invokes **callback(0)**.
That callback still runs when the mocked output routine returns failure.
The output routine statically calls `mtk_gps_get_position` (`50e2bc`) at
`534c84`; its actual branch at `534c88` proceeds only on return0.
The getter clears **0xc60 bytes** of the caller's buffer and rejects a null
buffer or failed internal gate. A public position structure layout is not
proven; a guessed small struct is unsafe.

Registered NMEA output slots from CALLBACK_ABI are +08 (`mnld 7b240`, app
output) and +10 (`mnld 7b3f0`, parser), with event callback +00 (`mnld 5de00`).
Neither callback0, output-ready, nor getter success alone proves a valid fix.
Position validity must be checked through an established output ABI or validated
NMEA fix fields. This audit executes neither a solver nor a position formatter.

## Reproduce the narrow test

From this worktree, with the existing container and pinned input:

```sh
docker exec -i mt6878-probe-build python3 - /probe/gnss-b41/libmnl.so < patches/gnss-navigation-audit/test_navigation.py
```

Environment inspected: Python3.14.7/aarch64, Unicorn module2.1.4,
pyelftools0.32, capstone5.0.6; disassembly via `/usr/bin/llvm-objdump`.
The test uses Unicorn and elftools, no phone-facing API. Each execution is
bounded to4096 instructions; non-whitelisted execution fails closed. Actual
ELF instruction ranges/tables execute against synthetic memory. Queue writes,
context lookup, logging, flush callbacks, output routines and allocation return
values are mocked or intercepted. Tests start at explicit internal branches,
not process entry: they establish local behavior, not end-to-end reachability.

Final result: all constructor/skip, init-status rejoin, dispatch/bounds,
PMTK161, reset-counterexample, exact-frame, absent-context/secondary,
RX-notification, allocation-failure, output-ready and getter-branch tests PASS.
State1 also emits the configuration frame: this negative readiness finding is
intentional, not suppressed.

Failures retained: the first feed test stopped with `UC_ERR_FETCH_UNMAPPED`
at an unmocked logging call (`50c1d8`); an explicit logging mock fixed the
harness. The first added output test had a missing `X23` register import
(`NameError`), corrected. Initial sandboxed Docker socket access was denied;
approved execution reached the same existing container. None is device evidence.

## Safe minimum next native implementation

1. Add a pure, offline-tested builder for the exact five-byte payload above to
   the main agent's existing framed transport, with a recording sink as default.
   Do not reuse the stop helper's u16 payload API, call internal library VAs,
   send PMTK161/FE05 arg0, or label this operation navigation start.
2. Keep emission disabled until the lifecycle owner can prove current-session
   full MVCD, RAMWORK, primary transport ownership, matching startup configuration
   and the preceding configuration dependencies. Sender acceptance is no gate.
   Audit AGPS param38 and the remaining mnld post-init configuration before
   treating this as a sufficient native sequence. Do not invent readiness flags.
3. Preserve continuous primary binary RX with bounded validated-frame counters;
   classify incoming data before attempting a position interface. Establish
   `509830` measurement/epoch routing and the position ABI offline. A transport
   bridge alone does not replace libmnl's host navigation processing.
4. Only after those gates and explicit authorization, the smallest supervised
   live experiment would send this single proven config frame on the primary
   link, once, with existing lifecycle stop/close handling and bounded RX capture.
   Do not force the secondary link, request a position, add retries, or infer
   success from a write/callback. Expected evidence is the captured outgoing
   frame and subsequent RX classification, not a fix. Unexpected state, transport
   loss or firmware fault ends the experiment under the lifecycle owner's
   recovery policy. This experiment has not been performed or authorized here.

There is deliberately no exact complete navigation-start recipe: the remaining
configuration and measurement-to-solver dependencies have not been proven.
