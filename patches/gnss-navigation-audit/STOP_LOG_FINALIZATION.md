# Stop delay: unterminated FSM printk record

Status: source-proven logging defect, offline-tested candidate fix; live fix
untested. No device access, builds, packaging edits or tracehelper changes.

## Actionable diagnosis

The supervisor is waiting for publication of a log record, not directly for
the hardware state. The vendor's final FSM printk has no newline. Linux can
leave that last record committed but not finalized indefinitely until another
printk reserves a record. Neither /dev/kmsg nor journald can read that record
while it remains unfinalized. Normal close is withheld by the supervisor until
it observes RESET_DONE, so it cannot be relied upon to generate the next log.
Unrelated kernel activity can break this dependency, explaining variability.

This is a publication dependency, not evidence of a 6-8 second DSP reset or
a slow MMIO operation. No newline does not mean the syscall reader receives a
partial line: the record is not readable at all yet. These are ordinary
pr_info records, not explicit pr_cont calls; the next ordinary record finalizes
the predecessor rather than necessarily concatenating their text.

## Exact pinned source chain

APKBUILD pins kernel `d84b264a54a37611f2f46bc19363cb9b41606205` and connectivity
modules `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`. The other pin `ee2be53...`
is the device-modules repository, not the GPS connectivity repository.
Vendor files were read with git show, not from the older checkout.

- `connectivity/gps/data_link/hal/gps_dl_hal.c:312-335`: MCUB flag log,
  clear flag, direct synchronous `gps_dsp_fsm(RESET_DONE, link_id)` call.
- `hal/gps_dsp_fsm.c:339-347`: state change has already occurred before
  normal or abnormal status logging. Neither format contains a newline.
- `inc/gps_dl_log.h:27` and `:213`: normal status macro ultimately calls
  pr_info without adding a newline. Warning macro has the same omission.
- `kernel/printk/printk.c:2192`: trailing newline sets LOG_NEWLINE and is
  stripped from the stored body. `:2239` vicinity captures source timestamp
  before publication. `:2322`: absent LOG_NEWLINE -> prb_commit; otherwise
  prb_final_commit. Both paths return; there is no wait for another printk.
- `kernel/printk/printk_ringbuffer.c:1763`: prb_commit stores desc_committed;
  it finalizes only if a newer descriptor already exists. `:1796`:
  prb_final_commit stores desc_finalized and advances finalized sequence.
- `:1884-1904`: desc_read_finalized_seq explicitly rejects desc_committed.
  `:86-106` documents that reserving a subsequent record finalizes its
  committed predecessor. There is no elapsed-time finalization rule here.
- `printk.c:796-828`: nonblocking devkmsg_read returns EAGAIN without an
  available record. A reader or select call does not finalize the last record.

Kernel source file SHA-256 values are enforced by the test:
`printk.c`: `d60698367c6548c4734c0862de22b583f5474add040a654815d89ada649a5ab1`;
`printk_ringbuffer.c`: `96840b39053bd9b4c7f0349528dd63a5ad8864a19e35671cf52bb8b474b66814`.
No local packaging patches referring to these GPS FSM/log or printk files
were found in the inspected kernel patch directory.

## Three observations, not three hardware timings

| Capture | MCUB journal time | FSM journal time | Displayed gap |
| --- | --- | --- | --- |
| repeat1 | 166.676499 | 173.276147 | 6.599648 s |
| repeat2 | 200.112368 | 208.024263 | 7.911895 s |
| stop-trace | 767.020356 | 767.296379 | 0.276023 s |

The successful trace puts the stop handler at 767.019547, FSM entry at
767.019616 and exit at 767.019633 (reported duration16.615 us). Its state-change
routine finishes at767.019622, and the containing handler ends767.019661.
The journal FSM timestamp is 0.276746 s after FSM exit. Initial ON also shows
trace766.924172 versus journal766.926521. This rules out treating the journal
timestamps as the execution times of those calls in this successful run.
Trace setup requests mono and sleep-time; capture reports no dropped events.
The helper hash matches its saved LIVE-PLAN. A single successful traced run
does not prove the absence of other stalls in either untraced failed repeat.

Repeat1's next displayed record after the delayed FSM is WLAN activity at
173.276753. Repeat2 release starts208.025185 after the supervisor deadline;
the log includes close wait interrupted with -512 and retval -22. The saved
plan says the supervisor timed out after STOP_WRITTEN. Cleanup/other logging
could then release the pending FSM record. Exact identity of that finalizing
writer in either repeat is NOT recoverable from short-form journal logs.
Preserve repeat2 as FAILED, even though normal OFF/CLOSED later appears.

## Journal versus KernelReader clocks

