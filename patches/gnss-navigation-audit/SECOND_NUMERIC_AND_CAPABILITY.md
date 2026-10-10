# Second numeric constructor and actual capability branch

New source constructors; frozen code unchanged. Native CI pending. No engine,
library query or phone operation was executed. Existing installed features are
not affected by these unintegrated userspace helpers.

## Important correction: MT6878 uses the property branch

Pinned B4.1 libmnl3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90:
mtk_gps_get_chipset_capability_v2 at51b488 reads the chipset matcher result,
copies the matching immutable0xd0 capability record into mnld's second capability
buffer. The mnld descriptor887a0 has relocated pointers de230 and de2f0.
Capability byte+cc therefore becomes de3bc, the calibration branch decision.
It is NOT an independently chosen default boolean.

The exact table at6edd50 has MT6878 records21/22/23:

| Adie | Key | Capability | +cc |
| --- | --- | --- | --- |
| 0x6631 | 6ed710 | 6ed7d0 | 1 |
| 0x6637 | 6ed8a0 | 6ed960 | 1 |
| 0x6686 | 6eda30 | 6edaf0 | 1 |

New b41_capability_branch_read reads those real relocated records from the
legitimate retained associated image. It requires actual chip/Adie identities,
checks exact GOT/table/key/value addresses and revision predicates, and copies
the actual capability record. It refuses absent/unknown Adie rather than using
OEM's empty-Adie first-match wildcard. No global mutation/library call/permission
boolean is added. Main must pass the real identity owner; test mappings are
parser fixtures, never substitutes for the legitimate loader/SHA gate.

Consequently the accepted legacy NV bridge must NOT be invoked as MT6878's
default calibration source. Its source-profile refusal is correct. Main can
obtain property_branch_de3bc directly from capability[cc], never caller zero.
Profile selector de22c is separately set by NVM_GetFileDesc/read of52-byte
platform profile9bc24 at7b0d4..7b184; it is not derived from the capability flag.
Missing profile-origin evidence is not default0 evidence.

When modern properties are absent,56d00 calls7f960, which creates a worker7f440.
That worker uses actual MIPC SETCOM/init/message141/sync-timeout and response
tags0(status),101(c0),102(c1),103(capid.temp), then publishes properties. It is
NOT a legacy ML4A fallback. Porting that actual modem-owned MIPC response path
must be coordinated with the modem owner; no invented file substitution,
successful IPC stubs, source writes or modem work is implemented here.

## Second block:38 concrete missing bytes

mnld636a8/ac sets x26=de594, which is second(de590)+4.63828..638c4 therefore
writes buffer sizes at second+1c/+20 and the float text at+28, not+18/+1c/+24.
New b41_second_numeric_apply reproduces the exact requested-buffer clamps:

- requested_dfff4 below1MiB produces25MiB and a300MiB secondary floor.
- Otherwise primary is min(request,48MiB); secondary floor is12*primary.
- Secondary is max(requested_dfff8,floor), capped at512MiB.
- Actual binary32 bits de4bc are promoted to double and formatted %.1f in a
  30-byte field at+28. The remaining bytes are source memset-retained zeros.

The helper uses a private C numeric locale, never changes process-global
locale, refuses nonfinite/oversized output, preserves unrelated bytes and
provenance, and marks only these38 bytes. Inputs must come from the legitimate
request/float owner. Computing sizes does not allocate buffers or establish the
owner behind second+64/+68. SECOND_POLICY stays unresolved, as do remaining
flags/scalars, paths, platform state origin, MPE schema and actual assistance.
No blanket zero provenance or mask-clearing constructor is added.

## Integration and CI

Main can apply b41_second_numeric_apply to the frozen second constructor output
before startup_bundle_build; its runtime writes do not overlap these38 bytes.
Read capability through the retained associated image before choosing any
calibration provider. Keep all remaining producer/source masks.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT/test_b41_capability_branch.py" \
  "$ASSETS/vendor/lib64/mt6878/libmnl.so"
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT/test_b41_second_numeric_producer.py" \
  "$ASSETS/vendor/bin/mnld"
CI=true sh "$AUDIT/run_second_numeric_ci.sh"
```

Both offline oracles passed:3 exact chipset matches plus unknown-Adie refusal,
and15 buffer boundary vectors with exact float-format call ABI. They intercept
external calls, not emulate a modem/navigation fix. Python needs pyelftools and
Unicorn plus the existing lifetime-managed Machine. Native/Bionic API28 closure:
b41_second_numeric.c, b41_capability_branch.c, test_b41_second_numeric.c.
Existing sanitizer/warning policy unchanged; no new linked library. Fixtures
cover numeric boundaries/immutable failure/provenance and pure relocated-record
parser success/refusals, not hardware or real loader success.
