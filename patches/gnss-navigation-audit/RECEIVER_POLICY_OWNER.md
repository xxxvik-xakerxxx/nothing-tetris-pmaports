# B4.1 Receiver Policy Producer

Candidate implementation; native compilation/execution and integration remain
pending. No engine, hardware, SSH, emulator, JIT, CI dispatch or push was used.
This closes the property acquisition dependency of the existing build-policy
constructor and implements five exact second-config producer bytes. It does
not establish complete receiver configuration, INIT or a GPS fix.

## Matching evidence

Pinned private assets were read from
`worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41` beneath the
outer workspace. The requested `worktrees/gnss-userspace-bridge/local/ota-b41`
directory was absent; no substitute release was used. Whole-file SHA256:

- mnld: `285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83`
- libmnl.so: `3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90`

All addresses below are file-backed ELF virtual addresses, checked statically
with Capstone. There is no execution of vendor instructions.

| Producer or consumer | Exact evidence |
| --- | --- |
| Property source | mnld628f4..62944 reads `ro.build.type` at138bd, then `ro.debuggable` at138cb, both with NULL fallback. PLT85530 uses GOT86bc8, whose AArch64 JUMP_SLOT relocation names `property_get`. |
| Accepted build policy | 62948..629c4 compares exact NUL-terminated `eng`, `userdebug`, `user`; debug must equal `1` for eng/result1 and userdebug/result2. User/result0 ignores debug contents. Unknown or unsupported combinations return -1 in stock. |
| Second+c8 | 63690 calls628e0;636ac makes x26=de594 (second base de590+4);636c4 writes result at x26+c4, hence second+c8. |
| Second+4 | 63698 reads byte de3c0;636a0/b4 reads byte88e40;636a4 reads word884c4. 636b0/bc,cc,d4 clear only bit0 if de3c0==0 AND884c4==1;636d8 writes the resulting byte at x26. |
| Register-base provenance | x25 initially points at de000 at62e54 but63028 changes it to88000 before636a4. The policy word is **884c4** (88000+4c4), not de4c4. The static test checks the last assignment and address arithmetic, not just existence of an earlier assignment. |
| Policy-word meaning | 63a20 retains this base in x24;63bd4/d8 tests [x24+4c4]==1. That branch calls859a0 at63bf0, whose GOT86e00 relocation names `mtk_gps_ofl_ap_config_init`. This is an AP config-init selector, not an inferred resume flag. |
| Actual INIT consumers | lib52b69c/a0 copies0x444 bytes;52b6c0 reads second+c8, then52b6d8/e0 stores it through two GOT pointers. 52bac8/cc reads second+4 and tests bit3;52bad0/e0 can open the serial-output path at second+1ea. Preserving all log bits matters. |

## Implementation and boundary

`b41_receiver_property_read` calls the actual Bionic `__system_property_get`
underlying the stock property service. It accepts only the two pinned keys and
checks the92-byte ABI. Other libc implementations return `-EOPNOTSUPP`.
Absent values fail with `-ENODATA`; no environment, guessed build type or file
replacement is introduced. Stock's NULL-fallback empty strings and unsupported
result -1 are deliberately refused by the existing conservative constructor.

`b41_receiver_properties_collect` owns a single setup attempt and frozen
process-lifetime strings, reading the keys in source order. Reads stop at the
first failure, preserving earlier evidence and the original error. Reentry
never reads again. Missing/oversized/malformed values fail visibly. The fixed
two-read userspace bound does not bound the property service itself; the parent
must retain the dedicated child's external process deadline.

`b41_receiver_policy_apply` reuses `b41_startup_set_build_policy` rather than
adding another string-to-policy mapping. It consumes the collected properties
and a legitimate policy owner's named snapshot for de3c0/884c4/88e40. It writes
only second+4 and+c8..cb, tags those bytes, rejects conflicting already-resolved
bytes, supports aliasing input/output, and recounts unknown bytes. It fulfills
only `B41_SECOND_BUILD_POLICY`; other missing-input bits, including unknown
bits, and receiver/stop/MPE semantic gates remain verbatim. Return1 is partial.

Parent integration can build the second block without BUILD_POLICY, collect
the properties before worker exposure, and apply this candidate before
`b41_startup_bundle_build`. Existing bundle writes do not overlap these five
bytes. No existing session or admission code was changed.

The first remaining producer needed by this API is the legitimate native
policy snapshot of **log byte88e40, secondary-policy byte de3c0, and AP config-init
word884c4**. This patch proves how they are transformed, but does not acquire
those globals or authorize zeros in their place. The other second-block fields,
path override origins, MPE schema/buffer ownership, first-config source gates,
AGPS receiving service/response semantics and full INIT remain independent
requirements. An outgoing connected AGPS socket cannot fulfill them.

## Verification and parent commands

Seven Python static/source tests pass against both exact assets, including
property import resolution, accepted string branches, last-register-assignment
provenance, second offsets, actual INIT consumers and unchanged admission gates.
The five existing endpoint static tests also pass. Shell syntax passes.

The C fixture is written but **not compiled or run locally**. It covers12288
build/log/secondary/AP-config vectors, exact unrelated-byte preservation, aliasing,
stale counters, retained unknown bits and semantic gates, malformed/missing
properties, first-error retention, reentry without new reads, and immutable
rejection for every conflicting byte. Wrapped boundaries never access devices,
the actual property service or a vendor engine.

Next actual Ubuntu native CI command, from repository root:

```sh
CI=true sh patches/gnss-navigation-audit/run_receiver_policy_ci.sh
```

The runner uses ASan/UBSan, C11 and warnings-as-errors with separate compile
and fixture deadlines. Parent can add it to the existing GNSS candidate step;
the workflow is outside this change's write scope and was not edited.

Next actual ARM64 Bionic API28 compile/link command in parent CI, using the
existing pinned NDKr27d installation and an existing `out` directory:

```sh
CI=true \
BIONIC_CC=/tmp/android-ndk-r27d/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android28-clang \
sh patches/gnss-navigation-audit/run_receiver_policy_ci.sh \
  --bionic-compile out/b41-receiver-policy-test
```

This compiles the real Bionic producer and links the fixture with wrapped
property boundaries. It does not run the artifact or a foreign-architecture
substitute. Parent must perform its normal ELF/closure checks and eventual
native fixture execution in the actual ARM64 Bionic environment.

Repeat only the static audit locally, from outer workspace:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012 \
python3 upstream/nothing-tetris-pmaports/patches/gnss-navigation-audit/test_b41_receiver_policy_source.py \
  worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/mnld \
  worktrees/nothing-tetris-scp-thermal/local/display-probe/gnss-b41/libmnl.so
```
