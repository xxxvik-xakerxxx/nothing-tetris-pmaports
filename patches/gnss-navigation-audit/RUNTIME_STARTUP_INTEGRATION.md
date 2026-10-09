# Runtime startup bundle and owned frame worker

New files only. Previously frozen adapter, first/second/XML/AGPS/control code,
headers, tests, runners and producer scripts remain unchanged. No phone/native
local build, commit, shared packaging or workflow change.

## Executable constructor chain

1. Frozen first builder + reviewed LNA bridge produce the real first base.
2. `b41_runtime_config_apply` fills all27 remaining first producer bytes from
   explicit typed owner snapshots, with provenance0x90 per output byte.
3. Frozen second builder produces identity, build policy, owned-fd snapshot,
   paths and MPE input copy. `b41_startup_bundle_build` adds26 proven scalar bytes,
   preserving the rest of second's provenance and owner/schema flags.
4. Bundle copies the distinct0x70/0x444 inputs and boolean second resolution map.
   It does NOT register callbacks, enter init/run, or clear engine gates.
5. Frame worker drains real callbacks3/4/5 copied requests, encodes AGPS150 via
   frozen host service, and sends through its exclusively assigned real IPC fd.

No generic success stubs or new raw-byte setter is exposed. Source group absence
returns-ENODATA with untouched output. All constructors still return1 partial
startup; a complete byte map is not a complete engine lifecycle.

## First producer bytes

| Bytes | Exact producer semantics |
| --- | --- |
| 20..23 | 62ce4..62d04: host88794==0 gives200, otherwise1000 |
| 28..2b | de308 OR actual2323c flags for receiver mode1/2/3 |
| 2c..2f | de308 if56ce0 boolean(de2fe), otherwise initial zero |
| 30..33 | Actual de304 chip-policy snapshot |
| 34..37 | de304 if same secondary predicate, otherwise initial zero |
| 38..3b | 88e10==-1 selects88c20; 88e14!=-1 overrides; BD_PRIORITY==1 would force4 |
| 50 | de9d8 unsigned values>1 normalize0 |
| 5b | de228 bits0/2/3 suppress; else host88794 and4eee0 bit0 select88c4c |
| 6c | ddd84 nonzero selects88c80, otherwise0 |

Exact XML GET miss for BD_PRIORITY is proven in the pinned libmnl parser. It
returns root type1 but preserves initialized zero policy. It is NOT GnssMode6,
nor permission to overwrite actual owner policy with a guessed mode. Wrong XML
hash is rejected by the frozen decoder before this source policy is applied.

The 27-byte branches are implemented, but their live source acquisition is not:
caller must supply the legitimate producer owner's88794, de304/de308/de2fe,
88c1c/88c20/88e10/88e14, de9d8, de228/4eee0/88c4c, ddd84/88c80 snapshots.
Presence flags are input completeness, not security/ownership certificates.
No scalar is promoted from zeroed storage or copied from a test handset.

`test_b41_runtime_producers.py` executed pinned mnld slices for all these bytes,
including128 MPE branch combinations and real file-backed2323c mode table.
It separately ran the full pinned GET decoder for absent BD_PRIORITY. PASS.

## Additional second producer bytes

| Bytes | Source |
| --- | --- |
| 0c | 63948..63954: byte88c18 |
| 24..27 | 63b98..63ba4: word88a5c |
| 64..67 | 63920..63940: wordde21c |
| 68..6b | Same word plus0x50000, actual ARM32 wrap semantics |
| b4..b7 | 63b90..63b9c: raw32 bits88c58 |
| b8..bf | 63b94..63ba0: raw64 bits88c68 |
| c4 | 56c90/63a84: capability byte9a4eb |

`test_b41_bundle_producers.py` executed each copy and overflow boundary against
pinned mnld: PASS. Raw float bits are preserved; no invented semantic conversion.
These fields are not falsely labeled as XML-derived. Applying stock19 tuning
features to engine-global consumers4fd870 and recovering remaining second policy
still require real consumer mappings. Frozen global XML policy gate remains set.

## Bounded worker quiescence, not engine stop

Single controller; fresh zeroed process-lifetime worker, adapter and IPC storage.
Start moves already-owned receiver fds after identity snapshots; never opens a
GPS node or probes hardware. This fd move does NOT prove driver readiness.
Detached worker uses actual queue/IPC functions. Unsupported NMEA/app/AGPS-data
events fail rather than being mislabeled as frame delivery. Frozen callback queue
contention can itself latch-EBUSY; this candidate does not hide that limitation.

`expose` must be called BEFORE vendor registration/init can retain callbacks/fds,
even if that registration later fails. Exposure is irreversible; no fabricated
uninit/stop acknowledgement can undo it.

Quiescence sets an atomic stop flag and signals private nonblocking eventfd. The
controller polls completion against an absolute CLOCK_MONOTONIC deadline. It
does not join/cancel a possibly blocked worker, call native engine stop, or close
device fds. Worker publishes completion after its last owner/storage access.
Like all non-real-time Linux code, deadline enforcement is subject to scheduling;
no hard real-time execution guarantee is claimed.

- Timeout/error: quarantine retains all receiver fds, IPC and callback storage.
- Exposure: even successful host-worker exit returns-EBUSY and quarantines.
- A late exit cannot revive quarantined state or permit cleanup/reinitialization.
- Before exposure only, successful quiescence allows separate `release_unused`.
  It checks ALL identities first, never closes a replaced foreign fd, never
  retries close(EINTR), and stops cleanup on first failure. Device close may block
  in the kernel; cleanup is deliberately separate from bounded quiescence.
- Exclusive ownership prohibits external fd close/reuse. fstat cannot detect all
  same-inode reuse races; identity checks are not a replacement for that rule.

Quarantine is process-lifetime containment, not a way to keep a failed engine
running safely or a hardware power-down guarantee. Supervisor must stop further
startup/use and recover through its owned process lifecycle, not unload drivers.

## Exact CI integration

Run `sh run_runtime_integration_ci.sh /path/to/verified/MNL_Config.xml` on Linux.
Requires pthreads/eventfd, libxml2/libcrypto development dependencies and existing
frozen sibling sources. No runner edits/installations are made by this chunk.
ASAN/UBSAN fixtures cover first27 output/provenance and missing groups, second26
bundle copies and unsigned wrap, real callback-to-socket packet delivery,
exposure quarantine, worker blocked in send at expired deadline, no revival after
late exit, substituted-fd refusal, peer failure and wrong event-owner refusal.
Native C fixtures are NOT compiled locally; their success remains a CI gate.

Local Python producer tests, AST parsing, shell syntax and scoped diff-check pass.
Next concrete runtime boundary AFTER native CI and source-owner integration:
create the sole worker with verified receiver/IPC ownership, deliver requests to
the legitimate service, verify responses, then prove native retained-thread stop.
This chunk authorizes neither mnl_run nor physical GPS activation.
