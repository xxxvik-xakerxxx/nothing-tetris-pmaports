# MD handoff reservation owner

Candidate, compile-only. Startup scope C/header/checker/component/vendor patch
and STARTUP_SCOPE.md remain frozen for main CI. No phone, activation, shared CI,
APKBUILD, U-Boot, git commit or local C build is part of this change.

## Concrete boundary

`mt6878_md_handoff_reservation.c/.h` creates a private immutable snapshot from
two explicit static `/reserved-memory` child nodes and a 32-byte **unverified
digest claim**. No invented addresses, node names, LK wire format, authentication
token or secure-monitor request. The factory checks each DT resource against
the boot reserved-memory table (lookup matches basename, not node identity),
rejects zero/overflow/multiple ranges, overlap, missing no-map, reusable and
reserved-memory ops, and rejects dynamic OF trees and module compilation.

Both actual Linux iomem regions must be claimed before publication. Busy System
RAM or another owner is an error, not a reason to ignore/steal the resource. A
second-claim failure releases only the first owned region; the first error is
returned. Successful publication pins both nodes and claims for the boot; there
is deliberately no hot-unbind/release API. Call once during owner setup, before
scope_begin. Normal Linux caller synchronization is required for publication.
It is not devm-managed and must not be retried as an allocation loop.

The retained ranges describe vendor ROM/RW and AP-MD SMEM reservations, not an
authenticated executable extent. The claim is copied, not computed over ROM.
An iomem reservation excludes cooperating Linux claimants, **not** physical
secure-world/MD/DMA writers. No ROM mapping/read or device power operation occurs.
This cannot certify that loaded bytes stay immutable.

`mt6878_md_reserved_handoff_ops` plugs into the frozen startup-scope interface.
Snapshot returns the private copy. AUTH rejects mismatched explicit fields or
digest with ESTALE and rejects an intact record with ENOKEY, unconditionally.
Consequently scope_begin stops before modem startup. Do not advertise this as a
completed authentication provider or wire it as a working modem backend.

## Exact evidence gap

Pinned vendor commit `ee2be53cb75670b548948636a0db1d1ff112bf12`:

- `drivers/misc/mediatek/ccci_util/ccci_util_lib_fo.c:453,459`: SMEM address/size
  come from LK smem layout. At 522-535 ROM/RW address/size and a readiness flag
  come from `hdr_tbl_inf` and its errno. At 1052-1069 the getter only returns
  globals, always zero; this is not verification of bytes or a signed digest.
- Same file 1240-1257 installs a reserved-memory initializer and the fallback DT
  layout; neither reserved memory nor no-map is cryptographic provenance.
- `ccci_util_lib_load_img.c:80+` and `:219+`: header format/version/size checks.
  The security-feature conditional at 29 includes security headers; it does
  not authenticate the digest in this file. `ccci_util/Makefile:33-36` selects
  that define based on CONFIG_MTK_SECURITY_SW_SUPPORT, not a success record.
- Existing POWER3/POWER2 BROM state/data flags and BOOT-enable state have no
  established binding to ROM range/digest. No new AUTH interpretation is made.

To implement successful AUTH, main needs either the matching secure/LK verifier
contract and outcome bound to the exact installed MD1 payload/range/digest plus
a trustworthy handoff/query, or the signed container/certificate format and
independently trusted signer key with permitted ROM reads and proven write
exclusion during verification/execution. A caller-supplied digest/header/errno
alone cannot fill that gap. EMI/remap and NS-access admission remain separate
requirements; this owner does not weaken them.

## Lock audit

Frozen scope orders supplier device_lock before md_scope_lock; supplier probe
has that same order. Begin temporarily takes scope mutex to acquire a supplier
reference, releases it, then takes the two locks in order. Once held, snapshot
and AUTH execute synchronously under **both** locks. The new callbacks are only
private copy/comparison; no mutex, device lock, PM, SMC, firmware request or
external verifier callback. Factory resource/OF allocation happens before scope.

Important remaining interface constraint: begin sets `md_scope.task` only after
its AUTH callback succeeds. A future AUTH callback recursively calling begin
or scoped INIT can deadlock before the same-task guard becomes effective; a
callback taking the same supplier device_lock also deadlocks. New callbacks
never do this. Frozen scope is not changed. Main must enforce a non-reentrant
callback contract or separately fix/validate that guard before admitting an
external verifier. Holding supplier lock does not lock all ATF execution.

## Main integration / next gate

1. Locally run `python3 patches/modem/check_handoff_reservation.py` (static only).
2. In independent Ubuntu CI run the same checker with `--native-ci`; it compiles
   the unmodified production body with strict warnings and ASan/UBSan. Tests
   cover range/provenance errors, partial claim rollback, immutable copy, every
   state field mismatch and AUTH never succeeding. Native result is pending.
3. For main's packaged-object smoke, install the new header/C together under the
   existing default-off startup-scope component and compile built-in, with the
   frozen public startup header. No new Kconfig/Makefile/shared packaging edits
   are included here. There is no automatic probe or shipping DT consumer.
4. Establish the real AUTH prerequisite above before adding a success-capable
   provider, ROM mapping, secure call, transport start or live experiment.
