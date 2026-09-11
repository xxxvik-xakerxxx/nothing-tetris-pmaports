# B4.1 post-init and host output boundary

Status: Partial source/emulation audit; native loading and navigation Untested.
No phone access, firmware operation, CI, full build or integration change.

Follow-up: `FRAME_SYNC_CONFIG_ABI.md` resolves slots3/4 machine signatures and
tests the second-config producer/copy slices; its remaining prerequisites
supersede the corresponding next-audit items below, not the runtime cautions.

## Provenance and method

Pinned Nothing B4.1 inputs, not the older source checkout:

- libmnl.so SHA256 `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`
- mnld SHA256 `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`
- Existing container inputs: `/probe/gnss-b41/{libmnl.so,mnld}` in
  `mt6878-probe-build`; local provenance under the GNSS worktree's
  `local/ota-b41/vendor-lib64` and `research/gnss-b41-inputs/import-summary.json`.
- Read-only companion evidence: `research/gnss-b41-inputs/CALLBACK_ABI.md`.

Addresses below are ELF virtual addresses, not runtime addresses or trustworthy
nearest-symbol labels. The test verifies both hashes, executes whitelisted ARM64
slices in Unicorn, and mocks external calls and globals explicitly. It does not
perform ELF relocation, native dlopen, full initialization or solve observations.

## AGPS 38 is not a navigation start

libmnl init at `52f320..52f330` calls `(38, NULL, 1, 4)`; another init
branch repeats this at `52f520..52f530`. Export `mtk_agps_set_param` at
`6b17b0` dispatches 38 to `6b1908`, 37 to `6b1920`.

The producer at `6b1930..6b196c` allocates payload length plus 10 bytes and
writes four little-endian u16 fields: source, destination, subtype, payload
length, then the payload at offset 8. Tested initialized bytes:

- 38: `01 00 04 00 12 00 00 00`, payload absent, allocation 10.
- 37 from mnld: `06 00 04 00 04 00 10 00`, followed by 16 bytes, allocation 26.

The final two allocation bytes remain untouched in both tests. The allocator
chain `651668 -> 508010 -> malloc` is not a zeroing allocator (static trace).
Do not serialize the allocation size or turn this internal object into a
gpsdl packet. Allocation and non-offload queue failure return -1; queue failure
frees the allocation. The offload branch is static-only, not validated here.

Non-offload queues through `651500`. Assistance worker `52d9ec`, receive
`50901c -> 6512dc`, calls `mtk_agps_agent_proc` (`6b3d14`) at `52da54`, then
frees the message. Source 1/subtype 18 reaches common assistance FSM selection
(`6b3e5c -> 6b3f74`), not the navigation runloop's message 1016.

The actual active FSM (`6b1fdc`), mode 2, handles subtype 18 at `6b207c` by
clearing assistance state and returning -1. The bounded test verifies state
clearing; subtype 17 returns 0 and retains state. Idle handling uses assistance
policy selection (`6b1b50`, call `mtk_agps_select` at `6b1bc4`); it is not fully
covered. Thus 38 is state-dependent assistance control, not a universal reset
or FE05 start. Param37's source6/subtype4 consumer at `6b40ac` copies assistance
policy fields; the full meaning of its 16-byte input remains unresolved.

## Remaining mnld configuration

At `63c30..63c40`, mnld calls `mtk_gps_mnl_run(0xde520, 0xde590)` and expects
return 18 (`63c7c`). Success-side optional EPO/QEPO/MTKNAV file updates precede
AGPS37 at `642cc` (two possible retries at `64310`, `64354`). This audit does
not adopt those retries. Property/global construction of the 16-byte AGPS37
block is only partially recovered; synthesizing the rest as zeros is unjustified.

The contiguous `643e4..64644` slice is executed with conditions both off and on.
The separate libmnl dispatcher slice verifies these message/length contracts:

| Param | mnld pointer | Condition | Internal message, bytes |
| --- | --- | --- | --- |
| 59 | ddd94 | always | 1026, 1 |
| 73 | ddd9c | always | 1030, 1 |
| 60 | ddd98 | byte 9a933 != 0 | 1029, 1 |
| 74 | de4b4 | always | 1031, 1 |
| 104 | 9bc20 | always | 314, 1 |
| 126 | de4a0 | word de484 == 1 | 1077, 4 |
| 121 | ddd78 | always | 1072, 4 |
| 133 | e02e0 | always | 1082, 8 |
| 135 | sp+a8 | w19 == 2 | rejected by ordinary non-offload table |
| 131 | sp+90 | always after 62550 | 1080, 4 |

Param133's AUDIO_INFO log displays one word, but its payload is eight bytes.
Param131/TMS_FREQ carries the ioctl30 result, not a guessed Hz value.
Param135/BEIDOU_PRIORITY exceeds the libmnl bound 133 at `50fda4`; rejection
is tested, not evidence to widen that table or fabricate a replacement command.