The inspected systemd v258 `parse_display_timestamp` deliberately ignores
_SOURCE_MONOTONIC_TIMESTAMP and falls back to the journal entry's monotonic
header timestamp for kernel messages without a source realtime timestamp.
Thus short-monotonic can show reception/storage time, not kernel printk time.
[systemd logs-show.c](https://raw.githubusercontent.com/systemd/systemd/v258/src/shared/logs-show.c).
The inspected v257 kmsg reader stores the kernel timestamp separately in
_SOURCE_BOOTTIME_TIMESTAMP and the legacy _SOURCE_MONOTONIC_TIMESTAMP field.
[systemd journald-kmsg.c](https://raw.githubusercontent.com/systemd/systemd/v257/src/journal/journald-kmsg.c).
These are source references, not a verified package-version match to this
phone. The captures lack source/header timestamp pairs, so do not assign every
millisecond to journald scheduling versus ring finalization. v258 kmsg source
fetch initially returned HTTP429; the v257 reference was available.

`gps_lifecycle.py` instead opens its own O_NONBLOCK /dev/kmsg cursor before
the operation and seeks to its current end. Lifecycle.feed checks the raw
header's sequence and timestamp. wait_for_phase uses host monotonic time for
its deadline and waits for EAGAIN after consuming available records. It does
not use journalctl, does not flush printk, and cannot see unfinalized records.
Source timestamp validation cannot solve delayed publication.

`supervise_gps_download.py` grants W after phase3 and grants R only after
STOP_WRITTEN plus phase4. Its unchanged total deadline is8 seconds; exception
cleanup terminates the child, potentially causing release logging. Increasing
the deadline or periodically writing a dummy kmsg record would mask the bug.
Waiting to drain to EAGAIN also creates a separate potential starvation issue
under continuous logging; it is not proof of the specific repeat2 cause and
is intentionally not changed in this fix.

## Minimal candidate and tests

`0001-gps-finalize-fsm-log-records.patch` changes only the normal and abnormal
FSM format strings to end in `\n`. It does not change all macros, MCUB logs,
severity, state ordering, hardware behavior or observer policy. printk strips
the terminator, leaving the observer's message pattern unchanged. Finalization
also makes earlier committed records readable; it is not a console flush.

Run from the owned worktree:

```sh
python3 -B patches/gnss-navigation-audit/test_fsm_log_finalization.py -v
```

Corrected result: **9 tests PASS**. The patch applies to exact git-show source in an
isolated `/tmp/camera-agent-fsm-*` fixture. Exact source-line matching checks
the hunk position independently of patch output; diagnostics on both stdout
and stderr reject offset/fuzz (case-insensitively, with LC_ALL=C). The corrected
hunk starts at340, with zero fuzz and zero offset in this fixture;
only two string terminators change. Tests enforce source hashes and execute
the actual hash-pinned KernelReader/Lifecycle with mocked read/select/time:
original quiet-ring reset times out; unrelated logging publishes it while
retaining its old source timestamp; fixed phases3/4/5 require no later printk;
unarmed reset and abnormal warning remain failures.

The sequential ringbuffer model follows the source's finalization rules; it
does NOT execute Linux C/atomics, concurrency, console output or wakeups.
No kernel compile or live validation was performed by this audit agent.
Correction retained: the original seven tests passed locally, but the report's
zero-offset claim was wrong. The main agent independently applied exact
git-archive source plus1002compat and this candidate using GNU patch --fuzz=0:
"Hunk #1 succeeded at 340 (offset 1 line)." The original header specified339.
The old test inspected stdout only and relied on patch diagnostics; why the
local invocation did not expose the mismatch was not established. The header
is now340. A new negative test rejects the original339 header even if patch
prints no warning; another rejects offset/fuzz on either output stream.
The main agent owns the targeted object build; this agent did not access its
container or claim its compilation result. An initial attempt to query
the device-module pin in the connectivity object store failed; APKBUILD then
established the correct repository/pin. Original observer/trace files untouched.

## Minimal next gate for the lifecycle owner

Review this two-line candidate before integrating it through the normal kernel
ownership boundary. Keep the same protocol and8-second deadline; no requests,
retries, forced log flushes or console/loglevel changes. A later explicitly
authorized experiment should pair an independently retained raw /dev/kmsg record
(sequence, source timestamp, monotonic receipt timestamp) with the existing
isolated trace. Expected: RESET_DONE becomes observable without any subsequent
unrelated printk; hardware path remains unchanged. Capture journal JSON source
and header fields as secondary evidence where available. Current overwritten
dmesg cannot reconstruct them. Preserve timeout/cleanup errors and existing
recovery policy; a single success still does not establish repeated lifecycle
support. This gate was not run here.

## Evidence hashes

All paths below are relative to `worktrees/hardware-integration/local/`:

- `gnss-supervised-c931-repeat-1/kernel.log`:
  `5b29e6229a9d31df2cb8693c9d5e41c49f90def2088f4b551acefa2527611ae7`
- `gnss-supervised-c931-repeat-2/kernel.log`:
  `8b56f2dfe434c2a748f39452a75a39dea46790a321dedbadf16a56aec3f9cb64`
- `gnss-supervised-c931-stop-trace/result.txt`:
  `0a077be304b60699d72d3d91a60e3904910246918ed9a191e14dde87f605a65b`
- `gnss-supervised-c931-stop-trace/kernel-active.log`:
  `3ee3b1f21cd3a52c76a57d4ba7505cb6d42429776edd3f57229a324791f78d25`

Userspace source SHA-256:

- gps_lifecycle.py: `52d18c1e7751c247da07d1252de55d10bc099df86bd9ebb466bc817a111c908e`
- supervise_gps_download.py: `71bdecfa6aa3c8e61e14ca28d7d98cab420c161814e19d6c790b0d75c570b046`
- gps_stop_trace.py: `89586b10b836b9ef63a4e91880c929f48914dc7d78e424fa880d4d1ddef66305`