Not covered by this contiguous test: assistance asset updates, the complete
AGPS37 policy producer, helper `4ef80`, stored accuracy handling near `64398`,
helper `61770`, conditional offload MPE/screen configuration after `64644`,
and cached accuracy application at `646ec`. libmnl's own mode-4 branch also
has conditional params4/46 at `52f404`/`52f428`. No exhaustive startup ABI is
claimed from the tested subset.

## Host solver and output contract

For the traced non-offload vendor pipeline, **yes: libmnl's host engine must
execute** (or its decoder/solver must be independently replaced). A native
receiver alone has no demonstrated DSP-stream-to-NMEA implementation. The
observed path runs data input and main flow before position formatting; neither
fullMVCD nor an FE05 opcode proves a position solution.

This is not proof that ordinary pmOS dlopen is supported. The pinned ELF needs
`libc++.so`, `libc.so`, `libm.so`, `libdl.so`, and uses Bionic/fortified imports,
including `__errno`, `__strlen_chk`, `__strncpy_chk2`, `__open_2`. pthread,
stdio, TLS/canary and other runtime ABI contracts also matter. Symbol-name shims
or renaming musl cannot establish compatibility.

Registration at `52f9d0` reads a 24-slot region (some slots skipped), requires
nonnull slots 0,1,3,4,5,6,7,8,9 (mask `0x3fb`), and changes stored pointers
even on failure. Full/null/each missing-slot cases are tested. Slot2 is not
required by those null checks, but is an output route. Unknown required callback
signatures must not be replaced by guessed stubs.

Static init copy: first argument is 0x70 bytes; second is 0x444 bytes at
`52b698..52b6a0`, to storage reached via GOT `6e69d0`. The following marker
belongs to the SECOND config block, not the first startup block.

Formatter `534b8c` uses dispatch `50c1d8` with category 5 (for example
`53add0..53adec`), routed via `508cfc` to `5243a0`. Its output branch compares
11 bytes at second-config offset `0x1cc` with `UseCallback` (`524a30..524a6c`).
Match and nonnull slot2 calls slot2 at `524a88`; otherwise it writes through fd
helper `521770`. Slot1/app is then called at `524ab8`. Tests verify marker
match/mismatch, pointer plus w1 byte length, embedded NUL preservation, and that
returning -1 from the callback does not prevent the next callback.

Static cautions outside that bounded branch: config bit2 can cause an additional
app callback; output holds lock4 from `5244e0` until `5249f8`. Copy bytes promptly,
do not block or reenter libmnl, retain the borrowed pointer, or interpret callback
return as delivery acknowledgement. mnld slot2 (`7b3f0`) passes pointer/length
to parser `684e0` at `7b454`; this is not itself a proven external NMEA service.
Output may be proprietary sentences or invalid fixes.

## Implemented prerequisite and tests

`b41_nmea_boundary.h` provides a pure numeric-table preflight before the
nontransactional registration and a bounded borrowed-output copy. It neither
casts/calls function pointers nor defines a complete vendor ABI. Capacity is
caller policy, not a recovered vendor maximum. No terminator or fix claim is
added. `test_b41_nmea_boundary.c` tests missing slots, invalid lengths/pointers,
embedded NUL, buffer lifetime and bounds with ASan/UBSan.

Run from this worktree (output executable outside git):

```sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined patches/gnss-navigation-audit/test_b41_nmea_boundary.c -o /tmp/camera-agent-nmea-boundary-test
/tmp/camera-agent-nmea-boundary-test
docker exec -i mt6878-probe-build python3 - /probe/gnss-b41/libmnl.so /probe/gnss-b41/mnld < patches/gnss-navigation-audit/test_b41_startup.py
```

Both tests PASS. Original emulation failure is retained here: param131 reached
unreviewed external `0x6e4910`; the harness stopped. Explicit diagnostic mocks
for that address and `0x50c1d8` were added to the dispatcher-only test. No binary
change, fallback execution or blanket instruction allowance was used.

## Next minimum implementation

Audit the mandatory callback signatures (especially slots3/4) and the complete
second-config producer, then build a fail-closed, offline compatible-runtime
preflight with device/file/ioctl access denied. Reuse this copy boundary for
bounded output collection, not the opaque mnld application callback. Do not
call mnl_run on top of an already initialized native receiver: startup transport
ownership/handoff is unresolved and may duplicate initialization.

No new live command is justified yet. Before a supervised live engine test,
prove single transport ownership, exact startup blocks/runtime ABI, and bounded
stop/close behavior. Its eventual evidence must distinguish raw output from
checksum-valid NMEA and a valid timestamped position. This audit does not promote
GNSS to navigation support and does not alter the separate r155 lifecycle work.
